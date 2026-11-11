import subprocess
from pathlib import Path


def test_no_forbidden_branding_in_repository():
    """Ensure legacy branding words never appear in the codebase.

    Target tokens are assembled from joined fragments so this test file itself
    does not trigger a false positive.
    """
    token1 = "".join(["w", "i", "s", "d", "o", "m"])
    token2 = "".join(["l", "a", "y", "e", "r", "s"])
    token3 = "".join(["w", "l", "v", "p"])

    forbidden_tokens = [token1, token2, token3]

    repo_root = Path(__file__).parent.parent.resolve()

    # Get list of tracked git files or all files if git not available
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True
        )
        files_to_check = [repo_root / p for p in res.stdout.splitlines() if p.strip()]
    except Exception:
        files_to_check = [
            p for p in repo_root.rglob("*")
            if p.is_file() and not any(part.startswith(".") for part in p.parts)
        ]

    violations = []
    text_extensions = {".py", ".html", ".js", ".css", ".md", ".txt", ".bat", ".sh", ".yml", ".yaml", ".json", ".toml"}

    for f in files_to_check:
        if not f.exists() or f.suffix.lower() not in text_extensions:
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore").lower()
            for tok in forbidden_tokens:
                if tok in content:
                    violations.append(f"{f.relative_to(repo_root)} contains forbidden token '{tok}'")
        except Exception:
            pass

    assert not violations, "Branding violations found:\n" + "\n".join(violations)
