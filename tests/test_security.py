import io

from app import sanitize_settings


def test_path_traversal_download(client):
    r1 = client.get("/download?path=../../etc/passwd")
    assert r1.status_code == 403

    r2 = client.get("/download?path=C:\\Windows\\win.ini")
    assert r2.status_code == 403

    r3 = client.get("/download?path=")
    assert r3.status_code == 400


def test_path_traversal_delete(client):
    r1 = client.post("/delete-file", json={"path": "../../etc/passwd"})
    assert r1.status_code == 403

    r2 = client.post("/delete-file", json={"path": "C:\\Windows\\System32\\calc.exe"})
    assert r2.status_code == 403

    r3 = client.post("/delete-file", json={})
    assert r3.status_code == 400


def test_path_traversal_probe(client):
    r1 = client.post("/probe", json={"path": "../../etc/passwd"})
    assert r1.status_code == 403

    r2 = client.post("/probe", json={"path": "C:\\Windows\\win.ini"})
    assert r2.status_code == 403


def test_path_traversal_process(client):
    # Reject process when file is outside videos dir
    r = client.post("/process", json={
        "files": ["../../etc/shadow"],
        "settings": {}
    })
    assert r.status_code == 400
    assert "Access denied" in r.json.get("error", "")


def test_path_traversal_slideshow(client):
    # Reject slideshow when image is outside images dir
    r = client.post("/slideshow", json={
        "files": ["../../sensitive.png"],
        "settings": {}
    })
    assert r.status_code == 400
    assert "Access denied" in r.json.get("error", "")


def test_upload_extension_allowlist(client):
    # Try uploading an unauthorized file into videos
    data = {"files": (io.BytesIO(b"malicious script"), "exploit.sh")}
    r = client.post("/upload/videos", data=data, content_type="multipart/form-data")
    assert r.status_code == 400
    assert "unsupported extension" in r.json.get("error", "")

    # Try uploading non-audio into audio
    data = {"files": (io.BytesIO(b"fake mp4"), "video.mp4")}
    r = client.post("/upload/audio", data=data, content_type="multipart/form-data")
    assert r.status_code == 400


def test_sanitize_settings_clamping():
    raw = {
        "logo_size": -50,
        "logo_opacity": 2.5,
        "logo_margin": 9999,
        "fps": 500,
        "img_duration": 0.05,
        "transition_duration": 15.0,
        "quality": "super_extreme",
        "logo_position": "nowhere",
        "orientation": "diagonal",
        "audio_mode": "destroy",
        "transition": "unsupported_magic",
        "transitions": ["wipeleft", "unknown_fx"],
        "trim_segments": [{"start": "00:00:20", "end": "00:00:10"}],  # end <= start
    }
    s = sanitize_settings(raw)

    assert s["logo_size"] == 10
    assert s["logo_opacity"] == 1.0
    assert s["logo_margin"] == 500
    assert s["fps"] == 120
    assert s["img_duration"] == 0.1
    assert s["quality"] == "medium"
    assert s["logo_position"] == "top_right"
    assert s["orientation"] == "landscape"
    assert s["audio_mode"] == "keep"
    assert s["transition"] == "fade"
    assert s["transitions"] == ["wipeleft", "fade"]
    assert s["trim_segments"] == []  # invalid end <= start rejected


def test_csrf_header_protection(client):
    # Same origin or empty origin is allowed
    client.post("/probe", json={"path": "dummy"}, headers={"Origin": "http://localhost"})
    # It might fail with 400 or 403 depending on host header, but let's test external origin
    r2 = client.post("/probe", json={"path": "dummy"}, headers={"Origin": "http://malicious-site.com"})
    assert r2.status_code == 403


def test_security_headers(client):
    r = client.get("/")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("Referrer-Policy") == "no-referrer"
    assert r.headers.get("X-Frame-Options") == "DENY"
