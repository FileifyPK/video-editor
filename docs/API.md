# Video Editor — REST API Specification

Video Editor exposes a lightweight JSON API. All state-changing requests use `POST` and expect either `application/json` or `multipart/form-data`.

---

## Index & Status Endpoints

### `GET /`
Renders the primary web user interface.

### `GET /health`
Returns system status for container orchestration and uptime probes.
- **Response (200 OK):**
  ```json
  {
    "status": "ok",
    "version": "1.0.0",
    "ffmpeg": true
  }
  ```

### `GET /ffmpeg-check`
Returns status of local FFmpeg executable.
- **Response (200 OK):**
  ```json
  {
    "available": true,
    "version": "ffmpeg version 8.1.1-essentials_build..."
  }
  ```

### `GET /transitions`
Returns the dictionary of all 36 available xfade transitions.
- **Response (200 OK):**
  ```json
  {
    "fade": "Fade",
    "wipeleft": "Wipe Left",
    "zoomin": "Zoom In"
  }
  ```

---

## File Operations

### `POST /upload/<folder>`
Uploads one or more files to a designated folder (`videos`, `logo`, `intro`, `outro`, `mid`, `audio`, `images`).
- **Content-Type:** `multipart/form-data`
- **Fields:** `files` (array of file objects)
- **Validation:** Uploaded files must match the folder-specific allowed extension list.
- **Response (200 OK):**
  ```json
  {
    "uploaded": [
      {
        "name": "sample.mp4",
        "path": "D:/.../uploads/videos/sample.mp4",
        "size_fmt": "14.2 MB",
        "duration": 60.5,
        "duration_fmt": "1:00",
        "width": 1920,
        "height": 1080
      }
    ]
  }
  ```
- **Error (400 Bad Request):**
  ```json
  {
    "error": "File 'script.sh' has unsupported extension '.sh'."
  }
  ```

### `GET /files/<folder>`
Lists files residing in an upload folder or output repository (`outputs`).
- **Response (200 OK):**
  ```json
  {
    "files": [
      {
        "name": "clip.mp4",
        "path": "...",
        "size_fmt": "5.4 MB"
      }
    ]
  }
  ```

### `POST /delete-file`
Deletes a single file within `uploads/` or `outputs/`.
- **Content-Type:** `application/json`
- **Body:** `{"path": "..."}`
- **Response:** `{"ok": true}` (200 OK) or `403 Forbidden` if path attempts directory traversal.

### `POST /clear/<folder>`
Deletes all files in the specified folder.
- **Response:** `{"ok": true}` (200 OK).

### `POST /probe`
Inspects media metadata for any file inside `uploads/` or `outputs/`.
- **Content-Type:** `application/json`
- **Body:** `{"path": "..."}`
- **Response (200 OK):**
  ```json
  {
    "duration": 45.2,
    "duration_fmt": "0:45",
    "width": 1920,
    "height": 1080,
    "fps": 30.0,
    "codec": "h264",
    "has_audio": true,
    "size": 10485760
  }
  ```

### `GET /download?path=...`
Downloads a generated MP4 file from `outputs/`.
- **Query Parameter:** `path` (relative or absolute path inside outputs)
- **Validation:** Target file must resolve strictly inside `outputs/` and have `.mp4` extension.
- **Response:** File stream (200 OK) or `403 Forbidden` / `404 Not Found`.

---

## Job Management

### `POST /process`
Starts a batch video processing job.
- **Content-Type:** `application/json`
- **Body:**
  ```json
  {
    "files": [".../uploads/videos/video1.mp4"],
    "settings": {
      "logo_enabled": true,
      "logo_path": ".../uploads/logo/logo.png",
      "logo_position": "top_right",
      "logo_size": 150,
      "logo_opacity": 0.8,
      "logo_margin": 40,
      "audio_mode": "keep",
      "audio_volume": 1.0,
      "quality": "medium",
      "use_gpu": false,
      "trim_segments": [
        {"start": "00:00:10", "end": "00:00:30"}
      ]
    }
  }
  ```
- **Response (200 OK):** `{"job_id": "a1b2c3d4e5f6"}`

### `POST /slideshow`
Starts a slideshow creation job from ordered images.
- **Content-Type:** `application/json`
- **Body:**
  ```json
  {
    "files": [".../img1.jpg", ".../img2.jpg"],
    "settings": {
      "fps": 30,
      "img_duration": 3.0,
      "transition_duration": 0.8,
      "transition": "fade",
      "transitions": ["wipeleft"],
      "orientation": "landscape",
      "output_name": "vacation_slideshow",
      "quality": "medium"
    }
  }
  ```
- **Response (200 OK):** `{"job_id": "f6e5d4c3b2a1"}`

### `GET /job/<jid>`
Polls real-time execution progress, status, and log messages.
- **Response (200 OK):**
  ```json
  {
    "status": "processing",
    "progress": 45,
    "current_item": 1,
    "total_items": 2,
    "item_pct": 90,
    "eta": 15,
    "logs": [
      {"ts": "20:30:00", "msg": "Job started", "level": "info"}
    ],
    "outputs": []
  }
  ```

### `POST /job/<jid>/cancel`
Cancels an ongoing job and terminates the associated FFmpeg subprocess.
- **Response (200 OK):** `{"ok": true}`

### `GET /jobs`
Returns a summary map of all tracked jobs.
- **Response (200 OK):**
  ```json
  {
    "jobs": {
      "a1b2c3d4e5f6": {
        "status": "done",
        "progress": 100,
        "type": "video",
        "outputs_count": 1
      }
    }
  }
  ```
