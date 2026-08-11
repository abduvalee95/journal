from datetime import datetime, date
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Bishkek")

MONTHS_UZ = [
    "январ","феврал","март","апрел","май","июн",
    "июл","август","сентябр","октябр","ноябр","декабр"
]

def bishkek_now() -> datetime:
    return datetime.now(TZ)

def today() -> str:
    return bishkek_now().date().isoformat()

def weekday() -> int:
    return bishkek_now().isoweekday()   # 1=Mon, 6=Sat

def format_date_uz(d: str) -> str:
    dt = date.fromisoformat(d)
    return f"{dt.day} {MONTHS_UZ[dt.month - 1]} {dt.year}"
