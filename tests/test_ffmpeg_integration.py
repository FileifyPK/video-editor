import subprocess
from pathlib import Path

import pytest

from app import _lock, ffmpeg_ok, jobs, probe, process_job, process_slideshow, uid


@pytest.mark.skipif(not ffmpeg_ok(), reason="FFmpeg executable is not available on PATH")
def test_ffmpeg_slideshow_integration(test_env):
    """Test generating a short slideshow from synthetic images with FFmpeg."""
    images_dir = test_env["images"]
    test_env["output"]

    # Generate 2 test images using ffmpeg
    img1 = images_dir / "test1.png"
    img2 = images_dir / "test2.png"

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1",
        "-frames:v", "1", str(img1)
    ], check=True, capture_output=True)

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1",
        "-frames:v", "1", str(img2)
    ], check=True, capture_output=True)

    jid = f"test_ss_{uid(6)}"
    with _lock:
        jobs[jid] = {
            "status": "queued",
            "progress": 0,
            "logs": [],
            "outputs": [],
            "files": [str(img1), str(img2)],
            "settings": {
                "fps": 15,
                "img_duration": 1.0,
                "transition_duration": 0.4,
                "transition": "fade",
                "orientation": "landscape",
                "output_name": "test_slideshow_out",
                "quality": "fast",
                "logo_enabled": False,
            },
            "created": 0,
            "type": "slideshow"
        }

    process_slideshow(jid)

    with _lock:
        job = jobs[jid]

    assert job["status"] == "done"
    assert len(job["outputs"]) == 1

    out_file = Path(job["outputs"][0])
    assert out_file.exists()
    assert out_file.stat().st_size > 0

    info = probe(out_file)
    assert info["duration"] > 0
    assert info["width"] == 1920
    assert info["height"] == 1080


@pytest.mark.skipif(not ffmpeg_ok(), reason="FFmpeg executable is not available on PATH")
def test_ffmpeg_video_trim_integration(test_env):
    """Test trimming a synthetic video."""
    videos_dir = test_env["videos"]
    vid_in = videos_dir / "synthetic_vid.mp4"

    # Generate a 4-second test video
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=25",
        "-f", "lavfi", "-i", "sine=duration=4:frequency=440",
        "-c:v", "libx264", "-c:a", "aac", str(vid_in)
    ], check=True, capture_output=True)

    jid = f"test_vid_{uid(6)}"
    with _lock:
        jobs[jid] = {
            "status": "queued",
            "progress": 0,
            "logs": [],
            "outputs": [],
            "files": [str(vid_in)],
            "settings": {
                "logo_enabled": False,
                "audio_mode": "keep",
                "quality": "fast",
                "use_gpu": False,
                "trim_segments": [{"start": "00:00:01", "end": "00:00:03"}],
            },
            "created": 0,
            "type": "video"
        }

    process_job(jid)

    with _lock:
        job = jobs[jid]

    assert job["status"] == "done"
    assert len(job["outputs"]) == 1

    out_file = Path(job["outputs"][0])
    assert out_file.exists()
    assert out_file.stat().st_size > 0

    info = probe(out_file)
    assert info["duration"] > 0
    assert info["has_audio"] is True
