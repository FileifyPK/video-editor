# Video Editor — User Guide

This guide covers all capabilities of Video Editor, tab-by-tab.

---

## 1. Left Sidebar: Uploading Files

The left sidebar manages your input media assets:

- **Videos:** Source files to trim, watermark, or concatenate. Multi-file uploads supported (`.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`, `.m4v`, `.flv`). Checkboxes next to uploaded videos determine which items get processed in the batch queue.
- **Logo:** Transparent watermark files (`.png`, `.webp`). Upload your brand or channel emblem here.
- **Intro / Outro / Mid-roll:** Auxiliary clips to attach to processed videos.
- **Audio:** Music, background ambience, or voiceover recordings (`.mp3`, `.wav`, `.aac`, `.m4a`, `.ogg`, `.flac`).
- **Images:** Photos and graphics for slideshow creation (`.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.tiff`).

---

## 2. Center Panel: Configuration Tabs

### 🔖 Logo (Watermark)
- **Enable Logo Overlay:** Toggle watermark overlay on or off.
- **Select Logo:** Pick from uploaded logo files.
- **Position:** Choose one of 5 positions:
  - `Top Left`
  - `Top Right` (default)
  - `Bottom Left`
  - `Bottom Right`
  - `Center`
- **Size:** Scales logo width in pixels (10 px to 2000 px, default: 150 px). Aspect ratio is preserved.
- **Opacity:** Adjust transparency from 0.0 (fully transparent) to 1.0 (fully opaque).
- **Margin:** Padding from the edge of the screen in pixels (0 px to 500 px).
- **Interactive Preview:** The preview frame displays a live visual preview of your logo placement.

### ✂ Trim (Multi-Section Trimming)
- Extract one or multiple sections from your videos and automatically merge them in order.
- Format: `HH:MM:SS` or `MM:SS` or raw seconds (e.g. `00:01:15` to `00:02:30`).
- Click `+ Add Another Section` to define subsequent slices.
- All timestamps are calculated against the source video duration.

### 🎵 Audio Options
Choose how audio is handled in output videos:
1. **Keep Original:** Retains source audio stream with a master volume slider (0.0 to 5.0x).
2. **Mute:** Completely removes all audio streams from output.
3. **Replace Audio:** Strips source audio and inserts your chosen uploaded audio track, trimming or looping as needed.
4. **Mix Background Audio:** Keeps source audio while mixing in an ambient or background music track. Both source volume and background track volume can be balanced independently.

### 📦 Output Settings
- **Quality Preset:**
  - `High` (CRF 18): Near-lossless quality, larger file sizes.
  - `Balanced` (CRF 22): Recommended everyday balance of visual fidelity and file size.
  - `Fast` (CRF 28): Smaller files, faster render times.
- **GPU Acceleration (NVENC):** When enabled, uses NVIDIA NVENC hardware encoder (`h264_nvenc`) with preset `p4` and constant quality `-cq`, significantly accelerating render times on compatible NVIDIA GPUs.

### 🎞 Slideshow Builder
- **Orientation:**
  - `Landscape (16:9)`: 1920×1080 resolution for YouTube and desktop viewing.
  - `Portrait (9:16)`: 1080×1920 resolution for Instagram Reels, YouTube Shorts, and TikTok.
- **Image Duration:** Display time per photo in seconds (0.1s to 60.0s).
- **Transition Duration:** Overlap time between slides (0.1s to 10.0s).
- **Global & Per-Slide Transitions:** Select a default transition from 36 effects, or drag-and-drop images in the queue to customize transitions for individual cuts.
- **Background Music & Watermarking:** Optionally include background music and watermark overlays directly in slideshow jobs.

---

## 3. Right Sidebar: Live Logs & Job History

- **Live Log:** Displays real-time FFmpeg stderr output, command parameters, and completion status.
- **Progress Tracking:** Dual-stage tracking shows overall job progress alongside single-item progress.
- **Estimated Time Remaining (ETA):** Automatically calculated based on encoding throughput.
- **Cancel Button:** Stops active rendering immediately and safely releases temporary disk files.
- **Completed Files:** Download finished `.mp4` videos directly with a single click.
