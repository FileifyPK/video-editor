# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-11

### Added
- Multi-section video trimming and automatic segment rejoining.
- Image slideshow creation engine supporting 36 hardware/software transitions via FFmpeg xfade.
- Custom logo watermark overlay with five position anchors (Top Left, Top Right, Bottom Left, Bottom Right, Center), size, opacity, and margin controls.
- Audio management modes: retain original audio with volume adjustment, mute, audio track replacement, and multi-track background mixing.
- GPU acceleration option utilizing NVIDIA NVENC (`h264_nvenc`).
- Real-time progress bars, live log streaming, and job cancellation support.
- Loopback-by-default network binding (`127.0.0.1`) and path traversal protection against arbitrary file access.
- Cross-platform launch scripts (`start.bat` for Windows, `start.sh` for Linux/macOS) and Docker support.
- Automated unit, security, identity, and FFmpeg integration test suites.
