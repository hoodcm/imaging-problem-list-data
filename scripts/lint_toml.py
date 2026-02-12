"""Lint TOML files in the repository."""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path


def _tracked_toml_files() -> list[Path]:
    patterns = ["*.toml", "*.toml.example"]
    try:
        completed = subprocess.run(
            ["git", "ls-files", *patterns],
            check=True,
            capture_output=True,
            text=True,
        )
        return sorted(Path(line) for line in completed.stdout.splitlines() if line.strip())
    except (FileNotFoundError, subprocess.CalledProcessError):
        root = Path(".")
        files: set[Path] = set()
        for pattern in patterns:
            files.update(root.rglob(pattern))
        return sorted(
            path
            for path in files
            if ".git" not in path.parts and "node_modules" not in path.parts and ".venv" not in path.parts
        )


def main() -> int:
    files = _tracked_toml_files()
    if not files:
        print("No TOML files found.")
        return 0

    errors: list[str] = []
    for path in files:
        try:
            data = path.read_text(encoding="utf-8")
            tomllib.loads(data)
        except UnicodeDecodeError as exc:
            errors.append(f"{path}: invalid UTF-8 ({exc})")
        except tomllib.TOMLDecodeError as exc:
            errors.append(f"{path}: {exc}")

    if errors:
        print("TOML lint failed:")
        for error in errors:
            print(f"- {error}")
        print(f"\nChecked {len(files)} TOML files; found {len(errors)} issue(s).")
        return 1

    print(f"TOML lint passed ({len(files)} files checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
