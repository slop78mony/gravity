#!/usr/bin/env python3
"""
Optimización autónoma del iPad.
Ejecuta análisis, limpieza y envía reporte por email al terminar.

Uso:
    python auto_optimize.py --path ~/Library/Mobile\ Documents --email tu@gmail.com
    python auto_optimize.py --path /Volumes/MiIPad --email tu@gmail.com --clean
"""

import argparse
import json
import platform
import smtplib
import subprocess
import sys
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# Asegura que el paquete sea encontrado si se ejecuta desde scripts/
sys.path.insert(0, str(Path(__file__).parent.parent))

from ipad_optimizer.analyzer import analyze, format_bytes
from ipad_optimizer.cleaner import clean_duplicates, clean_temp
from ipad_optimizer.config import load_config
from ipad_optimizer.monitor import _get_disk_usage, _save_snapshot


# ── Detección del iPad ────────────────────────────────────────────────────────

def detect_ipad_path() -> str | None:
    """Intenta detectar el path de montaje del iPad automáticamente."""
    system = platform.system()

    if system == "Darwin":  # macOS
        # Volúmenes montados vía ifuse o AFC
        volumes = Path("/Volumes")
        if volumes.exists():
            for vol in volumes.iterdir():
                if "ipad" in vol.name.lower() or "iphone" in vol.name.lower():
                    return str(vol)

        # iCloud Drive (siempre disponible en Mac)
        icloud = Path.home() / "Library" / "Mobile Documents"
        if icloud.exists():
            return str(icloud)

        # Backup de iTunes
        backup = Path.home() / "Library" / "Application Support" / "MobileSync" / "Backup"
        if backup.exists() and any(backup.iterdir()):
            return str(backup)

    elif system == "Windows":
        backup = Path.home() / "AppData" / "Roaming" / "Apple Computer" / "MobileSync" / "Backup"
        if backup.exists() and any(backup.iterdir()):
            return str(backup)

        icloud = Path.home() / "iCloudDrive"
        if icloud.exists():
            return str(icloud)

    elif system == "Linux":
        # ifuse mount point común
        for candidate in [Path.home() / "iPad", Path("/mnt/ipad"), Path("/media/ipad")]:
            if candidate.exists():
                return str(candidate)

    return None


def wait_for_ipad(timeout: int = 120) -> str | None:
    """Espera hasta que el iPad esté disponible. Devuelve el path o None."""
    print(f"[{_ts()}] Esperando iPad... (timeout: {timeout}s)")
    deadline = time.time() + timeout
    while time.time() < deadline:
        path = detect_ipad_path()
        if path:
            print(f"[{_ts()}] iPad detectado en: {path}")
            return path
        time.sleep(5)
    print(f"[{_ts()}] Timeout: iPad no detectado.")
    return None


# ── Reporte ───────────────────────────────────────────────────────────────────

def build_report(path: str, cfg: dict, cleaned: bool) -> dict:
    """Ejecuta análisis (y limpieza si se pide) y devuelve un dict con resultados."""
    report = {}
    start = time.time()

    print(f"[{_ts()}] Analizando {path}...")
    analysis = analyze(path, cfg)

    report["path"] = path
    report["timestamp"] = datetime.now().isoformat()
    report["total_size"] = format_bytes(analysis.total_size)
    report["file_count"] = analysis.file_count
    report["large_files"] = [(str(p), format_bytes(s)) for p, s in analysis.large_files[:10]]
    report["duplicate_groups"] = len(analysis.duplicates)
    report["duplicate_recoverable"] = format_bytes(
        sum(
            sum(f.stat().st_size for f in g[1:] if f.exists())
            for g in analysis.duplicates
        )
    )

    total_disk, used_disk, free_disk = _get_disk_usage(path)
    _save_snapshot(path, total_disk, used_disk, free_disk)
    report["disk_total"] = format_bytes(total_disk)
    report["disk_used"] = format_bytes(used_disk)
    report["disk_free"] = format_bytes(free_disk)
    report["disk_pct"] = f"{used_disk / total_disk * 100:.1f}%" if total_disk else "?"

    freed_total = 0
    if cleaned:
        print(f"[{_ts()}] Limpiando duplicados...")
        _, freed_dup = clean_duplicates(analysis, dry_run=False)
        print(f"[{_ts()}] Limpiando archivos temporales...")
        patterns = cfg.get("temp_patterns", [])
        _, freed_tmp = clean_temp(Path(path), patterns, dry_run=False)
        freed_total = freed_dup + freed_tmp

    report["freed"] = format_bytes(freed_total)
    report["duration_sec"] = round(time.time() - start, 1)
    return report


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(to: str, report: dict, smtp_user: str, smtp_pass: str) -> None:
    """Envía el reporte por email vía Gmail SMTP."""
    subject = f"✅ iPad Optimizer — reporte {datetime.now().strftime('%d/%m/%Y %H:%M')}"

    large_rows = "".join(
        f"<tr><td style='padding:4px 8px'>{name}</td>"
        f"<td style='padding:4px 8px;text-align:right'>{size}</td></tr>"
        for name, size in report["large_files"]
    ) or "<tr><td colspan='2' style='padding:4px 8px'>Ninguno</td></tr>"

    html = f"""
    <html><body style='font-family:sans-serif;color:#222'>
    <h2 style='color:#1a73e8'>iPad Storage Optimizer</h2>
    <p>Optimización completada el <b>{report['timestamp'][:19].replace('T',' ')}</b></p>

    <table style='border-collapse:collapse;margin-bottom:16px'>
      <tr><th colspan='2' style='background:#1a73e8;color:white;padding:6px 12px;text-align:left'>
        Resumen del disco
      </th></tr>
      <tr style='background:#f1f3f4'><td style='padding:4px 12px'>Ruta analizada</td>
        <td style='padding:4px 12px'><code>{report['path']}</code></td></tr>
      <tr><td style='padding:4px 12px'>Archivos escaneados</td>
        <td style='padding:4px 12px'>{report['file_count']:,}</td></tr>
      <tr style='background:#f1f3f4'><td style='padding:4px 12px'>Tamaño total</td>
        <td style='padding:4px 12px'>{report['total_size']}</td></tr>
      <tr><td style='padding:4px 12px'>Disco total</td>
        <td style='padding:4px 12px'>{report['disk_total']}</td></tr>
      <tr style='background:#f1f3f4'><td style='padding:4px 12px'>Disco usado</td>
        <td style='padding:4px 12px'>{report['disk_used']} ({report['disk_pct']})</td></tr>
      <tr><td style='padding:4px 12px'>Disco libre</td>
        <td style='padding:4px 12px'>{report['disk_free']}</td></tr>
    </table>

    <table style='border-collapse:collapse;margin-bottom:16px'>
      <tr><th colspan='2' style='background:#34a853;color:white;padding:6px 12px;text-align:left'>
        Limpieza
      </th></tr>
      <tr style='background:#f1f3f4'><td style='padding:4px 12px'>Grupos de duplicados</td>
        <td style='padding:4px 12px'>{report['duplicate_groups']}</td></tr>
      <tr><td style='padding:4px 12px'>Espacio recuperable</td>
        <td style='padding:4px 12px'>{report['duplicate_recoverable']}</td></tr>
      <tr style='background:#f1f3f4'><td style='padding:4px 12px'>Espacio liberado</td>
        <td style='padding:4px 12px'><b style='color:#34a853'>{report['freed']}</b></td></tr>
    </table>

    <table style='border-collapse:collapse;margin-bottom:16px'>
      <tr><th colspan='2' style='background:#ea4335;color:white;padding:6px 12px;text-align:left'>
        Archivos grandes (top 10)
      </th></tr>
      {large_rows}
    </table>

    <p style='color:#666;font-size:12px'>
      Duración: {report['duration_sec']}s &nbsp;|&nbsp;
      iPad Optimizer v1.0.0
    </p>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, to, msg.as_string())

    print(f"[{_ts()}] Reporte enviado a {to}")


def save_report_json(report: dict) -> Path:
    out = Path.home() / ".ipad_optimizer" / "last_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return out


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Optimización autónoma del iPad")
    parser.add_argument("--path", help="Ruta a analizar (auto-detecta si se omite)")
    parser.add_argument("--email", required=True, help="Email donde enviar el reporte")
    parser.add_argument("--smtp-user", help="Tu cuenta Gmail (remitente)")
    parser.add_argument("--smtp-pass", help="Contraseña de aplicación Gmail")
    parser.add_argument("--clean", action="store_true",
                        help="Limpiar duplicados y temporales automáticamente")
    parser.add_argument("--wait", type=int, default=0,
                        help="Esperar N segundos a que el iPad se conecte (0=no esperar)")
    args = parser.parse_args()

    # Resolver ruta
    path = args.path
    if not path and args.wait > 0:
        path = wait_for_ipad(timeout=args.wait)
    elif not path:
        path = detect_ipad_path()

    if not path:
        print("ERROR: No se pudo detectar el iPad. Especifica --path manualmente.")
        print("Ejemplo: python auto_optimize.py --path ~/Library/Mobile\\ Documents --email tu@gmail.com")
        sys.exit(1)

    cfg = load_config()

    # Ejecutar optimización
    report = build_report(path, cfg, cleaned=args.clean)
    saved = save_report_json(report)
    print(f"[{_ts()}] Reporte guardado en {saved}")

    # Imprimir resumen en consola
    print("\n" + "=" * 50)
    print("RESUMEN")
    print("=" * 50)
    for k, v in report.items():
        print(f"  {k:<25} {v}")

    # Enviar email si se configuraron credenciales
    smtp_user = args.smtp_user or args.email
    smtp_pass = args.smtp_pass

    if smtp_pass:
        try:
            send_email(args.email, report, smtp_user, smtp_pass)
        except Exception as e:
            print(f"[{_ts()}] Error enviando email: {e}")
            print("Verifica tu contraseña de aplicación Gmail.")
    else:
        print(f"\n[{_ts()}] Email no enviado: falta --smtp-pass")
        print("Agrega --smtp-pass para recibir el reporte en tu teléfono.")


if __name__ == "__main__":
    main()
