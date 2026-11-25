"""Publica una actualización: compila, firma el instalador y crea la release en GitHub.

Uso (en el PC donde desarrollas):
    python release.py --keygen            una sola vez: crea la clave de firma
    python release.py --notes "Qué cambió"  compila, firma y publica la versión de vault.py

Antes de publicar: sube tus cambios con git push y sube el número VERSION en vault.py.
El token de GitHub se pide aquí mismo (o se toma de la variable GITHUB_TOKEN); no se guarda.
"""
import argparse
import base64
import getpass
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import updater

ROOT = os.path.dirname(os.path.abspath(__file__))
KEY_DIR = os.path.join(os.path.expanduser("~"), ".hidden-mode")  # fuera del proyecto y de OneDrive
KEY_PATH = os.path.join(KEY_DIR, "signing_key.pem")
INSTALLER = os.path.join(ROOT, "installer", updater.INSTALLER_NAME)


def die(msg):
    print(f"\nERROR: {msg}")
    sys.exit(1)


def current_version() -> str:
    with open(os.path.join(ROOT, "vault.py"), encoding="utf-8") as f:
        m = re.search(r'^VERSION\s*=\s*"([^"]+)"', f.read(), re.M)
    if not m:
        die("No encuentro VERSION en vault.py.")
    return m.group(1)


def keygen():
    if os.path.exists(KEY_PATH):
        die(f"Ya existe una clave en {KEY_PATH}. Si la reemplazas, las apps ya instaladas dejarán de aceptar "
            "actualizaciones. Bórrala a mano solo si estás seguro.")
    os.makedirs(KEY_DIR, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    with open(KEY_PATH, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    user = os.environ.get("USERNAME", "")
    if user:  # solo tu usuario de Windows puede leer el archivo
        subprocess.run(["icacls", KEY_PATH, "/inheritance:r", "/grant:r", f"{user}:(R,W)"],
                       capture_output=True, check=False)
    pub = base64.b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    print(f"Clave privada guardada en: {KEY_PATH}")
    print("NO la subas a GitHub ni la compartas. Haz una copia en un lugar seguro.")
    print(f"\nClave pública (va en updater.py, PUBLIC_KEY_B64):\n{pub}")


def sign(version: str) -> str:
    if not os.path.exists(KEY_PATH):
        die("No hay clave de firma. Ejecuta primero: python release.py --keygen")
    with open(KEY_PATH, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)
    h = hashlib.sha256()
    with open(INSTALLER, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    sig = base64.b64encode(key.sign(updater.signed_message(version, h.hexdigest()))).decode()
    sig_path = INSTALLER + ".sig"
    with open(sig_path, "w") as f:
        f.write(sig)
    updater.verify_signature(version, h.hexdigest(), sig)  # comprobación cruzada con la clave pública de la app
    return sig_path


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def api(method, url, token, body=None, raw=None, ctype="application/json", timeout=60):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "User-Agent": updater.USER_AGENT, "Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        die(f"GitHub respondió {e.code}: {detail}")


def release(notes: str):
    version = current_version()
    tag = f"v{version}"
    if not updater.PUBLIC_KEY_B64:
        die("Falta la clave pública en updater.py. Ejecuta --keygen y pégala en PUBLIC_KEY_B64.")
    if git("status", "--porcelain", "--untracked-files=no"):
        die("Tienes cambios sin confirmar. Haz commit y push antes de publicar.")
    if git("rev-parse", "HEAD") != git("rev-parse", "origin/main"):
        die("Tu rama local no coincide con origin/main. Haz git push antes de publicar.")
    print(f"Publicando {tag} ...")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        os.path.join(ROOT, "build.ps1")], cwd=ROOT)
    if r.returncode != 0 or not os.path.exists(INSTALLER):
        die("La compilación falló.")
    sig_path = sign(version)
    token = os.environ.get("GITHUB_TOKEN") or getpass.getpass("Token de GitHub (permiso Contents: escritura): ").strip()
    if not token:
        die("Sin token no se puede publicar.")
    rel = api("POST", f"https://api.github.com/repos/{updater.REPO}/releases", token, {
        "tag_name": tag, "target_commitish": "main", "name": tag, "body": notes or f"Versión {version}",
        "draft": False, "prerelease": False})
    for path, ctype in ((INSTALLER, "application/octet-stream"), (sig_path, "text/plain")):
        name = os.path.basename(path)
        print(f"Subiendo {name} ...")
        with open(path, "rb") as f:
            payload = f.read()
        api("POST", f"https://uploads.github.com/repos/{updater.REPO}/releases/{rel['id']}/assets?name={name}",
            token, raw=payload, ctype=ctype, timeout=900)
    print(f"\nListo: {rel['html_url']}\nLas apps instaladas verán «Actualización pendiente» la próxima vez que abras la bóveda.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keygen", action="store_true", help="crea la clave de firma (una sola vez)")
    ap.add_argument("--notes", default="", help="texto que verán los usuarios al actualizar")
    args = ap.parse_args()
    keygen() if args.keygen else release(args.notes)
