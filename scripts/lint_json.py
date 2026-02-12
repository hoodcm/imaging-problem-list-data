"""Lint JSON files in the repository.

Checks:
- valid UTF-8
- valid JSON syntax
- no duplicate object keys
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def _object_pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    duplicates: list[str] = []

    for key, value in pairs:
        if key in result:
            duplicates.append(key)
        result[key] = value

    if duplicates:
        duplicate_list = ", ".join(sorted(set(duplicates)))
        raise ValueError(f"duplicate keys: {duplicate_list}")

    return result


def _tracked_json_files() -> list[Path]:
    try:
        completed = subprocess.run(
            ["git", "ls-files", "*.json"],
            check=True,
            capture_output=True,
            text=True,
        )
        files = [Path(line) for line in completed.stdout.splitlines() if line.strip()]
        return sorted(files)
    except (FileNotFoundError, subprocess.CalledProcessError):
        root = Path(".")
        files = [
            path
            for path in root.rglob("*.json")
            if ".git" not in path.parts and "node_modules" not in path.parts and ".venv" not in path.parts
        ]
        return sorted(files)


def main() -> int:
    files = _tracked_json_files()
    if not files:
        print("No JSON files found.")
        return 0

    errors: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
            json.loads(text, object_pairs_hook=_object_pairs_no_duplicates)
        except UnicodeDecodeError as exc:
            errors.append(f"{path}: invalid UTF-8 ({exc})")
        except json.JSONDecodeError as exc:
            errors.append(f"{path}:{exc.lineno}:{exc.colno}: {exc.msg}")
        except ValueError as exc:
            errors.append(f"{path}: {exc}")

    if errors:
        print("JSON lint failed:")
        for error in errors:
            print(f"- {error}")
        print(f"\nChecked {len(files)} JSON files; found {len(errors)} issue(s).")
        return 1

    print(f"JSON lint passed ({len(files)} files checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
