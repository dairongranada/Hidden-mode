"""Actualizaciones desde GitHub Releases, con firma digital Ed25519.

Cómo funciona:
1. La app consulta la última «release» del repositorio.
2. Si su versión es mayor que la instalada, ofrece actualizar.
3. Descarga el instalador y su firma, y comprueba que la firma sea válida con la
   clave pública incluida aquí. Solo quien tenga la clave privada (que queda en el PC
   donde publicas) puede firmar, así que una release falsa no se instala aunque alguien
   consiga acceso a la cuenta de GitHub.
4. Lanza el instalador en modo silencioso y la app se cierra; el instalador la reabre.
"""
import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

REPO = "dairongranada/Hidden-mode"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
INSTALLER_NAME = "Boveda_Setup.exe"
SIG_NAME = INSTALLER_NAME + ".sig"
PUBLIC_KEY_B64 = "cwXWuZoBB5ExAcEhVcSgZrHVp/9GPBgyOBSLCSntuLM="  # clave pública Ed25519 (32 bytes en base64); la genera `python release.py --keygen`
MAX_INSTALLER = 400 * 1024 * 1024
USER_AGENT = "Hidden-mode-updater"


class UpdateError(Exception):
    """Error con mensaje apto para mostrar al usuario."""


def parse_version(text) -> tuple:
    nums = [int(n) for n in re.findall(r"\d+", str(text).lstrip("vV").split("-")[0])[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def is_newer(candidate, current) -> bool:
    return parse_version(candidate) > parse_version(current)


def signed_message(version: str, digest_hex: str) -> bytes:
    """Lo que se firma: la versión va dentro para que nadie pueda reutilizar un instalador viejo."""
    return f"hidden-mode|{version}|{digest_hex}".encode()


def _open(url: str, timeout: int = 15):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=timeout)


def fetch_latest():
    """Devuelve los datos de la última release publicada, o None si no hay ninguna completa."""
    try:
        with _open(API_LATEST, 10) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:  # todavía no hay releases
            return None
        raise UpdateError(f"GitHub respondió con el error {e.code}.")
    except (OSError, ValueError):
        raise UpdateError("No se pudo conectar con GitHub.")
    assets = {a.get("name"): a for a in data.get("assets", []) if isinstance(a, dict)}
    if INSTALLER_NAME not in assets or SIG_NAME not in assets or not data.get("tag_name"):
        return None
    urls = (assets[INSTALLER_NAME].get("browser_download_url", ""), assets[SIG_NAME].get("browser_download_url", ""))
    if not all(u.startswith(DOWNLOAD_PREFIX) for u in urls):
        return None
    return {
        "version": str(data["tag_name"]).lstrip("vV"),
        "notes": data.get("body") or "",
        "installer_url": urls[0],
        "sig_url": urls[1],
        "size": int(assets[INSTALLER_NAME].get("size") or 0),
    }


def verify_signature(version: str, digest_hex: str, sig_text: str):
    if not PUBLIC_KEY_B64:
        raise UpdateError("Esta copia de la app no tiene clave de verificación, así que no puede actualizarse sola.")
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY_B64))
        key.verify(base64.b64decode(sig_text.strip(), validate=True), signed_message(version, digest_hex))
    except (InvalidSignature, ValueError, binascii.Error):
        raise UpdateError("La firma de la actualización no es válida. No se instaló nada.")


def download_verified(info: dict, progress=None) -> str:
    """Descarga el instalador y comprueba su firma. Devuelve la ruta del archivo verificado."""
    if info["size"] > MAX_INSTALLER:
        raise UpdateError("El instalador es demasiado grande.")
    folder = tempfile.mkdtemp(prefix="bvu_")
    dest = os.path.join(folder, INSTALLER_NAME)
    try:
        try:
            with _open(info["sig_url"], 15) as r:
                sig_text = r.read(4096).decode("ascii", "replace")
            digest, total = hashlib.sha256(), 0
            with _open(info["installer_url"], 30) as r, open(dest, "wb") as f:
                size = int(r.headers.get("Content-Length") or info["size"] or 0)
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_INSTALLER:
                        raise UpdateError("El instalador es demasiado grande.")
                    digest.update(chunk)
                    f.write(chunk)
                    if progress and size:
                        progress(min(total / size, 1.0))
        except UpdateError:
            raise
        except OSError:
            raise UpdateError("Se cortó la descarga. Inténtalo de nuevo.")
        if info["size"] and total != info["size"]:
            raise UpdateError("La descarga quedó incompleta.")
        verify_signature(info["version"], digest.hexdigest(), sig_text)
        return dest
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise


def launch_installer(path: str, extra=()):
    """Lanza el instalador en modo silencioso, desligado de esta app (que debe cerrarse enseguida)."""
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    # El instalador reabrirá esta app cuando esta ya se haya cerrado. Sin esta variable, la copia nueva
    # hereda la carpeta temporal de la vieja (que se borra al cerrar) y falla con «Failed to load Python DLL».
    env = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                      "/FORCECLOSEAPPLICATIONS", "/RELAUNCH=1", *extra],
                     creationflags=flags, close_fds=True, cwd=os.path.dirname(path), env=env)
