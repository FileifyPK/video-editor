# Contributing to Video Editor

Thank you for helping improve Video Editor!

## Development Setup

1. Clone the repository and navigate into the root directory.
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Or on Windows: .venv\Scripts\activate
   ```
3. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

## Running Tests & Checks

Before submitting changes, ensure the test suite passes:
```bash
ruff check .
pytest -q
```

## Pull Request Checklist

- Ensure new or changed functionality includes corresponding automated tests in `tests/`.
- Do not commit private media files (`.mp4`, `.mov`, `.png`, etc.) or personal configuration files.
- Keep commits focused and descriptive using conventional commit prefixes (`feat:`, `fix:`, `docs:`, `test:`).
