#!/usr/bin/env python3
"""
Instagram DM Unsend — Нэгтгэсэн хувилбар

Нэг тодорхой чат эсвэл бүх чатуудаас өөрийн илгээсэн мессежийг unsend хийнэ.

Онцлогууд:
- CLI arguments (target username, delay, dry-run, amount гэх мэт)
- Interactive горим (--all-chats эсвэл target_username-гүйгээр)
- Бүх inbox scan (primary, general, pending, spam)
- Raw API fallback (Pydantic validation алдаа гарахад)
- Retry логик + rate limit хамгаалалт
- 403 алдааг таньж алгасна

instagrapi (unofficial API) ашигладаг — зөвхөн өөрийн аккаунт, өөрийн
мессеж дээр ашиглаарай.
"""

from __future__ import annotations

import argparse
import getpass
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Optional

from instagrapi import Client
from instagrapi.exceptions import LoginRequired


DEFAULT_SESSION_FILE = "session.json"
MAX_RETRIES = 5


# ──────────────────────────── CLI ────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unsend your own Instagram DM messages."
    )
    parser.add_argument(
        "target_username",
        nargs="?",
        default=None,
        help="Instagram username you chatted with (without @). "
             "Omit for interactive thread selection.",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("IG_USERNAME"),
        help="Your Instagram username. Can also be set as IG_USERNAME.",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("IG_PASSWORD"),
        help="Your Instagram password. Can also be set as IG_PASSWORD.",
    )
    parser.add_argument(
        "--verification-code",
        default=os.getenv("IG_2FA_CODE"),
        help="Optional 2FA code. Can also be set as IG_2FA_CODE.",
    )
    parser.add_argument(
        "--amount",
        type=int,
        default=200,
        help="Max messages to fetch per thread. 0 = all available.",
    )
    parser.add_argument(
        "--thread-scan-amount",
        type=int,
        default=0,
        help="Max inbox threads to scan when participant lookup fails. 0 = all.",
    )
    parser.add_argument(
        "--all-chats",
        action="store_true",
        help="Interactive mode: list all chats and choose which to unsend from.",
    )
    parser.add_argument(
        "--allow-group-thread",
        action="store_true",
        help="Allow deleting messages from a group thread.",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=0.0,
        help="Min seconds between delete requests.",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=0.0,
        help="Max seconds between delete requests.",
    )
    parser.add_argument(
        "--no-delay",
        action="store_true",
        help="No intentional wait between requests.",
    )
    parser.add_argument(
        "--session-file",
        default=DEFAULT_SESSION_FILE,
        help=f"Path for reusable login settings. Default: {DEFAULT_SESSION_FILE}.",
    )
    parser.add_argument(
        "--newest-first",
        action="store_true",
        help="Delete newest messages first. Default: oldest first.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be unsent without deleting anything.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt.",
    )
    parser.add_argument(
        "--max-threads",
        type=int,
        default=100,
        help="Max threads to load in interactive mode. Default: 100.",
    )
    return parser.parse_args()


# ──────────────────────────── Login ────────────────────────────


def do_login(
    username: str,
    password: str,
    verification_code: Optional[str],
    session_file: Path,
) -> Client:
    client = Client()
    two_factor_code = verification_code or ""

    if session_file.exists():
        try:
            settings = client.load_settings(session_file)
            client.set_settings(settings)
            client.login(username, password, verification_code=two_factor_code)
            client.get_timeline_feed()
            print("[+] Session ашиглан нэвтэрлээ!")
            return client
        except LoginRequired:
            print("[*] Session хугацаа дууссан, шинээр нэвтэрч байна...")
            old_settings = client.get_settings()
            client.set_settings({})
            if old_settings.get("uuids"):
                client.set_uuids(old_settings["uuids"])
        except Exception as exc:
            print(f"[*] Session ашиглаж чадсангүй: {exc}")

    client.login(username, password, verification_code=two_factor_code)
    client.dump_settings(session_file)
    print("[+] Амжилттай нэвтэрлээ!")
    return client


# ──────────────────────────── Helpers ────────────────────────────


def value_from(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def thread_id_from(thread: Any) -> Optional[str]:
    if hasattr(thread, "id"):
        return str(thread.id)

    if isinstance(thread, dict):
        thread_data: dict[str, Any] = thread.get("thread") or thread
        thread_id = (
            thread_data.get("thread_id")
            or thread_data.get("id")
            or thread_data.get("thread_v2_id")
        )
        if thread_id:
            return str(thread_id)

    return None


def get_thread_display_name(thread: Any) -> str:
    title = value_from(thread, "thread_title", "")
    if title:
        return title
    users = value_from(thread, "users", []) or []
    if users:
        names = []
        for u in users:
            uname = value_from(u, "username", "")
            fname = value_from(u, "full_name", "")
            pk = value_from(u, "pk", "")
            if uname:
                names.append(f"@{uname}")
            elif fname:
                names.append(fname)
            else:
                names.append(f"user_{pk}")
        return ", ".join(names)
    return f"thread_{thread_id_from(thread) or '?'}"


def message_preview(message: Any) -> str:
    if isinstance(message, dict):
        text = message.get("text", "")
        item_type = message.get("item_type", "non-text")
    else:
        text = getattr(message, "text", None)
        item_type = getattr(message, "item_type", "non-text") or "non-text"
    if text:
        return text.replace("\n", " ")[:80]
    return f"<{item_type}>"


# ──────────────────────── Thread finding ────────────────────────


def thread_matches_user(
    thread: Any, target_user_id: str, target_username: str
) -> bool:
    target_username = target_username.lower()
    for user in value_from(thread, "users", []) or []:
        user_id = str(value_from(user, "pk", ""))
        username = str(value_from(user, "username", "") or "").lower()
        if user_id == str(target_user_id) or username == target_username:
            return True
    return False


def scan_threads_for_user(
    threads: list[Any],
    target_user_id: str,
    target_username: str,
    allow_group_thread: bool,
) -> Optional[str]:
    group_match: Optional[str] = None

    for thread in threads:
        if not thread_matches_user(thread, target_user_id, target_username):
            continue
        tid = thread_id_from(thread)
        if not tid:
            continue
        if value_from(thread, "is_group", False):
            group_match = group_match or tid
            continue
        return tid

    if allow_group_thread:
        return group_match
    return None


def find_thread_id(
    client: Client,
    target_user_id: str,
    target_username: str,
    thread_scan_amount: int,
    allow_group_thread: bool,
) -> str:
    errors: list[str] = []

    try:
        thread = client.direct_thread_by_participants([int(target_user_id)])
        tid = thread_id_from(thread)
        if tid:
            return tid
    except Exception as exc:
        errors.append(f"participant lookup: {exc}")

    scan_sources = [
        ("inbox", lambda: client.direct_threads(
            amount=thread_scan_amount, thread_message_limit=1)),
        ("primary inbox", lambda: client.direct_threads(
            amount=thread_scan_amount, box="primary", thread_message_limit=1)),
        ("general inbox", lambda: client.direct_threads(
            amount=thread_scan_amount, box="general", thread_message_limit=1)),
        ("pending inbox", lambda: client.direct_pending_inbox(
            amount=thread_scan_amount)),
        ("spam inbox", lambda: client.direct_spam_inbox(
            amount=thread_scan_amount)),
    ]

    for label, load_threads in scan_sources:
        try:
            print(f"[*] {label} сканнердаж байна @{target_username}...")
            tid = scan_threads_for_user(
                load_threads(), target_user_id, target_username,
                allow_group_thread,
            )
            if tid:
                return tid
        except Exception as exc:
            errors.append(f"{label}: {exc}")

    detail = "; ".join(errors[-3:])
    hint = (
        "DM thread олдсонгүй. Чат inbox-д байгаа, username зөв эсэхийг шалгана уу."
    )
    if detail:
        hint = f"{hint} Алдаанууд: {detail}"
    raise RuntimeError(hint)


# ──────────────────────── Raw API fallback ────────────────────────


def fetch_messages_raw(client: Client, thread_id: str) -> list[dict]:
    messages: list[dict] = []
    cursor = None
    while True:
        try:
            params: dict[str, Any] = {
                "visual_message_return_type": "unseen",
                "limit": 20,
            }
            if cursor:
                params["cursor"] = cursor
            result = client.private_request(
                f"direct_v2/threads/{thread_id}/", params=params
            )
            thread_data = result.get("thread", {})
            items = thread_data.get("items", [])
            if not items:
                break
            for item in items:
                messages.append({
                    "id": item.get("item_id"),
                    "user_id": str(item.get("user_id", "")),
                    "text": item.get("text", ""),
                    "item_type": item.get("item_type", "unknown"),
                })
            if not thread_data.get("has_older"):
                break
            cursor = thread_data.get("oldest_cursor")
        except Exception as e:
            print(f"  [!] Raw API алдаа: {e}")
            break
    return messages


def unsend_message_raw(client: Client, thread_id: str, item_id: str) -> bool:
    data = client.with_default_data({})
    data.pop("_uid", None)
    data.pop("device_id", None)
    result = client.private_request(
        f"direct_v2/threads/{thread_id}/items/{item_id}/delete/",
        data=data,
    )
    return result.get("status") == "ok"


# ──────────────────── Delete with retry logic ────────────────────


def delete_messages_with_retry(
    client: Client,
    thread_id: str,
    own_messages: list[Any],
    *,
    use_raw: bool = False,
    min_delay: float = 0.0,
    max_delay: float = 0.0,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Мессежүүдийг retry логиктой устгана. (deleted, failed, skipped) буцаана."""
    if dry_run:
        for i, msg in enumerate(own_messages[:10], 1):
            print(f"  {i:>3}. {message_preview(msg)}")
        if len(own_messages) > 10:
            print(f"  ... нэмэлт {len(own_messages) - 10} мессеж")
        print("[*] Dry run — юу ч устгагдаагүй.")
        return 0, 0, 0

    total = len(own_messages)
    deleted = 0
    failed = 0
    skipped = 0
    consecutive_errors = 0

    for index, msg in enumerate(own_messages, 1):
        if use_raw:
            msg_id = msg["id"]
        else:
            msg_id = getattr(msg, "id", None)
            if not msg_id:
                failed += 1
                print(f"  [{index}/{total}] ID байхгүй мессеж — алгасав.")
                continue

        success = False
        for attempt in range(MAX_RETRIES):
            try:
                if use_raw:
                    unsend_message_raw(client, thread_id, msg_id)
                else:
                    client.direct_message_delete(thread_id, msg_id)

                deleted += 1
                consecutive_errors = 0
                success = True
                print(f"  [{index}/{total}] ✅ устгалаа: {message_preview(msg)}")
                break

            except Exception as exc:
                err_str = str(exc)

                if "403" in err_str:
                    skipped += 1
                    print(f"  [{index}/{total}] ⊘ алгасав (unsend болохгүй): "
                          f"{message_preview(msg)}")
                    break

                consecutive_errors += 1
                wait = min(10 * (attempt + 1), 60)
                print(f"  [{index}/{total}] ✗ алдаа ({attempt+1}/{MAX_RETRIES}): {exc}")

                if consecutive_errors >= 10:
                    print(f"  [!] Дараалсан 10 алдаа — 60с хүлээж байна...")
                    time.sleep(60)
                    consecutive_errors = 0
                else:
                    time.sleep(wait)

        if not success and not any(
            "403" in str(getattr(msg, "_last_err", ""))
            for _ in [None]
        ):
            if consecutive_errors > 0 and attempt == MAX_RETRIES - 1:
                failed += 1

        if success and index < total and max_delay > 0:
            delay = random.uniform(min_delay, max_delay)
            time.sleep(delay)

    return deleted, failed, skipped


# ──────────────── Unsend from a single thread ────────────────


def unsend_from_thread(
    client: Client,
    thread_id: str,
    thread_name: str,
    my_user_id: str,
    *,
    amount: int = 200,
    newest_first: bool = False,
    min_delay: float = 0.0,
    max_delay: float = 0.0,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Нэг thread дотроос мессеж устгана. (deleted, failed, skipped) буцаана."""
    print(f"\n{'='*55}")
    print(f"  '{thread_name}' чатын мессежийг татаж байна...")
    print(f"{'='*55}")

    use_raw = False
    messages = None

    for attempt in range(MAX_RETRIES):
        try:
            messages = client.direct_messages(thread_id, amount=amount)
            break
        except Exception as e:
            if "validation error" in str(e).lower():
                print(f"  [!] Pydantic алдаа — raw API руу шилжиж байна...")
                use_raw = True
                break
            wait = min(30 * (attempt + 1), 120)
            print(f"  [!] Мессеж татах алдаа ({attempt+1}/{MAX_RETRIES}): {e}")
            print(f"      {wait}с хүлээж байна...")
            time.sleep(wait)

    if use_raw:
        raw_msgs = fetch_messages_raw(client, thread_id)
        if not raw_msgs:
            print(f"  '{thread_name}' — мессеж олдсонгүй.")
            return 0, 0, 0
        own = [m for m in raw_msgs if m["user_id"] == my_user_id]
        print(f"  Нийт {len(raw_msgs)} мессежээс {len(own)} миний мессеж (raw API)")
        return delete_messages_with_retry(
            client, thread_id, own,
            use_raw=True, min_delay=min_delay, max_delay=max_delay, dry_run=dry_run,
        )

    if not messages:
        print(f"  '{thread_name}' — мессеж олдсонгүй.")
        return 0, 0, 0

    own = [
        m for m in messages
        if str(getattr(m, "user_id", "")) == my_user_id
        or getattr(m, "is_sent_by_viewer", False)
    ]

    if hasattr(own[0] if own else None, "timestamp"):
        own.sort(key=lambda m: m.timestamp, reverse=newest_first)

    if not own:
        print(f"  '{thread_name}' — миний мессеж олдсонгүй.")
        return 0, 0, 0

    print(f"  Нийт {len(messages)} мессежээс {len(own)} миний мессеж олдлоо.")
    return delete_messages_with_retry(
        client, thread_id, own,
        use_raw=False, min_delay=min_delay, max_delay=max_delay, dry_run=dry_run,
    )


# ──────────────── Interactive: all chats mode ────────────────


def run_interactive(
    client: Client,
    args: argparse.Namespace,
) -> int:
    my_user_id = str(client.user_id)
    max_threads = args.max_threads

    print(f"\n[*] Чатуудыг татаж байна (хамгийн ихдээ {max_threads})...")
    try:
        threads = client.direct_threads(amount=max_threads)
    except Exception as e:
        print(f"[!] Чат татахад алдаа: {e}")
        return 1

    if not threads:
        print("[!] Чат олдсонгүй.")
        return 0

    print(f"\n{'='*55}")
    print(f"  Нийт {len(threads)} чат олдлоо:")
    print(f"{'='*55}")
    for i, thread in enumerate(threads, 1):
        name = get_thread_display_name(thread)
        msg_info = ""
        msgs = value_from(thread, "messages", [])
        if msgs:
            msg_info = f" ({len(msgs)} мессеж ачааллаа)"
        print(f"  {i}. {name}{msg_info}")

    print(f"\n  0. БҮГДИЙГ УСТГАХ (бүх чатын миний мессеж)")
    print(f"{'='*55}")

    choice = input("\n👉 Аль чатаас устгах вэ? (дугаар, эсвэл 0=бүгд): ").strip()

    grand_deleted = 0
    grand_failed = 0
    grand_skipped = 0

    if choice == "0":
        if not args.yes:
            confirm = input("[!] БҮГДИЙГ УСТГАХ гэж байна. Итгэлтэй юу? (y/n): ").strip().lower()
            if confirm != "y":
                print("Цуцаллаа.")
                return 0

        for thread in threads:
            name = get_thread_display_name(thread)
            tid = thread_id_from(thread)
            if not tid:
                continue
            d, f, s = unsend_from_thread(
                client, tid, name, my_user_id,
                amount=args.amount, newest_first=args.newest_first,
                min_delay=args.min_delay, max_delay=args.max_delay,
                dry_run=args.dry_run,
            )
            grand_deleted += d
            grand_failed += f
            grand_skipped += s
    else:
        try:
            indices = [int(x.strip()) for x in choice.split(",")]
        except ValueError:
            print("[!] Буруу оролт.")
            return 1

        for idx in indices:
            if idx < 1 or idx > len(threads):
                print(f"[!] {idx} буруу дугаар — алгасав.")
                continue
            thread = threads[idx - 1]
            name = get_thread_display_name(thread)
            tid = thread_id_from(thread)
            if not tid:
                continue
            d, f, s = unsend_from_thread(
                client, tid, name, my_user_id,
                amount=args.amount, newest_first=args.newest_first,
                min_delay=args.min_delay, max_delay=args.max_delay,
                dry_run=args.dry_run,
            )
            grand_deleted += d
            grand_failed += f
            grand_skipped += s

    print(f"\n{'='*55}")
    print(f"[+] ДУУСЛАА! Устгасан: {grand_deleted} | Алдаа: {grand_failed} | Алгассан: {grand_skipped}")
    print(f"{'='*55}")
    return 0 if grand_failed == 0 else 1


# ──────────────── Single target mode ────────────────


def run_single_target(
    client: Client,
    args: argparse.Namespace,
) -> int:
    target_username = args.target_username.lstrip("@")
    my_user_id = str(client.user_id)

    target_user_id = client.user_id_from_username(target_username)
    thread_id = find_thread_id(
        client, str(target_user_id), target_username,
        args.thread_scan_amount, args.allow_group_thread,
    )
    print(f"[+] Thread олдлоо: {thread_id} (@{target_username})")

    d, f, s = unsend_from_thread(
        client, thread_id, f"@{target_username}", my_user_id,
        amount=args.amount, newest_first=args.newest_first,
        min_delay=args.min_delay, max_delay=args.max_delay,
        dry_run=args.dry_run,
    )

    client.dump_settings(Path(args.session_file))
    print(f"\n[+] Дууслаа. Устгасан: {d} | Алдаа: {f} | Алгассан: {s}")
    return 0 if f == 0 else 1


# ──────────────────────────── Main ────────────────────────────


def main() -> int:
    args = parse_args()

    if args.no_delay:
        args.min_delay = 0.0
        args.max_delay = 0.0

    if args.min_delay < 0 or args.max_delay < 0 or args.min_delay > args.max_delay:
        print("--min-delay, --max-delay: non-negative, min <= max.")
        return 2
    if args.amount < 0 or args.thread_scan_amount < 0:
        print("--amount, --thread-scan-amount: 0 эсвэл түүнээс их байх ёстой.")
        return 2

    username = args.username or input("Instagram username: ").strip()
    password = args.password or getpass.getpass("Instagram password: ")
    if not username or not password:
        print("Username болон password шаардлагатай.")
        return 2

    session_file = Path(args.session_file)
    client = do_login(username, password, args.verification_code, session_file)

    if args.all_chats or args.target_username is None:
        return run_interactive(client, args)
    else:
        return run_single_target(client, args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nЦуцаллаа.")
        raise SystemExit(130)
