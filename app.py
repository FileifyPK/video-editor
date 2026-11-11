"""
Video Editor
============================================
Batch video processing and slideshow maker, powered by FFmpeg.

Features:
  • Batch video processing (trim, logo, audio, intro/outro/mid-roll)
  • Image → Slideshow video with transition effects
  • Both portrait (9:16) and landscape (16:9) output
  • Real-time progress + live log polling
  • Job queue with cancel support
  • File management (upload, list, delete)
  • Download processed outputs
"""

import os
import re
import uuid
import json
import time
import shutil
import threading
import subprocess
import logging
from pathlib import Path
from typing import Union, List, Dict, Any, Optional
from urllib.parse import urlparse
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

# ── Product Identity ──────────────────────────────────────────────────────────
APP_NAME = "Video Editor"
APP_TAGLINE = "Batch video processing and slideshow maker, powered by FFmpeg"
REPO_SLUG = "video-editor"
ENV_PREFIX = "VIDEO_EDITOR_"
COPYRIGHT = "Video Editor contributors"
__version__ = "1.0.0"

# ── Logging ───────────────────────────────────────────────────────────────────
logger = logging.getLogger("video_editor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ── Configuration ─────────────────────────────────────────────────────────────
HOST = os.environ.get(f"{ENV_PREFIX}HOST", "127.0.0.1")
PORT = int(os.environ.get(f"{ENV_PREFIX}PORT", "5000"))
MAX_UPLOAD_GB = float(os.environ.get(f"{ENV_PREFIX}MAX_UPLOAD_GB", "5"))
DEBUG = os.environ.get(f"{ENV_PREFIX}DEBUG", "0") == "1"
JOB_TTL_HOURS = float(os.environ.get(f"{ENV_PREFIX}JOB_TTL_HOURS", "6"))

# ── App ───────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(MAX_UPLOAD_GB * 1024 * 1024 * 1024)

BASE = Path(__file__).parent.resolve()
UPLOAD = BASE / "uploads"
OUTPUT = BASE / "outputs"
TEMP = BASE / "temp"

VIDEOS_DIR = UPLOAD / "videos"
LOGO_DIR = UPLOAD / "logo"
INTRO_DIR = UPLOAD / "intro"
OUTRO_DIR = UPLOAD / "outro"
MID_DIR = UPLOAD / "mid"
AUDIO_DIR = UPLOAD / "audio"
IMAGES_DIR = UPLOAD / "images"

for d in [VIDEOS_DIR, LOGO_DIR, INTRO_DIR, OUTRO_DIR,
          MID_DIR, AUDIO_DIR, IMAGES_DIR, OUTPUT, TEMP]:
    d.mkdir(parents=True, exist_ok=True)

jobs: Dict[str, Any] = {}
_lock = threading.Lock()

ALLOWED_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".flv"}
ALLOWED_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
ALLOWED_AUDIO = {".mp3", ".wav", ".aac", ".m4a", ".ogg", ".flac"}

FOLDER_MAP = {
    "videos": VIDEOS_DIR,
    "logo": LOGO_DIR,
    "intro": INTRO_DIR,
    "outro": OUTRO_DIR,
    "mid": MID_DIR,
    "audio": AUDIO_DIR,
    "images": IMAGES_DIR,
}

FOLDER_ALLOWLIST = {
    "videos": ALLOWED_VIDEO,
    "intro": ALLOWED_VIDEO,
    "outro": ALLOWED_VIDEO,
    "mid": ALLOWED_VIDEO,
    "logo": ALLOWED_IMAGE,
    "images": ALLOWED_IMAGE,
    "audio": ALLOWED_AUDIO,
}

# Transition effect definitions for FFmpeg xfade filter
# 36 supported transitions
TRANSITIONS: Dict[str, str] = {
    "fade": "Fade",
    "wipeleft": "Wipe Left",
    "wiperight": "Wipe Right",
    "wipeup": "Wipe Up",
    "wipedown": "Wipe Down",
    "slideleft": "Slide Left",
    "slideright": "Slide Right",
    "slideup": "Slide Up",
    "slidedown": "Slide Down",
    "circlecrop": "Circle Crop",
    "rectcrop": "Rect Crop",
    "distance": "Distance",
    "fadeblack": "Fade to Black",
    "fadewhite": "Fade to White",
    "radial": "Radial",
    "smoothleft": "Smooth Left",
    "smoothright": "Smooth Right",
    "smoothup": "Smooth Up",
    "smoothdown": "Smooth Down",
    "diagtl": "Diagonal TL",
    "diagtr": "Diagonal TR",
    "diagbl": "Diagonal BL",
    "diagbr": "Diagonal BR",
    "hlslice": "H Slice",
    "hrslice": "H Reverse Slice",
    "vuslice": "V Slice",
    "vdslice": "V Down Slice",
    "dissolve": "Dissolve",
    "pixelize": "Pixelize",
    "squeezeh": "Squeeze H",
    "squeezev": "Squeeze V",
    "zoomin": "Zoom In",
    "horzopen": "Horz Open",
    "horzclose": "Horz Close",
    "vertopen": "Vert Open",
    "vertclose": "Vert Close",
}


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITIES & SECURITY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def uid(n: int = 10) -> str:
    """Generate a random alphanumeric identifier."""
    return uuid.uuid4().hex[:n]


def safe_name(name: str) -> str:
    """Sanitize filename preserving Unicode while preventing traversal and reserved device names."""
    if not name:
        return f"file_{uid()}"
    base = Path(name).name
    # Replace illegal/control characters
    cleaned = re.sub(r'[\x00-\x1f\x7f<>:"/\\|?*]', "_", base).strip(". ")
    # Protect Windows reserved names
    stem = Path(cleaned).stem.upper()
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if stem in reserved:
        cleaned = f"_{cleaned}"
    if not cleaned or cleaned == ".":
        return f"file_{uid()}"
    return cleaned[:200]


def resolve_safe(user_path: Union[str, Path], *allowed_roots: Path) -> Path:
    """Resolve user_path and guarantee it lives inside one of allowed_roots.
    Raises ValueError otherwise. Handles symlinks, '..', absolute paths, Windows drive letters."""
    p = Path(user_path).resolve()
    for root in allowed_roots:
        root_res = root.resolve()
        try:
            if hasattr(p, "is_relative_to"):
                if p.is_relative_to(root_res):
                    return p
            else:
                p.relative_to(root_res)
                return p
        except (ValueError, AttributeError):
            continue
    raise ValueError(f"Access denied: path '{user_path}' is outside permitted directories.")


def fmt_size(b: Union[int, float]) -> str:
    """Format bytes into human-readable string."""
    b = float(b)
    for u in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.2f} TB"


def fmt_dur(s: Union[int, float]) -> str:
    """Format duration in seconds to mm:ss or hh:mm:ss."""
    s = int(s)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def ts_to_secs(ts: Any) -> float:
    """Convert timestamp string (hh:mm:ss, mm:ss, or seconds) to float seconds."""
    ts = str(ts).strip()
    if not ts:
        return 0.0
    if ":" in ts:
        parts = [float(p) for p in ts.split(":")]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
    try:
        return float(ts)
    except Exception:
        return 0.0


def ffmpeg_ok() -> bool:
    """Check if ffmpeg executable is available in PATH."""
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def ffmpeg_version() -> str:
    """Return the first line of ffmpeg -version output."""
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        return r.stdout.split("\n")[0]
    except Exception:
        return "unknown"


def probe(path: Union[str, Path]) -> Dict[str, Any]:
    """Inspect media file using ffprobe and return metadata dict."""
    info = {"duration": 0.0, "width": 0, "height": 0, "fps": 0.0,
            "codec": "", "has_audio": False, "size": 0}
    try:
        p = Path(path)
        info["size"] = p.stat().st_size
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json",
               "-show_streams", "-show_format", p.as_posix()]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(r.stdout)
        info["duration"] = float(data.get("format", {}).get("duration", 0))
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                info["width"] = s.get("width", 0)
                info["height"] = s.get("height", 0)
                info["codec"] = s.get("codec_name", "")
                try:
                    num, den = s.get("r_frame_rate", "0/1").split("/")
                    info["fps"] = round(float(num) / float(den), 2)
                except Exception:
                    pass
            if s.get("codec_type") == "audio":
                info["has_audio"] = True
    except Exception as e:
        logger.debug(f"Probe exception for {path}: {e}")
    return info


def purge_stale_temp(max_age_hours: float = 24.0) -> None:
    """Purge intermediate files in temp/ older than max_age_hours."""
    now = time.time()
    cutoff = now - (max_age_hours * 3600)
    try:
        for f in TEMP.iterdir():
            if f.is_file() and f.name != ".gitkeep":
                try:
                    if f.stat().st_mtime < cutoff:
                        f.unlink(missing_ok=True)
                except Exception:
                    pass
    except Exception:
        pass


def prune_jobs() -> None:
    """Drop finished, errored, or cancelled jobs older than JOB_TTL_HOURS."""
    now = time.time()
    cutoff = now - (JOB_TTL_HOURS * 3600)
    with _lock:
        to_del = [jid for jid, j in jobs.items()
                  if j.get("created", 0) < cutoff and j.get("status") in {"done", "error", "cancelled"}]
        for jid in to_del:
            del jobs[jid]


def jlog(jid: str, msg: str, level: str = "info") -> None:
    """Append a log entry to the job log with capped history."""
    ts = time.strftime("%H:%M:%S")
    with _lock:
        if jid in jobs:
            logs = jobs[jid]["logs"]
            logs.append({"ts": ts, "msg": msg, "level": level})
            if len(logs) > 2000:
                jobs[jid]["logs"] = logs[-2000:]


def jprog(jid: str, pct: Union[int, float], status: Optional[str] = None,
          current_item: Optional[int] = None, total_items: Optional[int] = None,
          item_pct: Optional[Union[int, float]] = None) -> None:
    """Update progress percentage, ETA, and status of a job."""
    with _lock:
        if jid in jobs:
            jobs[jid]["progress"] = min(max(int(pct), 0), 100)
            if status:
                jobs[jid]["status"] = status
            if current_item is not None:
                jobs[jid]["current_item"] = current_item
            if total_items is not None:
                jobs[jid]["total_items"] = total_items
            if item_pct is not None:
                jobs[jid]["item_pct"] = min(max(int(item_pct), 0), 100)

            if "start_time" not in jobs[jid]:
                jobs[jid]["start_time"] = time.time()

            elapsed = time.time() - jobs[jid]["start_time"]
            if pct > 0:
                total_est = elapsed / (pct / 100.0)
                jobs[jid]["eta"] = max(0, int(total_est - elapsed))
            else:
                jobs[jid]["eta"] = None


def jdone(jid: str, outputs: List[str], msg: str = "Done") -> None:
    """Mark job as complete with outputs."""
    with _lock:
        if jid in jobs:
            jobs[jid].update({
                "status": "done",
                "progress": 100,
                "outputs": outputs,
                "item_pct": 100,
                "eta": 0
            })
    jlog(jid, f"✓ {msg}", "success")


def jerr(jid: str, msg: str) -> None:
    """Mark job as failed with error message."""
    with _lock:
        if jid in jobs:
            jobs[jid]["status"] = "error"
            jobs[jid]["eta"] = None
    jlog(jid, f"✗ {msg}", "error")


def run_ffmpeg(cmd: List[Any], jid: str, timeout: int = 7200,
               is_item: bool = False, base_pct: Optional[float] = None,
               weight_pct: Optional[float] = None) -> bool:
    """Run FFmpeg subprocess with live output parsing and cancel support."""
    jlog(jid, "CMD: " + " ".join(str(c) for c in cmd))
    try:
        with _lock:
            if jid in jobs and jobs[jid].get("status") == "cancelled":
                return False

        proc = subprocess.Popen(
            [str(c) for c in cmd],
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            universal_newlines=True
        )

        with _lock:
            if jid in jobs:
                jobs[jid]["proc"] = proc

        dur_re = re.compile(r"Duration:\s+(\d+):(\d+):(\d+\.\d+)")
        time_re = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
        total_s = None

        if proc.stderr:
            for line in proc.stderr:
                line = line.rstrip()
                with _lock:
                    if jid in jobs and jobs[jid].get("status") == "cancelled":
                        proc.terminate()
                        break
                if not total_s:
                    m = dur_re.search(line)
                    if m:
                        h, mn, s = m.groups()
                        total_s = int(h) * 3600 + int(mn) * 60 + float(s)
                m = time_re.search(line)
                if m and total_s and total_s > 0:
                    h, mn, s = m.groups()
                    cur = int(h) * 3600 + int(mn) * 60 + float(s)
                    pct = min(int(cur / total_s * 100), 100)
                    if is_item:
                        with _lock:
                            if jid in jobs:
                                jobs[jid]["item_pct"] = pct
                                if base_pct is not None and weight_pct is not None:
                                    overall = base_pct + (pct / 100.0) * weight_pct
                                    jobs[jid]["progress"] = min(max(int(overall), 0), 100)
                                    start_t = jobs[jid].get("start_time")
                                    if start_t and overall > 0:
                                        elapsed = time.time() - start_t
                                        total_est = elapsed / (overall / 100.0)
                                        jobs[jid]["eta"] = max(0, int(total_est - elapsed))
                    else:
                        jprog(jid, min(int(cur / total_s * 88), 88))
                if any(kw in line.lower() for kw in ("error", "invalid data", "no such file")):
                    jlog(jid, line, "warn")

        proc.wait(timeout=timeout)

        with _lock:
            if jid in jobs and "proc" in jobs[jid]:
                del jobs[jid]["proc"]

        return proc.returncode == 0
    except Exception as e:
        logger.error(f"FFmpeg exception for job {jid}: {e}")
        jlog(jid, f"FFmpeg exception: {e}", "error")
        return False


def reencode(src: Union[str, Path], dst: Union[str, Path], jid: str,
             crf: str = "20", is_item: bool = False,
             base_pct: Optional[float] = None, weight_pct: Optional[float] = None) -> bool:
    """Reencode media file to standardized h264/aac mp4 format."""
    cmd = [
        "ffmpeg", "-y", "-i", Path(src).as_posix(),
        "-c:v", "libx264", "-preset", "fast", "-crf", str(crf),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart", Path(dst).as_posix()
    ]
    return run_ffmpeg(cmd, jid, is_item=is_item, base_pct=base_pct, weight_pct=weight_pct)


def concat_videos(paths: List[Union[str, Path]], out: Union[str, Path], jid: str) -> bool:
    """Concatenate multiple videos with identical stream params using ffmpeg concat demuxer."""
    list_f = TEMP / f"_list_{uid()}.txt"
    with open(list_f, "w", encoding="utf-8") as f:
        for p in paths:
            p_safe = Path(p).as_posix()
            f.write(f"file '{p_safe}'\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
           "-i", list_f.as_posix(), "-c", "copy", Path(out).as_posix()]
    ok = run_ffmpeg(cmd, jid)
    try:
        list_f.unlink(missing_ok=True)
    except Exception:
        pass
    return ok


def cleanup(*paths: Union[str, Path]) -> None:
    """Safely unlink one or more file paths."""
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
        except Exception:
            pass


def sanitize_settings(settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate and clamp all user-provided processing parameters."""
    s = dict(settings or {})

    # Logo size [10, 2000]
    try:
        s["logo_size"] = max(10, min(2000, int(s.get("logo_size", 150))))
    except (ValueError, TypeError):
        s["logo_size"] = 150

    # Logo opacity [0.0, 1.0]
    try:
        s["logo_opacity"] = max(0.0, min(1.0, float(s.get("logo_opacity", 0.8))))
    except (ValueError, TypeError):
        s["logo_opacity"] = 0.8

    # Logo margin [0, 500]
    try:
        s["logo_margin"] = max(0, min(500, int(s.get("logo_margin", 40))))
    except (ValueError, TypeError):
        s["logo_margin"] = 40

    # Audio volumes [0.0, 5.0]
    try:
        s["audio_volume"] = max(0.0, min(5.0, float(s.get("audio_volume", 1.0))))
    except (ValueError, TypeError):
        s["audio_volume"] = 1.0

    try:
        s["bg_volume"] = max(0.0, min(5.0, float(s.get("bg_volume", 0.3))))
    except (ValueError, TypeError):
        s["bg_volume"] = 0.3

    # FPS [1, 120]
    try:
        s["fps"] = max(1, min(120, int(s.get("fps", 30))))
    except (ValueError, TypeError):
        s["fps"] = 30

    # Image duration [0.1, 60.0]
    try:
        s["img_duration"] = max(0.1, min(60.0, float(s.get("img_duration", 3.0))))
    except (ValueError, TypeError):
        s["img_duration"] = 3.0

    # Transition duration [0.1, 10.0]
    try:
        td = max(0.1, min(10.0, float(s.get("transition_duration", 0.8))))
        if td >= s["img_duration"]:
            td = max(0.1, round(s["img_duration"] / 2.0, 2))
        s["transition_duration"] = td
    except (ValueError, TypeError):
        s["transition_duration"] = 0.8

    # Quality setting
    if s.get("quality") not in {"high", "medium", "fast"}:
        s["quality"] = "medium"

    # Logo position
    if s.get("logo_position") not in {"top_right", "top_left", "bottom_right", "bottom_left", "center"}:
        s["logo_position"] = "top_right"

    # Orientation
    if s.get("orientation") not in {"landscape", "portrait"}:
        s["orientation"] = "landscape"

    # Audio mode
    if s.get("audio_mode") not in {"keep", "mute", "replace", "add"}:
        s["audio_mode"] = "keep"

    # Single transition
    if "transition" in s and s["transition"] not in TRANSITIONS:
        s["transition"] = "fade"

    # Transitions array
    if "transitions" in s and isinstance(s["transitions"], list):
        s["transitions"] = [t if t in TRANSITIONS else "fade" for t in s["transitions"]]

    # Output name
    out_name = str(s.get("output_name", "slideshow")).strip()
    s["output_name"] = safe_name(out_name)[:100] or "slideshow"

    # Multi-trim sections
    clean_trims = []
    raw_trims = s.get("trim_segments", [])
    if not raw_trims:
        ts = str(s.get("trim_start", "")).strip()
        te = str(s.get("trim_end", "")).strip()
        if ts or te:
            raw_trims = [{"start": ts, "end": te}]

    for seg in raw_trims:
        if not isinstance(seg, dict):
            continue
        ts = str(seg.get("start", "")).strip()
        te = str(seg.get("end", "")).strip()
        if not ts and not te:
            continue
        s_sec = ts_to_secs(ts)
        e_sec = ts_to_secs(te)
        if s_sec < 0 or e_sec < 0:
            continue
        if ts and te and e_sec <= s_sec:
            continue
        clean_trims.append({"start": ts, "end": te})
    s["trim_segments"] = clean_trims

    s["logo_enabled"] = bool(s.get("logo_enabled", False))
    s["use_gpu"] = str(s.get("use_gpu", False)).lower() == "true"

    return s


# ══════════════════════════════════════════════════════════════════════════════
#  SLIDESHOW JOB WORKER
# ══════════════════════════════════════════════════════════════════════════════

def process_slideshow(jid: str) -> None:
    """Build an MP4 video from images with transitions."""
    clip_paths: List[str] = []
    slideshow_raw: Optional[str] = None
    try:
        with _lock:
            job = dict(jobs[jid])

        s = job.get("settings", {})
        image_paths = job.get("files", [])
        job_out = OUTPUT / jid
        job_out.mkdir(parents=True, exist_ok=True)

        fps = int(s.get("fps", 30))
        img_duration = float(s.get("img_duration", 3.0))
        trans_names = s.get("transitions", [])
        default_trans = s.get("transition", "fade")
        trans_dur = float(s.get("transition_duration", 0.8))
        orientation = s.get("orientation", "landscape")
        output_name = s.get("output_name", "slideshow")
        audio_path = s.get("audio_path", "")
        quality = s.get("quality", "medium")
        logo_enabled = bool(s.get("logo_enabled", False))
        logo_path = s.get("logo_path", "")
        logo_pos = s.get("logo_position", "top_right")
        logo_size = int(s.get("logo_size", 150))
        logo_opacity = float(s.get("logo_opacity", 0.8))
        logo_margin = int(s.get("logo_margin", 40))

        crf_map = {"high": "18", "medium": "22", "fast": "28"}
        crf = crf_map.get(quality, "22")

        if orientation == "portrait":
            out_w, out_h = 1080, 1920
        else:
            out_w, out_h = 1920, 1080

        n = len(image_paths)
        jlog(jid, f"Slideshow: {n} image(s) → {out_w}×{out_h}  {img_duration}s/image  fps={fps}")
        jprog(jid, 2, "processing", current_item=0, total_items=n)

        if n == 0:
            jerr(jid, "No images provided")
            return

        scale_filter = (
            f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
            f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1"
        )

        jlog(jid, f"  Step 1/3: Preparing {n} image clips…")

        for i, img_path in enumerate(image_paths):
            with _lock:
                if jobs.get(jid, {}).get("status") == "cancelled":
                    jlog(jid, "Job cancelled by user", "warn")
                    for cp in clip_paths:
                        cleanup(cp)
                    return

            s1_base = 2 + (i / n) * 40
            s1_weight = 40.0 / n
            jprog(jid, int(s1_base), current_item=i + 1, total_items=n, item_pct=0)
            clip_out = str((TEMP / f"_slide_{jid}_{i:04d}.mp4").as_posix())
            clip_dur = img_duration

            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", Path(img_path).as_posix(),
                "-vf", scale_filter,
                "-t", str(clip_dur),
                "-r", str(fps),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", crf,
                "-pix_fmt", "yuv420p",
                "-an",
                clip_out
            ]
            if not run_ffmpeg(cmd, jid, is_item=True, base_pct=s1_base, weight_pct=s1_weight):
                jlog(jid, f"  ⚠ Failed to prepare image {i+1}, skipping", "warn")
                continue
            clip_paths.append(clip_out)
            jprog(jid, int(s1_base + s1_weight), item_pct=100)

        if len(clip_paths) == 0:
            jerr(jid, "All image clips failed")
            return

        jlog(jid, f"  ✓ {len(clip_paths)} clips prepared")

        with _lock:
            if jobs.get(jid, {}).get("status") == "cancelled":
                for cp in clip_paths:
                    cleanup(cp)
                return

        # ── STEP 2: Chain clips with xfade transitions ─────────────────────
        jlog(jid, "  Step 2/3: Applying transitions…")
        jprog(jid, 45, "applying transitions", item_pct=0)

        slideshow_raw = str((TEMP / f"_ss_raw_{jid}.mp4").as_posix())

        if len(clip_paths) == 1:
            shutil.copy2(clip_paths[0], slideshow_raw)
        else:
            filter_parts = []
            labels = [f"[{i}:v]" for i in range(len(clip_paths))]
            prev_label = labels[0]
            offset = 0.0

            for i in range(1, len(clip_paths)):
                t_idx = i - 1
                trans_name = trans_names[t_idx] if t_idx < len(trans_names) else default_trans
                if trans_name not in TRANSITIONS:
                    trans_name = default_trans

                offset += img_duration - trans_dur
                out_label = f"[x{i:03d}]"
                filter_parts.append(
                    f"{prev_label}{labels[i]}"
                    f"xfade=transition={trans_name}"
                    f":duration={trans_dur}"
                    f":offset={offset:.4f}"
                    f"{out_label}"
                )
                prev_label = out_label

            inputs = []
            for cp in clip_paths:
                inputs += ["-i", Path(cp).as_posix()]

            total_dur = n * img_duration - (n - 1) * trans_dur
            fc_str = "; ".join(filter_parts)

            cmd = (
                ["ffmpeg", "-y"] +
                inputs +
                ["-filter_complex", fc_str,
                 "-map", prev_label,
                 "-t", str(total_dur),
                 "-c:v", "libx264",
                 "-preset", "fast",
                 "-crf", crf,
                 "-pix_fmt", "yuv420p",
                 "-r", str(fps),
                 "-an",
                 slideshow_raw]
            )
            if not run_ffmpeg(cmd, jid):
                jlog(jid, "  ⚠ xfade failed — falling back to simple concat", "warn")
                list_f = TEMP / f"_slist_{jid}.txt"
                with open(list_f, "w", encoding="utf-8") as lf:
                    for cp in clip_paths:
                        cp_safe = Path(cp).as_posix()
                        lf.write(f"file '{cp_safe}'\n")
                cmd2 = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                        "-i", list_f.as_posix(), "-c:v", "libx264", "-preset", "fast",
                        "-crf", crf, "-pix_fmt", "yuv420p", "-an", slideshow_raw]
                run_ffmpeg(cmd2, jid)
                try:
                    list_f.unlink(missing_ok=True)
                except Exception:
                    pass

        jprog(jid, 75)
        jlog(jid, "  ✓ Transitions applied")

        with _lock:
            if jobs.get(jid, {}).get("status") == "cancelled":
                for cp in clip_paths:
                    cleanup(cp)
                if slideshow_raw:
                    cleanup(slideshow_raw)
                return

        # ── STEP 3: Add audio + logo overlay ──────────────────────────────
        jlog(jid, "  Step 3/3: Finalising — audio + logo…")

        final_out = str((job_out / f"{output_name}.mp4").as_posix())

        cmd_inputs = ["-i", Path(slideshow_raw).as_posix()]
        n_inputs = 1
        fc_parts = []
        cur_v = "[0:v]"
        cur_a = None

        # Audio
        if audio_path and Path(audio_path).exists():
            cmd_inputs += ["-i", Path(audio_path).as_posix()]
            ai = n_inputs
            n_inputs += 1
            total_dur_approx = n * img_duration
            fc_parts.append(
                f"[{ai}:a]aloop=loop=-1:size=2e+09,"
                f"atrim=duration={total_dur_approx:.2f},"
                f"afade=t=out:st={max(0, total_dur_approx - 2):.2f}:d=2,"
                f"volume=0.9[bgaudio]"
            )
            cur_a = "[bgaudio]"

        # Logo
        if logo_enabled and logo_path and Path(logo_path).exists():
            pos_map = {
                "top_right": f"W-w-{logo_margin}:{logo_margin}",
                "top_left": f"{logo_margin}:{logo_margin}",
                "bottom_right": f"W-w-{logo_margin}:H-h-{logo_margin}",
                "bottom_left": f"{logo_margin}:H-h-{logo_margin}",
                "center": "(W-w)/2:(H-h)/2",
            }
            overlay_pos = pos_map.get(logo_pos, pos_map["top_right"])
            cmd_inputs += ["-i", Path(logo_path).as_posix()]
            li = n_inputs
            n_inputs += 1
            ll = f"[logo{li}]"
            vout = f"[vlogo{li}]"
            fc_parts.append(
                f"[{li}:v]scale={logo_size}:-1,"
                f"format=rgba,"
                f"colorchannelmixer=aa={logo_opacity:.3f}{ll}"
            )
            fc_parts.append(f"{cur_v}{ll}overlay={overlay_pos}{vout}")
            cur_v = vout

        cmd = ["ffmpeg", "-y"] + cmd_inputs
        if fc_parts:
            cmd += ["-filter_complex", "; ".join(fc_parts)]
            mv = cur_v[1:-1] if re.match(r"^\[\d+:[va]\]$", cur_v) else cur_v
            cmd += ["-map", mv]
            if cur_a:
                ma = cur_a[1:-1] if re.match(r"^\[\d+:[va]\]$", cur_a) else cur_a
                cmd += ["-map", ma]
        else:
            cmd += ["-map", "0:v"]

        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", crf,
                "-pix_fmt", "yuv420p", "-r", str(fps)]
        if cur_a:
            cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
        else:
            cmd += ["-an"]
        cmd += ["-movflags", "+faststart", final_out]

        if not run_ffmpeg(cmd, jid, base_pct=75, weight_pct=25):
            jlog(jid, "  ⚠ Final encode failed, saving raw slideshow", "warn")
            shutil.copy2(slideshow_raw, final_out)

        for cp in clip_paths:
            cleanup(cp)
        cleanup(slideshow_raw)

        jprog(jid, 100)
        sz = fmt_size(Path(final_out).stat().st_size) if Path(final_out).exists() else "?"
        jdone(jid, [final_out], f"Slideshow done — {Path(final_out).name} ({sz})")
        jlog(jid, f"  Output: {final_out}", "success")

    except Exception as e:
        logger.error(f"Slideshow exception: {e}", exc_info=True)
        jerr(jid, str(e))
    finally:
        for cp in clip_paths:
            cleanup(cp)
        if slideshow_raw:
            cleanup(slideshow_raw)


# ══════════════════════════════════════════════════════════════════════════════
#  VIDEO JOB WORKER
# ══════════════════════════════════════════════════════════════════════════════

def process_job(jid: str) -> None:
    """Process batch video jobs: multi-trim, audio adjustment, logo, mid-roll, intro/outro."""
    try:
        with _lock:
            job = dict(jobs[jid])
        settings = job.get("settings", {})
        file_paths = job.get("files", [])
        job_out = OUTPUT / jid
        job_out.mkdir(parents=True, exist_ok=True)
        total = len(file_paths)
        jlog(jid, f"Job started — {total} video(s)")
        jprog(jid, 2, "processing")

        logo_enabled = bool(settings.get("logo_enabled", False))
        logo_path = settings.get("logo_path", "")
        logo_pos = settings.get("logo_position", "top_right")
        logo_size = int(settings.get("logo_size", 150))
        logo_opacity = float(settings.get("logo_opacity", 0.8))
        logo_margin = int(settings.get("logo_margin", 40))

        trim_segments = settings.get("trim_segments", [])
        intro_path = settings.get("intro_path", "")
        outro_path = settings.get("outro_path", "")
        mid_path = settings.get("mid_path", "")
        mid_ts = settings.get("mid_timestamp", "")

        audio_mode = settings.get("audio_mode", "keep")
        rep_audio = settings.get("replace_audio_path", "")
        add_audio_p = settings.get("add_audio_path", "")
        audio_vol = float(settings.get("audio_volume", 1.0))
        bg_vol = float(settings.get("bg_volume", 0.3))

        quality = settings.get("quality", "medium")
        use_gpu = bool(settings.get("use_gpu", False))

        crf_map = {"high": "18", "medium": "22", "fast": "28"}
        crf = crf_map.get(quality, "22")
        vcodec = "h264_nvenc" if use_gpu else "libx264"
        vpreset = "p4" if use_gpu else "medium"

        pos_map = {
            "top_right": f"W-w-{logo_margin}:{logo_margin}",
            "top_left": f"{logo_margin}:{logo_margin}",
            "bottom_right": f"W-w-{logo_margin}:H-h-{logo_margin}",
            "bottom_left": f"{logo_margin}:H-h-{logo_margin}",
            "center": "(W-w)/2:(H-h)/2",
        }
        overlay_pos = pos_map.get(logo_pos, pos_map["top_right"])

        completed = []

        for idx, vid_path in enumerate(file_paths):
            with _lock:
                if jobs.get(jid, {}).get("status") == "cancelled":
                    jlog(jid, "Job cancelled by user", "warn")
                    return

            vp = Path(vid_path)
            if not vp.exists():
                jlog(jid, f"Not found: {vp.name}", "error")
                continue

            item_base = 5 + (idx / total) * 90
            item_weight = 90.0 / total

            jprog(jid, int(item_base), current_item=idx + 1, total_items=total, item_pct=0)
            stem = vp.stem
            vinfo = probe(str(vp))
            dur = vinfo["duration"]
            jlog(jid, f"[{idx+1}/{total}] {vp.name}  {vinfo['width']}×{vinfo['height']}  {fmt_dur(dur)}")

            # ── STAGE 0: Multi-Trim ────────────────────────────────────────
            source_for_stage1 = vp.as_posix()
            temp_parts = []

            if len(trim_segments) > 0:
                jlog(jid, f"  → Stage 0: Trimming {len(trim_segments)} section(s)…")
                s0_weight = item_weight * 0.1
                part_weight = s0_weight / len(trim_segments)

                for i, seg in enumerate(trim_segments):
                    ts = seg.get("start", "").strip()
                    te = seg.get("end", "").strip()
                    if not ts and not te:
                        continue

                    part_out = str((TEMP / f"_part_{uid()}_{i}.mp4").as_posix())
                    cmd = ["ffmpeg", "-y"]
                    if ts:
                        cmd += ["-ss", ts]
                    cmd += ["-i", vp.as_posix()]
                    if te:
                        cmd += ["-to", te]
                    cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero", part_out]

                    if run_ffmpeg(cmd, jid, is_item=True, base_pct=item_base + i * part_weight, weight_pct=part_weight):
                        temp_parts.append(part_out)

                if len(temp_parts) > 1:
                    merged_parts = str((TEMP / f"_merged_{uid()}.mp4").as_posix())
                    if concat_videos(temp_parts, merged_parts, jid):
                        source_for_stage1 = merged_parts
                    else:
                        jlog(jid, "  ⚠ Multi-trim concat failed, using original", "warn")
                elif len(temp_parts) == 1:
                    source_for_stage1 = temp_parts[0]

                item_base += s0_weight
                item_weight *= 0.9

            # ── STAGE 1: Main processing (audio + logo) ─────────────────────
            stage1_out = str((TEMP / f"_s1_{uid()}.mp4").as_posix())

            cmd_inputs = ["-i", source_for_stage1]
            n_inputs = 1
            fc = []
            cur_v = "[0:v]"

            eff_vinfo = vinfo if source_for_stage1 == vp.as_posix() else probe(source_for_stage1)
            eff_dur = eff_vinfo["duration"]
            has_audio = eff_vinfo["has_audio"]
            cur_a = "[0:a]" if has_audio else None

            # Audio treatment
            if audio_mode == "mute":
                cur_a = None
            elif audio_mode == "replace" and rep_audio and Path(rep_audio).exists():
                cmd_inputs += ["-i", Path(rep_audio).as_posix()]
                ai = n_inputs
                n_inputs += 1
                out_lbl = f"[ra{ai}]"
                fc.append(f"[{ai}:a]apad,atrim=duration={eff_dur:.3f},volume={audio_vol:.3f}{out_lbl}")
                cur_a = out_lbl
            elif audio_mode == "add" and add_audio_p and Path(add_audio_p).exists():
                cmd_inputs += ["-i", Path(add_audio_p).as_posix()]
                ai = n_inputs
                n_inputs += 1
                bg_lbl = f"[bga{ai}]"
                mix_lbl = f"[mix{ai}]"
                fc.append(f"[{ai}:a]apad,atrim=duration={eff_dur:.3f},volume={bg_vol:.3f}{bg_lbl}")
                if cur_a:
                    main_lbl = f"[mna{ai}]"
                    fc.append(f"{cur_a}volume={audio_vol:.3f}{main_lbl}")
                    fc.append(f"{main_lbl}{bg_lbl}amix=inputs=2:duration=first:dropout_transition=2{mix_lbl}")
                    cur_a = mix_lbl
                else:
                    cur_a = bg_lbl
            elif audio_mode == "keep" and cur_a and audio_vol != 1.0:
                vol_lbl = "[avol]"
                fc.append(f"{cur_a}volume={audio_vol:.3f}{vol_lbl}")
                cur_a = vol_lbl

            # Logo overlay
            if logo_enabled and logo_path and Path(logo_path).exists():
                cmd_inputs += ["-i", Path(logo_path).as_posix()]
                li = n_inputs
                n_inputs += 1
                ll = f"[logo{li}]"
                vout = f"[vl{li}]"
                fc.append(
                    f"[{li}:v]scale={logo_size}:-1,"
                    f"format=rgba,"
                    f"colorchannelmixer=aa={logo_opacity:.3f}{ll}"
                )
                fc.append(f"{cur_v}{ll}overlay={overlay_pos}{vout}")
                cur_v = vout

            cmd = ["ffmpeg", "-y"] + cmd_inputs
            if fc:
                cmd += ["-filter_complex", ";".join(fc)]
                mv = cur_v[1:-1] if re.match(r"^\[\d+:[va]\]$", cur_v) else cur_v
                cmd += ["-map", mv]
                if cur_a:
                    ma = cur_a[1:-1] if re.match(r"^\[\d+:[va]\]$", cur_a) else cur_a
                    cmd += ["-map", ma]
            else:
                cmd += ["-map", "0:v"]
                if cur_a:
                    cmd += ["-map", "0:a"]

            if use_gpu:
                cmd += ["-c:v", vcodec, "-preset", vpreset, "-cq", crf]
            else:
                cmd += ["-c:v", vcodec, "-preset", vpreset, "-crf", crf]

            if cur_a:
                cmd += ["-c:a", "aac", "-b:a", "192k"]
            else:
                cmd += ["-an"]
            cmd += ["-movflags", "+faststart", stage1_out]

            jlog(jid, "  → Stage 1: encode…")
            s1_weight = item_weight * 0.7
            if not run_ffmpeg(cmd, jid, is_item=True, base_pct=item_base, weight_pct=s1_weight):
                jlog(jid, "  ✗ Stage 1 failed — skipping", "error")
                cleanup(stage1_out)
                if source_for_stage1 != vp.as_posix():
                    cleanup(source_for_stage1)
                for p in temp_parts:
                    cleanup(p)
                continue
            jlog(jid, "  ✓ Stage 1 complete")

            if source_for_stage1 != vp.as_posix():
                cleanup(source_for_stage1)
            for p in temp_parts:
                cleanup(p)

            # ── STAGE 2: Mid-roll ──────────────────────────────────────────
            stage2_out = stage1_out
            s2_base = item_base + s1_weight
            s2_weight = item_weight * 0.15

            if mid_path and Path(mid_path).exists() and mid_ts:
                jlog(jid, f"  → Stage 2: mid-roll at {mid_ts}…")
                p1 = str((TEMP / f"_p1_{uid()}.mp4").as_posix())
                p2 = str((TEMP / f"_p2_{uid()}.mp4").as_posix())
                p1r = str((TEMP / f"_p1r_{uid()}.mp4").as_posix())
                p2r = str((TEMP / f"_p2r_{uid()}.mp4").as_posix())
                midr = str((TEMP / f"_mid_{uid()}.mp4").as_posix())
                merged = str((TEMP / f"_midmrg_{uid()}.mp4").as_posix())

                step = s2_weight / 6.0

                ok1 = run_ffmpeg(["ffmpeg", "-y", "-i", stage1_out, "-t", mid_ts, "-c", "copy", p1],
                                 jid, is_item=True, base_pct=s2_base, weight_pct=step)
                ok2 = run_ffmpeg(["ffmpeg", "-y", "-i", stage1_out, "-ss", mid_ts, "-c", "copy", p2],
                                 jid, is_item=True, base_pct=s2_base + step, weight_pct=step)

                if ok1 and ok2:
                    reencode(p1, p1r, jid, crf, is_item=True, base_pct=s2_base + step * 2, weight_pct=step)
                    reencode(mid_path, midr, jid, crf, is_item=True, base_pct=s2_base + step * 3, weight_pct=step)
                    reencode(p2, p2r, jid, crf, is_item=True, base_pct=s2_base + step * 4, weight_pct=step)
                    if concat_videos([p1r, midr, p2r], merged, jid):
                        stage2_out = merged
                        jlog(jid, "  ✓ Mid-roll inserted")
                    else:
                        jlog(jid, "  ⚠ Mid-roll concat failed", "warn")
                else:
                    jlog(jid, "  ⚠ Mid-roll split failed", "warn")
                cleanup(p1, p2, p1r, p2r, midr)
            else:
                jprog(jid, int(s2_base + s2_weight))

            # ── STAGE 3: Intro / Outro ─────────────────────────────────────
            segments = []
            seg_temps = []
            s3_base = item_base + s1_weight + s2_weight
            s3_weight = item_weight * 0.15

            s3_steps = (1 if intro_path else 0) + 1 + (1 if outro_path else 0) + 1
            s3_step = s3_weight / s3_steps
            cur_s3 = s3_base

            if intro_path and Path(intro_path).exists():
                inr = str((TEMP / f"_inr_{uid()}.mp4").as_posix())
                reencode(intro_path, inr, jid, crf, is_item=True, base_pct=cur_s3, weight_pct=s3_step)
                segments.append(inr)
                seg_temps.append(inr)
                cur_s3 += s3_step

            main_r = str((TEMP / f"_mainr_{uid()}.mp4").as_posix())
            reencode(stage2_out, main_r, jid, crf, is_item=True, base_pct=cur_s3, weight_pct=s3_step)
            segments.append(main_r)
            seg_temps.append(main_r)
            cur_s3 += s3_step

            if outro_path and Path(outro_path).exists():
                outr = str((TEMP / f"_outr_{uid()}.mp4").as_posix())
                reencode(outro_path, outr, jid, crf, is_item=True, base_pct=cur_s3, weight_pct=s3_step)
                segments.append(outr)
                seg_temps.append(outr)
                cur_s3 += s3_step

            final_out = str((job_out / f"{stem}_processed.mp4").as_posix())

            if len(segments) > 1:
                jlog(jid, f"  → Stage 3: concat {len(segments)} segment(s)…")
                if not concat_videos(segments, final_out, jid):
                    jlog(jid, "  ⚠ Concat failed, saving main only", "warn")
                    shutil.copy2(main_r, final_out)
                else:
                    jlog(jid, "  ✓ Concat complete")
            else:
                shutil.copy2(main_r, final_out)

            completed.append(final_out)
            jprog(jid, int(item_base + item_weight), item_pct=100)

            cleanup(*seg_temps)
            if stage2_out != stage1_out:
                cleanup(stage2_out)
            cleanup(stage1_out)

        # Cleanup temp leftovers for this job
        for f in TEMP.glob("_part_*"):
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass

        jdone(jid, completed, f"{len(completed)}/{total} video(s) processed")

    except Exception as e:
        logger.error(f"Process job exception: {e}", exc_info=True)
        jerr(jid, str(e))


# ══════════════════════════════════════════════════════════════════════════════
#  MIDDLEWARE & ERROR HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

@app.before_request
def check_csrf() -> Optional[Any]:
    """Validate same-origin for state-changing requests when Origin or Referer header is sent."""
    if request.method == "POST":
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer")
        header = origin or referer
        if header:
            parsed = urlparse(header)
            if parsed.netloc and parsed.netloc != request.host:
                return jsonify({"error": "Forbidden: cross-origin request rejected"}), 403
    return None


@app.after_request
def set_security_headers(response: Any) -> Any:
    """Inject hardened HTTP security headers."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.errorhandler(413)
def request_entity_too_large(error: Any) -> Any:
    """Return JSON response for file upload exceeding size limit."""
    return jsonify({"error": f"Upload exceeds maximum limit of {MAX_UPLOAD_GB} GB"}), 413


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Render the primary single-page UI."""
    return render_template(
        "index.html",
        ffmpeg_ok=ffmpeg_ok(),
        transitions=TRANSITIONS,
        app_name=APP_NAME,
        app_tagline=APP_TAGLINE,
        app_version=__version__,
    )


@app.route("/health")
def health():
    """Healthcheck endpoint for container orchestration and status monitoring."""
    return jsonify({
        "status": "ok",
        "version": __version__,
        "ffmpeg": ffmpeg_ok()
    })


@app.route("/ffmpeg-check")
def check_ffmpeg():
    """Check FFmpeg presence and return version info."""
    ok = ffmpeg_ok()
    return jsonify({"available": ok, "version": ffmpeg_version() if ok else ""})


@app.route("/upload/<folder>", methods=["POST"])
def upload(folder: str):
    """Handle secure file uploads with folder-specific extension allow-lists."""
    if folder not in FOLDER_MAP:
        return jsonify({"error": "Invalid folder"}), 400

    allowed_exts = FOLDER_ALLOWLIST.get(folder, set())
    dest_dir = FOLDER_MAP[folder]
    uploaded = []

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files uploaded"}), 400

    for f in files:
        if not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext not in allowed_exts:
            return jsonify({
                "error": f"File '{f.filename}' has unsupported extension '{ext}'. Allowed: {', '.join(sorted(allowed_exts))}"
            }), 400

        name = safe_name(f.filename)
        dest = dest_dir / name
        if dest.exists():
            name = f"{Path(name).stem}_{uid(6)}{ext}"
            dest = dest_dir / name

        f.save(dest)
        info = {
            "name": name,
            "path": dest.as_posix(),
            "size_fmt": fmt_size(dest.stat().st_size)
        }
        if ext in ALLOWED_VIDEO:
            pi = probe(str(dest))
            info.update(pi)
            info["duration_fmt"] = fmt_dur(pi["duration"])
            info["resolution"] = f"{pi['width']}×{pi['height']}" if pi["width"] else "—"
        uploaded.append(info)

    return jsonify({"uploaded": uploaded})


@app.route("/files/<folder>")
def list_files(folder: str):
    """List uploaded files or generated outputs."""
    if folder == "outputs":
        files = []
        for p in sorted(OUTPUT.rglob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.is_file() and p.suffix.lower() == ".mp4":
                files.append({
                    "name": p.name,
                    "path": p.as_posix(),
                    "size_fmt": fmt_size(p.stat().st_size)
                })
        return jsonify({"files": files})

    if folder not in FOLDER_MAP:
        return jsonify({"files": []})

    files = []
    for p in sorted(FOLDER_MAP[folder].iterdir()):
        if p.is_file() and p.name != ".gitkeep":
            info = {
                "name": p.name,
                "path": p.as_posix(),
                "size_fmt": fmt_size(p.stat().st_size)
            }
            if p.suffix.lower() in ALLOWED_VIDEO:
                pi = probe(str(p))
                info.update(pi)
                info["duration_fmt"] = fmt_dur(pi["duration"])
                info["resolution"] = f"{pi['width']}×{pi['height']}" if pi["width"] else "—"
            files.append(info)
    return jsonify({"files": files})


@app.route("/delete-file", methods=["POST"])
def delete_file():
    """Delete a single file securely within uploads or outputs."""
    data = request.json or {}
    path_str = data.get("path", "")
    if not path_str:
        return jsonify({"error": "No path provided"}), 400

    try:
        p = resolve_safe(path_str, UPLOAD, OUTPUT)
    except ValueError as e:
        return jsonify({"error": str(e)}), 403

    if not p.exists():
        return jsonify({"error": "File not found"}), 404
    if not p.is_file():
        return jsonify({"error": "Target is not a file"}), 400

    try:
        p.unlink()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": f"Failed to delete file: {e}"}), 500


@app.route("/clear/<folder>", methods=["POST"])
def clear_folder(folder: str):
    """Clear all user files in a given folder."""
    if folder == "outputs":
        shutil.rmtree(OUTPUT, ignore_errors=True)
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / ".gitkeep").touch(exist_ok=True)
        return jsonify({"ok": True})

    if folder not in FOLDER_MAP:
        return jsonify({"ok": False, "error": "Invalid folder"}), 400

    d = FOLDER_MAP[folder]
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    (d / ".gitkeep").touch(exist_ok=True)
    return jsonify({"ok": True})


@app.route("/probe", methods=["POST"])
def probe_route():
    """Probe media metadata for a file within uploads or outputs."""
    path_str = (request.json or {}).get("path", "")
    if not path_str:
        return jsonify({"error": "Path required"}), 400

    try:
        p = resolve_safe(path_str, UPLOAD, OUTPUT)
    except ValueError as e:
        return jsonify({"error": str(e)}), 403

    if not p.exists() or not p.is_file():
        return jsonify({"error": "File not found"}), 404

    pi = probe(str(p))
    pi["duration_fmt"] = fmt_dur(pi["duration"])
    return jsonify(pi)


@app.route("/download")
def download():
    """Download an output MP4 file safely."""
    path_str = request.args.get("path", "")
    if not path_str:
        return "Path required", 400

    try:
        p = resolve_safe(path_str, OUTPUT)
    except ValueError:
        return "Access denied", 403

    if not p.exists() or not p.is_file():
        return "Not found", 404
    if p.suffix.lower() != ".mp4":
        return "Invalid file type", 400

    return send_file(str(p), as_attachment=True, download_name=p.name)


@app.route("/process", methods=["POST"])
def start_process():
    """Validate parameters and start asynchronous video processing job."""
    prune_jobs()
    data = request.json or {}
    raw_files = data.get("files", [])
    raw_settings = data.get("settings", {})

    if not raw_files:
        return jsonify({"error": "No videos selected"}), 400
    if not ffmpeg_ok():
        return jsonify({"error": "FFmpeg not found. Install FFmpeg and add to PATH."}), 500

    # Validate video files
    safe_files = []
    for fp in raw_files:
        try:
            p = resolve_safe(fp, VIDEOS_DIR)
            if not p.exists() or not p.is_file() or p.suffix.lower() not in ALLOWED_VIDEO:
                return jsonify({"error": f"Invalid video file: '{fp}'"}), 400
            safe_files.append(p.as_posix())
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    settings = sanitize_settings(raw_settings)

    # Validate paths in settings
    if settings["logo_enabled"] and settings.get("logo_path"):
        try:
            lp = resolve_safe(settings["logo_path"], LOGO_DIR)
            if not lp.exists() or not lp.is_file() or lp.suffix.lower() not in ALLOWED_IMAGE:
                return jsonify({"error": "Invalid logo file"}), 400
            settings["logo_path"] = lp.as_posix()
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    for key, folder_dir, allowset in [
        ("intro_path", INTRO_DIR, ALLOWED_VIDEO),
        ("outro_path", OUTRO_DIR, ALLOWED_VIDEO),
        ("mid_path", MID_DIR, ALLOWED_VIDEO),
        ("replace_audio_path", AUDIO_DIR, ALLOWED_AUDIO),
        ("add_audio_path", AUDIO_DIR, ALLOWED_AUDIO),
    ]:
        val = settings.get(key, "").strip()
        if val:
            try:
                p = resolve_safe(val, folder_dir)
                if not p.exists() or not p.is_file() or p.suffix.lower() not in allowset:
                    return jsonify({"error": f"Invalid file for {key}"}), 400
                settings[key] = p.as_posix()
            except ValueError as e:
                return jsonify({"error": str(e)}), 400

    jid = uid(12)
    with _lock:
        jobs[jid] = {
            "status": "queued",
            "progress": 0,
            "logs": [],
            "outputs": [],
            "files": safe_files,
            "settings": settings,
            "created": time.time(),
            "type": "video"
        }

    threading.Thread(target=process_job, args=(jid,), daemon=True).start()
    return jsonify({"job_id": jid})


@app.route("/slideshow", methods=["POST"])
def start_slideshow():
    """Validate parameters and start asynchronous slideshow creation job."""
    prune_jobs()
    data = request.json or {}
    raw_files = data.get("files", [])
    raw_settings = data.get("settings", {})

    if not raw_files:
        return jsonify({"error": "No images selected"}), 400
    if not ffmpeg_ok():
        return jsonify({"error": "FFmpeg not found. Install FFmpeg and add to PATH."}), 500

    # Validate image files
    safe_files = []
    for fp in raw_files:
        try:
            p = resolve_safe(fp, IMAGES_DIR)
            if not p.exists() or not p.is_file() or p.suffix.lower() not in ALLOWED_IMAGE:
                return jsonify({"error": f"Invalid image file: '{fp}'"}), 400
            safe_files.append(p.as_posix())
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    settings = sanitize_settings(raw_settings)

    # Validate audio path
    audio_p = settings.get("audio_path", "").strip()
    if audio_p:
        try:
            ap = resolve_safe(audio_p, AUDIO_DIR)
            if not ap.exists() or not ap.is_file() or ap.suffix.lower() not in ALLOWED_AUDIO:
                return jsonify({"error": "Invalid audio file"}), 400
            settings["audio_path"] = ap.as_posix()
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    # Validate logo path
    if settings["logo_enabled"] and settings.get("logo_path"):
        try:
            lp = resolve_safe(settings["logo_path"], LOGO_DIR)
            if not lp.exists() or not lp.is_file() or lp.suffix.lower() not in ALLOWED_IMAGE:
                return jsonify({"error": "Invalid logo file"}), 400
            settings["logo_path"] = lp.as_posix()
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    jid = uid(12)
    with _lock:
        jobs[jid] = {
            "status": "queued",
            "progress": 0,
            "logs": [],
            "outputs": [],
            "files": safe_files,
            "settings": settings,
            "created": time.time(),
            "type": "slideshow"
        }

    threading.Thread(target=process_slideshow, args=(jid,), daemon=True).start()
    return jsonify({"job_id": jid})


@app.route("/transitions")
def get_transitions():
    """Return dictionary of available xfade transitions."""
    return jsonify(TRANSITIONS)


@app.route("/job/<jid>")
def job_status(jid: str):
    """Return live status, progress, ETA, and logs for a job."""
    with _lock:
        job = jobs.get(jid)
    if not job:
        return jsonify({"error": "not found"}), 404

    return jsonify({
        "status": job["status"],
        "progress": job["progress"],
        "logs": job["logs"],
        "outputs": job.get("outputs", []),
        "current_item": job.get("current_item"),
        "total_items": job.get("total_items"),
        "item_pct": job.get("item_pct"),
        "eta": job.get("eta")
    })


@app.route("/job/<jid>/cancel", methods=["POST"])
def cancel_job(jid: str):
    """Cancel an active job and terminate running FFmpeg process."""
    with _lock:
        if jid in jobs:
            jobs[jid]["status"] = "cancelled"
            proc = jobs[jid].get("proc")
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
    jlog(jid, "Job cancelled by user", "warn")
    return jsonify({"ok": True})


@app.route("/jobs")
def list_jobs():
    """List summary of active and recent jobs."""
    prune_jobs()
    with _lock:
        summary = {
            jid: {
                "status": j["status"],
                "progress": j["progress"],
                "created": j.get("created"),
                "type": j.get("type"),
                "outputs_count": len(j.get("outputs", []))
            }
            for jid, j in jobs.items()
        }
    return jsonify({"jobs": summary})


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    purge_stale_temp(24)
    ok = ffmpeg_ok()
    ver = ffmpeg_version() if ok else "NOT FOUND"
    print("=" * 55)
    print(f"  {APP_NAME} v{__version__}")
    print(f"  http://{HOST}:{PORT}")
    print("=" * 55)
    if HOST not in ("127.0.0.1", "localhost", "::1"):
        print("  [WARNING] This app has no authentication.")
        print("            Do not expose it to untrusted networks!")
        print("=" * 55)
    print(f"  FFmpeg: {'[OK] ' + ver[:40] if ok else '[ERR] Not found — install FFmpeg!'}")
    print("  Press Ctrl+C to stop")
    print("=" * 55)
    app.run(debug=DEBUG, host=HOST, port=PORT, threaded=True)
