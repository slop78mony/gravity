"""Continuous storage monitoring with configurable alerts."""

import json
import shutil
import time
from datetime import datetime
from pathlib import Path

import schedule
from rich.console import Console
from rich.live import Live
from rich.table import Table

from .analyzer import format_bytes
from .config import HISTORY_FILE, CONFIG_DIR

console = Console()


def _get_disk_usage(path: str) -> tuple[int, int, int]:
    """Returns (total, used, free) in bytes."""
    usage = shutil.disk_usage(path)
    return usage.total, usage.used, usage.free


def _load_history() -> list[dict]:
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return []


def _save_snapshot(path: str, total: int, used: int, free: int) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    history = _load_history()
    history.append(
        {
            "ts": datetime.now().isoformat(),
            "path": path,
            "total": total,
            "used": used,
            "free": free,
        }
    )
    # Keep last 1000 entries
    history = history[-1000:]
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def _usage_table(path: str, total: int, used: int, free: int, threshold: int) -> Table:
    pct = used / total * 100 if total else 0
    color = "red" if pct >= threshold else "yellow" if pct >= threshold * 0.9 else "green"

    table = Table(title=f"Uso de almacenamiento — {path}", show_header=False)
    table.add_column("Campo", style="bold")
    table.add_column("Valor")
    table.add_row("Total", format_bytes(total))
    table.add_row("Usado", f"[{color}]{format_bytes(used)} ({pct:.1f}%)[/{color}]")
    table.add_row("Libre", format_bytes(free))
    table.add_row("Actualizado", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return table


def check_once(path: str, cfg: dict) -> None:
    total, used, free = _get_disk_usage(path)
    threshold = cfg.get("alert_threshold_percent", 85)
    _save_snapshot(path, total, used, free)
    console.print(_usage_table(path, total, used, free, threshold))

    pct = used / total * 100 if total else 0
    if pct >= threshold:
        console.print(
            f"\n[bold red]ALERTA:[/bold red] Almacenamiento al {pct:.1f}% "
            f"(umbral: {threshold}%). ¡Considera liberar espacio!"
        )


def start_monitor(path: str, cfg: dict, interval: int | None = None) -> None:
    interval_secs = interval or cfg.get("monitor_interval", 3600)
    threshold = cfg.get("alert_threshold_percent", 85)
    console.print(
        f"[bold]Monitor iniciado[/bold] — revisando cada {interval_secs}s "
        f"(umbral de alerta: {threshold}%)\n"
        "Presiona [bold]Ctrl+C[/bold] para detener.\n"
    )

    def job():
        total, used, free = _get_disk_usage(path)
        _save_snapshot(path, total, used, free)
        pct = used / total * 100 if total else 0
        console.print(_usage_table(path, total, used, free, threshold))
        if pct >= threshold:
            console.print(
                f"[bold red]ALERTA:[/bold red] {pct:.1f}% usado — ¡libera espacio!"
            )

    job()
    schedule.every(interval_secs).seconds.do(job)

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Monitor detenido.[/yellow]")


def show_history(path: str | None = None) -> None:
    history = _load_history()
    if not history:
        console.print("[yellow]Sin historial registrado aún.[/yellow]")
        return

    if path:
        history = [e for e in history if e["path"] == path]

    table = Table(title="Historial de almacenamiento")
    table.add_column("Fecha/Hora", style="cyan")
    table.add_column("Ruta")
    table.add_column("Total", justify="right")
    table.add_column("Usado", justify="right")
    table.add_column("Libre", justify="right")
    table.add_column("%", justify="right")

    for entry in history[-20:]:
        pct = entry["used"] / entry["total"] * 100 if entry["total"] else 0
        color = "red" if pct >= 85 else "yellow" if pct >= 70 else "green"
        table.add_row(
            entry["ts"][:19],
            entry["path"],
            format_bytes(entry["total"]),
            format_bytes(entry["used"]),
            format_bytes(entry["free"]),
            f"[{color}]{pct:.1f}%[/{color}]",
        )

    console.print(table)
