#!/usr/bin/env python3
"""Validate local hardware configuration files before launching sensors."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PLACEHOLDER_PATTERNS = (
    re.compile(r"YOUR_"),
    re.compile(r"192\.168\.x\.x"),
    re.compile(r'"ip"\s*:\s*""'),
    re.compile(r'"cmd_data_ip"\s*:\s*""'),
)


def validate_file(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"missing file: {path}"]
    text = path.read_text(encoding="utf-8", errors="replace")
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.search(text):
            errors.append(f"{path}: contains placeholder or empty runtime value matching {pattern.pattern}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local Livox/Hikrobot configuration files.")
    parser.add_argument("configs", nargs="+", type=Path)
    args = parser.parse_args()

    errors: list[str] = []
    for config in args.configs:
        errors.extend(validate_file(config))

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("local hardware config validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
