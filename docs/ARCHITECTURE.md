# Video Editor — Architecture Documentation

This document describes the architectural layout, threading model, and execution lifecycle of Video Editor.

---

## 1. Component Overview

```text
┌────────────────────────────────────────────────────────┐
│                   Single-Page Client                   │
│   (HTML5, Vanilla JS, CSS Grid/Flexbox, Event Loop)    │
└───────────────────────────┬────────────────────────────┘
                            │ HTTP / JSON / Multipart
┌───────────────────────────▼────────────────────────────┐
│                    Flask Web Server                    │
│   - Route validation & resolve_safe() sandbox          │
│   - sanitize_settings() input normalizer               │
│   - Thread-safe in-memory jobs store                   │
│   - Static assets & template renderer                  │
└─────────────┬────────────────────────────┬─────────────┘
              │ Spawn Thread               │ Poll Status
┌─────────────▼──────────────┐ ┌───────────▼─────────────┐
│  Background Job Workers    │ │   Job History & Logs    │
│  - process_job()           │ │   - Live log buffer     │
│  - process_slideshow()     │ │   - Subprocess tracker  │
└─────────────┬──────────────┘ └─────────────────────────┘
              │ Subprocess (Popen)
┌─────────────▼──────────────────────────────────────────┐
│              External FFmpeg / FFprobe Tools           │
│   - Multi-trim & concat demuxer                        │
│   - Filter graphs (xfade, overlay, aloop, amix)        │
│   - CPU (libx264) & GPU (h264_nvenc) encoders          │
└────────────────────────────────────────────────────────┘
```

---

## 2. File & Directory Layout

- `uploads/`: Temporary repository for uploaded assets, organized into subdirectories (`videos/`, `logo/`, `intro/`, `outro/`, `mid/`, `audio/`, `images/`).
- `temp/`: Scratchpad for intermediate rendering stages (e.g. trimmed parts, individual image clips, concat playlists). Automatically cleaned up upon job completion, cancellation, error, or server startup.
- `outputs/<jid>/`: Finished rendered MP4 files organized by job ID.
- `templates/index.html`: Responsive single-page interface rendered via Jinja2.

---

## 3. Concurrency & Threading Model

1. **Worker Threads:** Every execution request (`/process` or `/slideshow`) generates a unique alphanumeric `job_id`, registers a job record in the global `jobs` dictionary under a thread mutex lock (`_lock`), and launches an unblocked daemon `threading.Thread`.
2. **Subprocess Management:** Workers invoke `subprocess.Popen` with explicit parameter lists (never using `shell=True`). The active `Popen` reference is linked to `jobs[jid]['proc']` to support clean termination on cancellation.
3. **Telemetry & Log Parsing:** Standard error from FFmpeg is parsed line-by-line to extract `Duration:` and `time=` markers, updating job percentage and remaining time estimates in real time. Log entries are capped at 2,000 lines per job.
4. **Job Retention & Pruning:** When jobs exceed `VIDEO_EDITOR_JOB_TTL_HOURS`, they are pruned from memory during subsequent job submissions or status checks.

---

## 4. Pipeline Stages

### Video Processing Pipeline (`process_job`)
1. **Stage 0 (Multi-Trim):** Extracts defined time segments with `-ss` and `-to`, then joins them via FFmpeg's concat demuxer (`-f concat -safe 0`).
2. **Stage 1 (Primary Processing):**
   - Applies volume scaling or audio replacement/mixing.
   - Rescales user logo with `scale=X:-1`, applies RGBA color mixer for transparency, and overlays onto video.
   - Encodes via `libx264` or `h264_nvenc`.
3. **Stage 2 (Mid-roll Insertion):** Splits intermediate video at `mid_timestamp`, re-encodes parts to standard parameters, and concatenates `[part1, mid_roll, part2]`.
4. **Stage 3 (Intro/Outro Concatenation):** Re-encodes optional intro and outro clips to match main video parameters and joins them into the final output.

### Slideshow Pipeline (`process_slideshow`)
1. **Clip Generation:** Generates individual video clips from static images scaled and letterbox-padded to exact dimensions (`1920x1080` or `1080x1920`).
2. **Transition Chaining:** Chains clips sequentially using FFmpeg's `xfade` filter graph with calculated cumulative time offsets.
3. **Audio & Watermark Pass:** Integrates looped audio with fade-out and overlays watermarks.
