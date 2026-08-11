from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

TZ = ZoneInfo("Asia/Bishkek")

def _mock(dt_str):
    return datetime.fromisoformat(dt_str).replace(tzinfo=TZ)

def test_weekday_monday():
    with patch("app.utils.localtime.bishkek_now", return_value=_mock("2026-08-10T12:00:00")):
        from app.utils.localtime import weekday
        assert weekday() == 1

def test_weekday_saturday():
    with patch("app.utils.localtime.bishkek_now", return_value=_mock("2026-08-15T12:00:00")):
        from app.utils.localtime import weekday
        assert weekday() == 6

def test_today_returns_iso():
    with patch("app.utils.localtime.bishkek_now", return_value=_mock("2026-08-10T12:00:00")):
        from app.utils.localtime import today
        assert today() == "2026-08-10"

def test_format_date_uz():
    from app.utils.localtime import format_date_uz
    assert format_date_uz("2026-08-11") == "11 август 2026"
    assert format_date_uz("2026-01-01") == "1 январ 2026"
