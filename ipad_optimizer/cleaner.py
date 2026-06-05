"""File cleanup: remove duplicates, temp files, and cache."""

import fnmatch
import os
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .analyzer import AnalysisReport, format_bytes

console = Console()


def find_temp_files(root: Path, patterns: list[str]) -> list[Path]:
    found = []
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            for pat in patterns:
                if fnmatch.fnmatch(name, pat):
                    found.append(Path(dirpath) / name)
                    break
    return found


def remove_files(paths: list[Path], dry_run: bool = True) -> tuple[int, int]:
    """Returns (removed_count, freed_bytes)."""
    removed, freed = 0, 0
    for p in paths:
        try:
            size = p.stat().st_size
            if not dry_run:
                p.unlink()
            removed += 1
            freed += size
        except (OSError, PermissionError) as e:
            console.print(f"[yellow]Advertencia:[/yellow] No se pudo eliminar {p}: {e}")
    return removed, freed


def clean_duplicates(report: AnalysisReport, dry_run: bool = True) -> tuple[int, int]:
    """Keep the first file in each duplicate group, remove the rest."""
    to_remove: list[Path] = []
    for group in report.duplicates:
        # Keep the file with the shortest path (likely the original)
        keeper = min(group, key=lambda p: len(str(p)))
        to_remove.extend(f for f in group if f != keeper)

    if not to_remove:
        console.print("[green]No se encontraron duplicados para eliminar.[/green]")
        return 0, 0

    _print_removal_table(to_remove, "Archivos duplicados a eliminar")
    removed, freed = remove_files(to_remove, dry_run)
    _print_result(removed, freed, dry_run)
    return removed, freed


def clean_temp(root: Path, patterns: list[str], dry_run: bool = True) -> tuple[int, int]:
    temp_files = find_temp_files(root, patterns)

    if not temp_files:
        console.print("[green]No se encontraron archivos temporales.[/green]")
        return 0, 0

    _print_removal_table(temp_files, "Archivos temporales a eliminar")
    removed, freed = remove_files(temp_files, dry_run)
    _print_result(removed, freed, dry_run)
    return removed, freed


def _print_removal_table(paths: list[Path], title: str) -> None:
    table = Table(title=title, show_lines=False)
    table.add_column("Archivo", style="cyan", overflow="fold")
    table.add_column("Tamaño", justify="right", style="red")
    for p in paths[:50]:
        try:
            size = format_bytes(p.stat().st_size)
        except OSError:
            size = "?"
        table.add_row(str(p), size)
    if len(paths) > 50:
        table.add_row(f"... y {len(paths) - 50} más", "")
    console.print(table)


def _print_result(removed: int, freed: int, dry_run: bool) -> None:
    action = "[yellow](simulación)[/yellow]" if dry_run else "[green](ejecutado)[/green]"
    console.print(
        f"\n{action} {removed} archivo(s) — "
        f"[bold]{format_bytes(freed)}[/bold] liberados"
    )
