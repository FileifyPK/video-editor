import json


def test_index_route(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    assert "Video Editor" in html
    assert "topbar-title" in html
    assert "app-icon" in html


def test_health_route(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json
    assert data.get("status") == "ok"
    assert "version" in data
    assert "ffmpeg" in data


def test_ffmpeg_check_route(client):
    r = client.get("/ffmpeg-check")
    assert r.status_code == 200
    data = r.json
    assert "available" in data


def test_transitions_route(client):
    r = client.get("/transitions")
    assert r.status_code == 200
    transitions = r.json
    assert isinstance(transitions, dict)
    assert len(transitions) == 36
    assert "fade" in transitions
    assert "wipeleft" in transitions


def test_files_route(client, test_env):
    # Empty folder
    r = client.get("/files/videos")
    assert r.status_code == 200
    assert r.json == {"files": []}

    # Invalid folder
    r_bad = client.get("/files/nonexistent")
    assert r_bad.status_code == 200
    assert r_bad.json == {"files": []}


def test_job_not_found(client):
    r = client.get("/job/nonexistent_id_123")
    assert r.status_code == 404


def test_jobs_list(client):
    r = client.get("/jobs")
    assert r.status_code == 200
    assert "jobs" in r.json
