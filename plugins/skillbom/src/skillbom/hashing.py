"""Content hash of a skill/plugin directory (procedure in docs/license-file.md)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

EXCLUDED_DIRS = {".git", "node_modules"}
EXCLUDED_FILES = {".DS_Store", "skill-license.yaml", "skill-license.yml", "skill-license.json"}


def content_hash(root: Path) -> str:
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in filenames:
            p = Path(dirpath, name)
            if name in EXCLUDED_FILES or p.is_symlink() or not p.is_file():
                continue
            files.append(p.relative_to(root).as_posix())
    digest = hashlib.sha256()
    for rel in sorted(files, key=lambda s: s.encode()):
        file_hash = hashlib.sha256((root / rel).read_bytes()).hexdigest()
        digest.update(f"{rel}\0{file_hash}\n".encode())
    return digest.hexdigest()
