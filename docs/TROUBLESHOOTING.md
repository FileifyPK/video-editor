# Video Editor — Troubleshooting Guide

This guide covers common issues, diagnosis techniques, and solutions.

---

## 1. "FFmpeg Missing" or `ffmpeg-check` Fails

**Symptoms:** The top bar shows a red badge `FFmpeg Missing`, and processing buttons are disabled.

**Resolution:**
- Confirm that `ffmpeg` and `ffprobe` are installed and reachable in your terminal:
  ```bash
  ffmpeg -version
  ffprobe -version
  ```
- If installed but not found, add the folder containing `ffmpeg.exe` to your system environment `PATH` variable.
- After modifying `PATH`, completely close and restart `start.bat` or `start.sh` so the new environment is loaded.

---

## 2. NVIDIA GPU Acceleration (NVENC) Errors

**Symptoms:** Live Log displays `Cannot load nvcuda.dll` or `Unknown encoder 'h264_nvenc'`.

**Cause:** The system lacks a compatible NVIDIA graphics card, updated NVIDIA display drivers, or FFmpeg was compiled without NVENC support (`--enable-nvenc`).

**Resolution:**
- Switch back to standard CPU encoding by unticking **Use NVIDIA GPU (NVENC)** in the Output tab. CPU encoding (`libx264`) works reliably on all machines.
- Ensure your NVIDIA drivers are up-to-date from [nvidia.com/drivers](https://www.nvidia.com/download/index.aspx).

---

## 3. Upload Fails with HTTP 413 (File Too Large)

**Symptoms:** Browser alerts that upload failed, or network inspector returns HTTP 413.

**Cause:** Source file exceeds the configured upload limit (default: 5 GB).

**Resolution:**
- Adjust the upload limit by setting the `VIDEO_EDITOR_MAX_UPLOAD_GB` environment variable:
  ```cmd
  set VIDEO_EDITOR_MAX_UPLOAD_GB=15
  start.bat
  ```

---

## 4. Non-Latin Filenames (Urdu, Arabic, Chinese, Accents)

**Symptoms:** Files with non-Latin titles upload or render with underscored names.

**Behavior:**
- Video Editor preserves Unicode names across all modern filesystems.
- Filename sanitization only replaces filesystem-reserved and control characters (`< > : " / \ | ? *`) and Windows reserved device stems (such as `CON`, `PRN`, `AUX`, `NUL`).

---

## 5. Port 5000 Already in Use

**Symptoms:** The server fails to start, displaying `[WinError 10048] Only one usage of each socket address is normally permitted` or `Address already in use`.

**Resolution:**
- Choose an alternative port by defining `VIDEO_EDITOR_PORT`:
  ```cmd
  set VIDEO_EDITOR_PORT=5050
  start.bat
  ```
  Or on Linux/macOS:
  ```bash
  VIDEO_EDITOR_PORT=5050 ./start.sh
  ```

---

## 6. Temporary Disk Space Usage in `temp/`

**Symptoms:** Hard drive fills up during large batch processing jobs.

**Resolution:**
- Processing creates intermediate files in the `temp/` directory. These files are automatically deleted upon job completion or cancellation.
- If an unexpected crash occurs, restart the server; Video Editor automatically scans and purges files older than 24 hours at startup.
- You can manually delete leftover files inside `temp/` at any time when no jobs are actively processing (keep `.gitkeep`).
