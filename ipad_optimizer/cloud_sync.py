"""Cloud synchronization with Google Drive to free local storage."""

import os
import pickle
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeRemainingColumn

console = Console()

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_FILE = Path.home() / ".ipad_optimizer" / "gdrive_token.pickle"
CREDENTIALS_FILE = Path.home() / ".ipad_optimizer" / "credentials.json"


def _get_drive_service():
    """Authenticate and return a Google Drive service object."""
    try:
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        console.print(
            "[red]Error:[/red] Instala las dependencias con:\n"
            "  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        )
        raise SystemExit(1)

    creds = None
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                console.print(
                    f"[red]Error:[/red] No se encontró {CREDENTIALS_FILE}.\n"
                    "Descarga tus credenciales OAuth desde Google Cloud Console y "
                    f"guárdalas en {CREDENTIALS_FILE}"
                )
                raise SystemExit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("drive", "v3", credentials=creds)


def _upload_file(service, local_path: Path, folder_id: str | None = None) -> str:
    """Upload a file to Drive, return the file ID."""
    from googleapiclient.http import MediaFileUpload

    metadata = {"name": local_path.name}
    if folder_id:
        metadata["parents"] = [folder_id]

    media = MediaFileUpload(str(local_path), resumable=True)
    result = service.files().create(body=metadata, media_body=media, fields="id").execute()
    return result.get("id", "")


def _get_or_create_folder(service, name: str) -> str:
    """Return the Drive folder ID, creating it if needed."""
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def sync_to_drive(
    paths: list[Path],
    folder_name: str = "iPad Backup",
    delete_after: bool = False,
    dry_run: bool = True,
) -> tuple[int, int]:
    """
    Upload files to Google Drive.
    Returns (uploaded_count, freed_bytes).
    """
    if not paths:
        console.print("[yellow]No hay archivos para sincronizar.[/yellow]")
        return 0, 0

    if dry_run:
        console.print(
            f"[yellow](Simulación)[/yellow] Se subirían {len(paths)} archivo(s) "
            f"a Google Drive / {folder_name}"
        )
        total = sum(p.stat().st_size for p in paths if p.exists())
        from .analyzer import format_bytes
        console.print(f"Espacio a liberar: [bold]{format_bytes(total)}[/bold]")
        return 0, 0

    service = _get_drive_service()
    folder_id = _get_or_create_folder(service, folder_name)

    uploaded, freed = 0, 0

    with Progress(
        TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Subiendo...", total=len(paths), filename="")

        for p in paths:
            progress.update(task, filename=p.name)
            try:
                _upload_file(service, p, folder_id)
                size = p.stat().st_size
                uploaded += 1
                freed += size
                if delete_after:
                    p.unlink()
            except Exception as e:
                console.print(f"[red]Error subiendo {p.name}:[/red] {e}")
            finally:
                progress.advance(task)

    from .analyzer import format_bytes
    action = "subidos y eliminados localmente" if delete_after else "subidos (copia local conservada)"
    console.print(f"\n[green]{uploaded} archivo(s) {action}.[/green]")
    console.print(f"Espacio liberado: [bold]{format_bytes(freed)}[/bold]")
    return uploaded, freed


def list_drive_files(folder_name: str = "iPad Backup") -> None:
    """List files already uploaded to Drive."""
    service = _get_drive_service()
    folder_id = _get_or_create_folder(service, folder_name)

    query = f"'{folder_id}' in parents and trashed=false"
    results = service.files().list(
        q=query, fields="files(name, size, modifiedTime)", orderBy="modifiedTime desc"
    ).execute()
    files = results.get("files", [])

    if not files:
        console.print(f"[yellow]No hay archivos en Drive / {folder_name}.[/yellow]")
        return

    from rich.table import Table
    from .analyzer import format_bytes

    table = Table(title=f"Google Drive / {folder_name}")
    table.add_column("Nombre", style="cyan")
    table.add_column("Tamaño", justify="right")
    table.add_column("Modificado", style="dim")

    for f in files:
        size = format_bytes(int(f.get("size", 0)))
        table.add_row(f["name"], size, f.get("modifiedTime", "")[:10])

    console.print(table)
