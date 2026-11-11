import shutil
import tempfile
from pathlib import Path
import pytest
import app as app_module


@pytest.fixture
def test_env(monkeypatch):
    """Create isolated temporary environment for uploads, outputs, and temp files."""
    temp_dir = Path(tempfile.mkdtemp(prefix="ve_test_"))
    upload_dir = temp_dir / "uploads"
    output_dir = temp_dir / "outputs"
    work_temp_dir = temp_dir / "temp"

    videos_dir = upload_dir / "videos"
    logo_dir = upload_dir / "logo"
    intro_dir = upload_dir / "intro"
    outro_dir = upload_dir / "outro"
    mid_dir = upload_dir / "mid"
    audio_dir = upload_dir / "audio"
    images_dir = upload_dir / "images"

    for d in [videos_dir, logo_dir, intro_dir, outro_dir, mid_dir, audio_dir, images_dir, output_dir, work_temp_dir]:
        d.mkdir(parents=True, exist_ok=True)

    folder_map = {
        "videos": videos_dir,
        "logo": logo_dir,
        "intro": intro_dir,
        "outro": outro_dir,
        "mid": mid_dir,
        "audio": audio_dir,
        "images": images_dir,
    }

    monkeypatch.setattr(app_module, "BASE", temp_dir)
    monkeypatch.setattr(app_module, "UPLOAD", upload_dir)
    monkeypatch.setattr(app_module, "OUTPUT", output_dir)
    monkeypatch.setattr(app_module, "TEMP", work_temp_dir)
    monkeypatch.setattr(app_module, "VIDEOS_DIR", videos_dir)
    monkeypatch.setattr(app_module, "LOGO_DIR", logo_dir)
    monkeypatch.setattr(app_module, "INTRO_DIR", intro_dir)
    monkeypatch.setattr(app_module, "OUTRO_DIR", outro_dir)
    monkeypatch.setattr(app_module, "MID_DIR", mid_dir)
    monkeypatch.setattr(app_module, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(app_module, "IMAGES_DIR", images_dir)
    monkeypatch.setattr(app_module, "FOLDER_MAP", folder_map)

    yield {
        "root": temp_dir,
        "upload": upload_dir,
        "output": output_dir,
        "temp": work_temp_dir,
        "videos": videos_dir,
        "logo": logo_dir,
        "images": images_dir,
        "audio": audio_dir,
    }

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def client(test_env):
    """Flask test client."""
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c
