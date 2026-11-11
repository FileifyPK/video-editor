from pathlib import Path
import pytest
from app import ts_to_secs, fmt_size, fmt_dur, safe_name, resolve_safe


def test_ts_to_secs():
    assert ts_to_secs("01:02:03") == 3723.0
    assert ts_to_secs("02:03") == 123.0
    assert ts_to_secs("12.5") == 12.5
    assert ts_to_secs("") == 0.0
    assert ts_to_secs("garbage") == 0.0
    assert ts_to_secs(None) == 0.0
    assert ts_to_secs("00:00:15.5") == 15.5


def test_fmt_size():
    assert fmt_size(500) == "500.0 B"
    assert fmt_size(1024) == "1.0 KB"
    assert fmt_size(1024 * 1024) == "1.0 MB"
    assert fmt_size(1024 * 1024 * 1024) == "1.0 GB"
    assert fmt_size(1024 * 1024 * 1024 * 1024) == "1.00 TB"


def test_fmt_dur():
    assert fmt_dur(45) == "0:45"
    assert fmt_dur(125) == "2:05"
    assert fmt_dur(3665) == "1:01:05"
    assert fmt_dur(0) == "0:00"


def test_safe_name():
    assert safe_name("").startswith("file_")
    assert safe_name("simple.mp4") == "simple.mp4"
    assert safe_name("../../etc/passwd") == "passwd"
    assert safe_name("..\\windows\\system32.dll") == "system32.dll"
    # Unicode support: Urdu, Arabic, Chinese
    assert "اردو" in safe_name("اردو_ویڈیو.mp4")
    assert "العربية" in safe_name("العربية.mp4")
    assert "中文" in safe_name("中文视频.mp4")
    # Windows reserved names
    assert safe_name("CON.txt") == "_CON.txt"
    assert safe_name("aux.mp4") == "_aux.mp4"
    assert safe_name("NUL") == "_NUL"


def test_resolve_safe(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    child = root / "valid.txt"
    child.write_text("ok")

    # Valid resolution
    res = resolve_safe(str(child), root)
    assert res == child.resolve()

    # Outside traversal
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")

    with pytest.raises(ValueError):
        resolve_safe(str(outside), root)

    with pytest.raises(ValueError):
        resolve_safe("../outside.txt", root)
