# Instagram DM Unsend

Өөрийн илгээсэн Instagram DM мессежүүдийг unsend хийдэг CLI tool. `instagrapi` ашигладаг.

## Онцлогууд

- Нэг чатаас өөрийн мессежүүдийг username-аар олж unsend хийх
- Бүх чат дундаас сонгон unsend хийх interactive горим
- Primary, General, Pending, Spam inbox-уудыг scan хийж thread олох
- Pydantic validation алдаа гарвал raw API руу fallback хийх
- Мессеж бүр дээр retry логик ашиглах
- `403` unsend боломжгүй мессежүүдийг алгасах
- `--dry-run` горимоор устгахгүйгээр шалгах

## Repository-г татах

```bash
git clone https://github.com/rinchynn/ig-unsend.git
cd ig-unsend
```

## Суулгах

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Тохиргоо

Environment variable-аар Instagram нэвтрэх мэдээллээ өгч болно:

```bash
export IG_USERNAME="таны_instagram_нэр"
export IG_PASSWORD="таны_нууц_үг"
```

Хэрэв environment variable тохируулаагүй бол скрипт ажиллах үед terminal дээр асууна.

## Ашиглах арга

### 1) Нэг чатаас мессеж unsend хийх

```bash
# Эхлээд dry run хийж шалгах
python ig_unsend.py some_username --dry-run

# Confirmation авч устгах
python ig_unsend.py some_username

# Бүх мессежийг шууд устгах
python ig_unsend.py some_username --amount 0 --yes

# 2FA код дамжуулах
python ig_unsend.py some_username --verification-code 123456

# Thread-ийг бүх inbox-с scan хийж хайх
python ig_unsend.py some_username --thread-scan-amount 0

# Шинэ мессежээс эхэлж устгах
python ig_unsend.py some_username --newest-first

# Устгалтын хооронд delay тохируулах
python ig_unsend.py some_username --min-delay 2 --max-delay 5
```

### 2) Бүх чатаас сонгон устгах (interactive)

```bash
# Бүх чатыг жагсаана
python ig_unsend.py --all-chats

# Эсвэл username-гүйгээр шууд interactive горимд орно
python ig_unsend.py
```

Interactive горимд:

- Чатууд дугаартай жагсаагдана
- Дугаараар сонгож болно (`1` эсвэл `1,3,5` гэх мэт)
- `0` оруулбал бүх чатын өөрийн мессежүүдийг unsend хийнэ

## CLI аргументууд

| Argument | Тайлбар | Default |
|----------|---------|---------|
| `target_username` | Чатын username (оруулахгүй бол interactive горим) | — |
| `--all-chats` | Interactive горим руу шууд шилжинэ | `false` |
| `--amount N` | Thread-ээс fetch хийх мессежийн тоо (`0` = бүгд) | `200` |
| `--thread-scan-amount N` | Thread хайхад scan хийх inbox тоо (`0` = бүгд) | `0` |
| `--allow-group-thread` | Group thread-ээс устгах зөвшөөрөх | `false` |
| `--max-threads N` | Interactive горимд татах чатын тоо | `100` |
| `--min-delay N` | Устгалт хоорондын minimum секунд | `0` |
| `--max-delay N` | Устгалт хоорондын maximum секунд | `0` |
| `--no-delay` | Delay бүрмөсөн унтраах | `false` |
| `--newest-first` | Шинэ мессежээс эхлэн устгах | `false` |
| `--dry-run` | Устгахгүй, зөвхөн preview хийнэ | `false` |
| `--yes` | Confirmation prompt алгасна | `false` |
| `--session-file PATH` | Session файлын зам | `session.json` |
| `--verification-code CODE` | 2FA баталгаажуулах код | — |

## Файлын бүтэц

```text
ig-unsend/
├── ig_unsend.py      # Үндсэн CLI скрипт
├── requirements.txt  # Хамааралтай сангууд
└── .gitignore
```

## Анхаарах зүйлс

- `session.json` автоматаар үүсч дахин ашиглагдаж болно — GitHub руу push хийж болохгүй
- Instagram challenge эсвэл limit гарвал official app дээр баталгаажуулаад дахин оролдоно
- Inbox-оос chat delete хийсэн бол thread олдохгүй байж магадгүй
- Энэ нь unofficial API ашигладаг тул account дээр limit, challenge, эсвэл block үүсэх эрсдэлтэй

## Санал болгох workflow

Аюулгүй ашиглахын тулд эхлээд дараах дарааллаар туршаарай:

```bash
python ig_unsend.py some_username --dry-run
python ig_unsend.py some_username
```

## Disclaimer

Энэ tool-ийг зөвхөн өөрийн аккаунт дээр, өөрийн илгээсэн мессежүүд дээр хариуцлагатай ашиглана уу. Instagram-ийн rate limit, challenge, болон platform policy-г анхаарч хэрэглээрэй.
