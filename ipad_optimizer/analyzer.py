"""Storage analysis: directory sizes, large files, duplicates."""

import hashlib
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


@dataclass
class FileInfo:
    path: Path
    size: int
    ext: str


@dataclass
class AnalysisReport:
    root: Path
    total_size: int = 0
    file_count: int = 0
    dir_sizes: dict = field(default_factory=dict)
    large_files: list = field(default_factory=list)
    duplicates: list = field(default_factory=list)  # list of duplicate groups


def _iter_files(root: Path, skip_exts: set) -> Iterator[FileInfo]:
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix in skip_exts:
                continue
            try:
                size = p.stat().st_size
                yield FileInfo(path=p, size=size, ext=p.suffix.lower())
            except (OSError, PermissionError):
                continue


def _file_hash(path: Path, chunk: int = 65536) -> str:
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            while True:
                block = f.read(chunk)
                if not block:
                    break
                h.update(block)
    except (OSError, PermissionError):
        return ""
    return h.hexdigest()


def analyze(root: str, cfg: dict) -> AnalysisReport:
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Path not found: {root_path}")

    report = AnalysisReport(root=root_path)
    skip_exts = set(cfg.get("extensions_to_skip", []))
    large_threshold = cfg.get("large_file_threshold", 100 * 1024 * 1024)
    min_dup_size = cfg.get("min_duplicate_size", 10 * 1024)

    size_by_dir: dict[str, int] = defaultdict(int)
    by_size: dict[int, list[Path]] = defaultdict(list)

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        task = progress.add_task("Analizando archivos...", total=None)

        for fi in _iter_files(root_path, skip_exts):
            report.total_size += fi.size
            report.file_count += 1
            dir_key = str(fi.path.parent)
            size_by_dir[dir_key] += fi.size
            if fi.size >= large_threshold:
                report.large_files.append((fi.path, fi.size))
            if fi.size >= min_dup_size:
                by_size[fi.size].append(fi.path)

        progress.update(task, description="Buscando duplicados...")

        # Group candidates by hash
        hash_groups: dict[str, list[Path]] = defaultdict(list)
        candidates = [paths for paths in by_size.values() if len(paths) > 1]
        for group in candidates:
            for p in group:
                h = _file_hash(p)
                if h:
                    hash_groups[h].append(p)

    report.large_files.sort(key=lambda x: x[1], reverse=True)
    report.duplicates = [paths for paths in hash_groups.values() if len(paths) > 1]

    # Top 10 heaviest directories
    top_dirs = sorted(size_by_dir.items(), key=lambda x: x[1], reverse=True)[:10]
    report.dir_sizes = dict(top_dirs)

    return report


def format_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
