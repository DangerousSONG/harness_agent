# tools/base_tools.py

from pathlib import Path
import subprocess


def safe_path(workdir: Path, p: str) -> Path:
    """
    Resolve a user-provided path inside the workspace.
    Prevent path traversal outside the workspace.
    """
    workdir = workdir.resolve()
    path = (workdir / p).resolve()

    try:
        path.relative_to(workdir)
    except ValueError:
        raise ValueError(f"Path escapes workspace: {p}")

    return path


def run_bash(workdir: Path, command: str) -> str:
    dangerous = [
        "rm -rf /",
        "sudo",
        "shutdown",
        "reboot",
        "> /dev/",
    ]

    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"

    try:
        r = subprocess.run(
            command,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )

        stdout = r.stdout or ""
        stderr = r.stderr or ""

        out = (stdout + stderr).strip()
        return out[:50000] if out else "(no output)"

    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except Exception as e:
        return f"Error: {e}"


def run_read(workdir: Path, path: str, limit: int | None = None) -> str:
    try:
        fp = safe_path(workdir, path)
        lines = fp.read_text(encoding="utf-8").splitlines()

        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]

        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"


def run_write(workdir: Path, path: str, content: str) -> str:
    try:
        fp = safe_path(workdir, path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


def run_edit(workdir: Path, path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(workdir, path)
        c = fp.read_text(encoding="utf-8")

        if old_text not in c:
            return f"Error: Text not found in {path}"

        fp.write_text(c.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"