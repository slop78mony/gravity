"""Main CLI entry point."""

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .analyzer import analyze, format_bytes
from .cleaner import clean_duplicates, clean_temp
from .cloud_sync import list_drive_files, sync_to_drive
from .config import load_config, save_config
from .monitor import check_once, show_history, start_monitor

console = Console()


@click.group()
@click.version_option()
def cli():
    """iPad Storage Optimizer — analiza, limpia y sincroniza tu almacenamiento."""


# ── analyze ──────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("path", default=".")
@click.option("--top", default=20, show_default=True, help="Número de archivos grandes a mostrar.")
def analyze_cmd(path: str, top: int):
    """Analiza el almacenamiento en PATH y muestra un resumen."""
    cfg = load_config()
    try:
        report = analyze(path, cfg)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    console.rule("[bold]Resumen de almacenamiento[/bold]")
    console.print(f"Ruta analizada : [cyan]{report.root}[/cyan]")
    console.print(f"Archivos totales: [bold]{report.file_count:,}[/bold]")
    console.print(f"Tamaño total   : [bold]{format_bytes(report.total_size)}[/bold]")

    # Top directories
    if report.dir_sizes:
        table = Table(title="Directorios más pesados", show_lines=False)
        table.add_column("Directorio", style="cyan", overflow="fold")
        table.add_column("Tamaño", justify="right", style="magenta")
        for d, s in list(report.dir_sizes.items())[:10]:
            table.add_row(d, format_bytes(s))
        console.print(table)

    # Large files
    if report.large_files:
        table = Table(title=f"Archivos grandes (top {top})", show_lines=False)
        table.add_column("Archivo", style="cyan", overflow="fold")
        table.add_column("Tamaño", justify="right", style="red")
        for p, s in report.large_files[:top]:
            table.add_row(str(p), format_bytes(s))
        console.print(table)
    else:
        console.print("[green]No se encontraron archivos grandes.[/green]")

    # Duplicates summary
    dup_count = sum(len(g) - 1 for g in report.duplicates)
    dup_size = sum(
        sum(f.stat().st_size for f in g[1:] if f.exists()) for g in report.duplicates
    )
    console.print(
        f"\nDuplicados encontrados: [bold yellow]{dup_count}[/bold yellow] "
        f"({format_bytes(dup_size)} recuperables)"
    )
    console.print("\nUsa [bold]ipad-optimizer clean[/bold] para liberar espacio.")


# ── clean ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("path", default=".")
@click.option("--duplicates", is_flag=True, help="Eliminar duplicados.")
@click.option("--temp", is_flag=True, help="Eliminar archivos temporales.")
@click.option("--all", "clean_all", is_flag=True, help="Ejecutar todos los tipos de limpieza.")
@click.option("--dry-run/--no-dry-run", default=True, show_default=True,
              help="Simular sin borrar archivos reales.")
def clean(path: str, duplicates: bool, temp: bool, clean_all: bool, dry_run: bool):
    """Elimina archivos duplicados y temporales en PATH."""
    cfg = load_config()
    root = Path(path).expanduser().resolve()

    if not root.exists():
        console.print(f"[red]Error:[/red] Ruta no encontrada: {root}")
        sys.exit(1)

    if clean_all:
        duplicates = temp = True

    if not duplicates and not temp:
        console.print("[yellow]Especifica --duplicates, --temp o --all.[/yellow]")
        sys.exit(1)

    if dry_run:
        console.print("[yellow]Modo simulación (--dry-run). Usa --no-dry-run para borrar.[/yellow]\n")

    total_freed = 0

    if duplicates:
        console.rule("[bold]Limpieza de duplicados[/bold]")
        report = analyze(path, cfg)
        _, freed = clean_duplicates(report, dry_run=dry_run)
        total_freed += freed

    if temp:
        console.rule("[bold]Limpieza de archivos temporales[/bold]")
        patterns = cfg.get("temp_patterns", [])
        _, freed = clean_temp(root, patterns, dry_run=dry_run)
        total_freed += freed

    console.print(f"\n[bold]Total liberado: {format_bytes(total_freed)}[/bold]")


# ── monitor ───────────────────────────────────────────────────────────────────

@cli.group()
def monitor():
    """Monitoreo continuo del almacenamiento."""


@monitor.command("start")
@click.argument("path", default="/")
@click.option("--interval", default=None, type=int, help="Intervalo en segundos (default: config).")
def monitor_start(path: str, interval: int | None):
    """Inicia el monitor de almacenamiento para PATH."""
    cfg = load_config()
    start_monitor(path, cfg, interval)


@monitor.command("check")
@click.argument("path", default="/")
def monitor_check(path: str):
    """Muestra el uso actual del almacenamiento en PATH."""
    cfg = load_config()
    check_once(path, cfg)


@monitor.command("history")
@click.argument("path", default=None, required=False)
def monitor_history(path: str | None):
    """Muestra el historial de uso registrado."""
    show_history(path)


# ── sync ──────────────────────────────────────────────────────────────────────

@cli.group()
def sync():
    """Sincronización con Google Drive."""


@sync.command("upload")
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--folder", default="iPad Backup", show_default=True, help="Carpeta en Drive.")
@click.option("--delete", is_flag=True, help="Eliminar archivos locales tras subir.")
@click.option("--dry-run/--no-dry-run", default=True, show_default=True)
def sync_upload(files: tuple, folder: str, delete: bool, dry_run: bool):
    """Sube FILES a Google Drive."""
    paths = [Path(f) for f in files]
    if dry_run:
        console.print("[yellow]Modo simulación (--dry-run). Usa --no-dry-run para subir.[/yellow]\n")
    sync_to_drive(paths, folder_name=folder, delete_after=delete, dry_run=dry_run)


@sync.command("large")
@click.argument("path", default=".")
@click.option("--folder", default="iPad Backup", show_default=True)
@click.option("--delete", is_flag=True, help="Eliminar archivos locales tras subir.")
@click.option("--dry-run/--no-dry-run", default=True, show_default=True)
def sync_large(path: str, folder: str, delete: bool, dry_run: bool):
    """Sube los archivos grandes de PATH a Google Drive."""
    cfg = load_config()
    report = analyze(path, cfg)
    paths = [p for p, _ in report.large_files]
    if dry_run:
        console.print("[yellow]Modo simulación (--dry-run). Usa --no-dry-run para subir.[/yellow]\n")
    sync_to_drive(paths, folder_name=folder, delete_after=delete, dry_run=dry_run)


@sync.command("list")
@click.option("--folder", default="iPad Backup", show_default=True)
def sync_list(folder: str):
    """Lista los archivos ya subidos a Drive."""
    list_drive_files(folder)


# ── config ────────────────────────────────────────────────────────────────────

@cli.command("config")
@click.option("--alert-threshold", type=int, help="Porcentaje de uso para alertas (0-100).")
@click.option("--large-file-mb", type=int, help="Umbral para 'archivo grande' en MB.")
@click.option("--monitor-interval", type=int, help="Intervalo de monitoreo en segundos.")
@click.option("--show", is_flag=True, help="Mostrar configuración actual.")
def config_cmd(alert_threshold, large_file_mb, monitor_interval, show):
    """Gestiona la configuración de la herramienta."""
    cfg = load_config()

    if show or not any([alert_threshold, large_file_mb, monitor_interval]):
        table = Table(title="Configuración actual")
        table.add_column("Clave", style="cyan")
        table.add_column("Valor", style="green")
        for k, v in cfg.items():
            table.add_row(k, str(v))
        console.print(table)
        return

    if alert_threshold is not None:
        cfg["alert_threshold_percent"] = alert_threshold
    if large_file_mb is not None:
        cfg["large_file_threshold"] = large_file_mb * 1024 * 1024
    if monitor_interval is not None:
        cfg["monitor_interval"] = monitor_interval

    save_config(cfg)
    console.print("[green]Configuración guardada.[/green]")


def main():
    cli()
