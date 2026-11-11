"""Núcleo de la bóveda (cifrado y almacenamiento, sin interfaz).

- Archivos: AES-256-GCM por bloques (sirve para videos grandes).
- Clave maestra aleatoria, protegida ("envuelta") con una clave derivada de la
  contraseña con scrypt. Así se puede cambiar la contraseña sin recifrar todo.
- Nombres de archivo, álbumes y miniaturas también van cifrados.
"""
import base64
import ctypes
import json
import os
import re
import secrets
import shutil
import struct
import sys
import time
import uuid
import zipfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

VERSION = "2.0.0"
MAGIC = b"VLT1"
CHUNK = 1024 * 1024  # 1 MB
FILE_EXT = ".dat"
SCRYPT_N_OLD = 2**15  # bóvedas v1
SCRYPT_N = 2**16      # bóvedas nuevas
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}
VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v"}


def app_dir():
    base = sys.executable if getattr(sys, "frozen", False) else __file__
    return os.path.dirname(os.path.abspath(base))


# ---------------------------------------------------------------- ubicación
_ROOT = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
DEFAULT_BASE = os.path.join(_ROOT, "Microsoft")
BASE_DIR = os.path.join(DEFAULT_BASE, "CLRCache")  # bóveda "clásica" + archivo puntero
POINTER_PATH = os.path.join(BASE_DIR, "loc.dat")
OLD_DIR = os.path.join(app_dir(), "vault_data")  # versiones muy antiguas (junto al .exe)

DATA_DIR = FILES_DIR = THUMB_DIR = META_PATH = INDEX_PATH = INDEX_BAK = ""
SETTINGS_PATH = ATTEMPTS_PATH = ""


def set_data_dir(path: str):
    """Define la carpeta de la bóveda activa."""
    global DATA_DIR, FILES_DIR, THUMB_DIR, META_PATH, INDEX_PATH, INDEX_BAK, SETTINGS_PATH, ATTEMPTS_PATH
    DATA_DIR = path
    FILES_DIR = os.path.join(path, "sym")
    THUMB_DIR = os.path.join(path, "thm")
    META_PATH = os.path.join(path, "cfg.dat")
    INDEX_PATH = os.path.join(path, "idx.dat")
    INDEX_BAK = os.path.join(path, "idx.bak")
    SETTINGS_PATH = os.path.join(path, "st.dat")
    ATTEMPTS_PATH = os.path.join(path, "att.dat")


set_data_dir(BASE_DIR)

_HIDDEN_SYSTEM = 0x02 | 0x04
_NORMAL = 0x80


def set_attr(path: str, attr: int):
    try:
        ctypes.windll.kernel32.SetFileAttributesW(path, attr)
    except Exception:
        pass


def hide(path: str):
    set_attr(path, _HIDDEN_SYSTEM)


def unhide(path: str):
    set_attr(path, _NORMAL)


def read_pointer():
    try:
        with open(POINTER_PATH) as f:
            return json.load(f).get("dir")
    except Exception:
        return None


def write_pointer(path):
    """Guarda (o borra, si path es None) la ubicación recordada en este PC."""
    try:
        unhide(POINTER_PATH)
        if path is None:
            if os.path.exists(POINTER_PATH):
                os.remove(POINTER_PATH)
            return
        os.makedirs(BASE_DIR, exist_ok=True)
        with open(POINTER_PATH, "w") as f:
            json.dump({"dir": path}, f)
        hide(POINTER_PATH)
        hide(BASE_DIR)
    except Exception:
        pass


def find_vault(folder: str):
    """Busca una bóveda en la carpeta o en sus subcarpetas directas."""
    if os.path.exists(os.path.join(folder, "cfg.dat")):
        return folder
    try:
        for n in os.listdir(folder):
            sub = os.path.join(folder, n)
            if os.path.isdir(sub) and os.path.exists(os.path.join(sub, "cfg.dat")):
                return sub
    except OSError:
        pass
    return None


def resolve_location():
    """Decide qué bóveda usar al iniciar. Devuelve ('unlock'|'missing'|'create', ruta)."""
    migrate_old_vault()
    p = read_pointer()
    if p:
        set_data_dir(p)
        return ("unlock" if os.path.exists(META_PATH) else "missing"), p
    set_data_dir(BASE_DIR)
    return ("unlock" if os.path.exists(META_PATH) else "create"), BASE_DIR


def new_vault_dir(base=None) -> str:
    base = base or DEFAULT_BASE
    return os.path.join(base, "CLR_" + secrets.token_hex(4))


def migrate_old_vault():
    """Mueve una bóveda de versiones antiguas (carpeta vault_data junto al .exe)."""
    old_meta = os.path.join(OLD_DIR, "meta.json")
    if os.path.exists(os.path.join(BASE_DIR, "cfg.dat")) or not os.path.exists(old_meta):
        return
    set_data_dir(BASE_DIR)
    os.makedirs(FILES_DIR, exist_ok=True)
    old_files = os.path.join(OLD_DIR, "files")
    if os.path.isdir(old_files):
        for n in os.listdir(old_files):
            shutil.move(os.path.join(old_files, n),
                        os.path.join(FILES_DIR, os.path.splitext(n)[0] + FILE_EXT))
    shutil.move(os.path.join(OLD_DIR, "index.bin"), INDEX_PATH)
    shutil.move(old_meta, META_PATH)
    shutil.rmtree(OLD_DIR, ignore_errors=True)
    for f in os.listdir(FILES_DIR):
        hide(os.path.join(FILES_DIR, f))
    for p in (INDEX_PATH, META_PATH, FILES_DIR, DATA_DIR):
        hide(p)


# ---------------------------------------------------------------- ajustes
DEFAULT_SETTINGS = {"idle_minutes": 5, "lock_on_minimize": True, "block_capture": False, "title": "Bóveda"}


def load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            s.update(json.load(f))
    except Exception:
        pass
    return s


def save_settings(s: dict):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        unhide(SETTINGS_PATH)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f)
        hide(SETTINGS_PATH)
    except Exception:
        pass


# ---------------------------------------------------------------- intentos fallidos
def attempt_status():
    """(fallos, momento hasta el que está bloqueado el acceso)."""
    try:
        with open(ATTEMPTS_PATH) as f:
            d = json.load(f)
        return int(d.get("fails", 0)), float(d.get("until", 0))
    except Exception:
        return 0, 0.0


def _write_attempts(fails, until):
    try:
        unhide(ATTEMPTS_PATH)
        with open(ATTEMPTS_PATH, "w") as f:
            json.dump({"fails": fails, "until": until}, f)
        hide(ATTEMPTS_PATH)
    except Exception:
        pass


def register_fail():
    """Registra un intento fallido. Desde el 3.º hay espera creciente (5 s, 10 s, 20 s... máx. 15 min)."""
    fails, _ = attempt_status()
    fails += 1
    delay = 0 if fails < 3 else min(5 * 2 ** (fails - 3), 900)
    _write_attempts(fails, time.time() + delay if delay else 0)
    return fails, delay


def register_success():
    _write_attempts(0, 0)


# ---------------------------------------------------------------- cripto
def derive_key(password: str, salt: bytes, n: int = SCRYPT_N_OLD) -> bytes:
    return Scrypt(salt=salt, length=32, n=n, r=8, p=1).derive(password.encode("utf-8"))


def encrypt_bytes(key: bytes, data: bytes) -> bytes:
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, data, None)


def decrypt_bytes(key: bytes, blob: bytes) -> bytes:
    return AESGCM(key).decrypt(blob[:12], blob[12:], None)


def _nonce(prefix: bytes, counter: int) -> bytes:
    return prefix + struct.pack(">I", counter)


def encrypt_file(key: bytes, src: str, dst: str):
    aes = AESGCM(key)
    prefix = secrets.token_bytes(8)
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        fout.write(MAGIC + prefix)
        counter = 0
        block = fin.read(CHUNK)
        while True:
            nxt = fin.read(CHUNK)
            last = b"\x01" if not nxt else b"\x00"  # evita truncado del archivo
            ct = aes.encrypt(_nonce(prefix, counter), block, last)
            fout.write(struct.pack(">I", len(ct)) + ct)
            if not nxt:
                break
            block, counter = nxt, counter + 1


def decrypt_file_chunks(key: bytes, src: str):
    aes = AESGCM(key)
    with open(src, "rb") as fin:
        head = fin.read(12)
        if head[:4] != MAGIC:
            raise ValueError("Archivo no válido")
        prefix = head[4:]
        counter = 0
        raw = fin.read(4)
        while raw:
            size = struct.unpack(">I", raw)[0]
            ct = fin.read(size)
            nxt = fin.read(4)
            last = b"\x01" if not nxt else b"\x00"
            yield aes.decrypt(_nonce(prefix, counter), ct, last)
            raw, counter = nxt, counter + 1


def decrypt_to_bytes(key: bytes, src: str) -> bytes:
    return b"".join(decrypt_file_chunks(key, src))


def decrypt_to_path(key: bytes, src: str, dst: str):
    with open(dst, "wb") as f:
        for part in decrypt_file_chunks(key, src):
            f.write(part)


# ---------------------------------------------------------------- borrado seguro
def shred_file(path: str):
    """Sobrescribe el archivo con datos aleatorios y lo borra.
    En SSD o carpetas sincronizadas (OneDrive) no se puede garantizar el borrado físico."""
    try:
        os.chmod(path, 0o600)
        size = os.path.getsize(path)
        with open(path, "r+b") as f:
            left = size
            while left > 0:
                n = min(left, CHUNK)
                f.write(secrets.token_bytes(n))
                left -= n
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        pass
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def secure_rmtree(folder: str):
    for root, _, files in os.walk(folder):
        for n in files:
            shred_file(os.path.join(root, n))
    shutil.rmtree(folder, ignore_errors=True)


# ---------------------------------------------------------------- miniaturas cifradas
def save_thumb(key: bytes, fid: str, jpeg: bytes):
    os.makedirs(THUMB_DIR, exist_ok=True)
    hide(THUMB_DIR)
    p = os.path.join(THUMB_DIR, fid + FILE_EXT)
    with open(p, "wb") as f:
        f.write(encrypt_bytes(key, jpeg))
    hide(p)


def load_thumb(key: bytes, fid: str):
    try:
        with open(os.path.join(THUMB_DIR, fid + FILE_EXT), "rb") as f:
            return decrypt_bytes(key, f.read())
    except Exception:
        return None


# ---------------------------------------------------------------- bóveda
class Vault:
    def __init__(self):
        self.key = None
        self.items = []   # {id, name, type, size, added, album}
        self.albums = []  # nombres de álbumes

    @staticmethod
    def exists():
        return os.path.exists(META_PATH)

    @staticmethod
    def _read_meta():
        with open(META_PATH) as f:
            return json.load(f)

    @staticmethod
    def _open_key(meta: dict, password: str):
        """Devuelve la clave maestra o None si la contraseña es incorrecta."""
        salt = base64.b64decode(meta["salt"])
        try:
            if meta.get("v") == 2:
                kek = derive_key(password, salt, meta["n"])
                return decrypt_bytes(kek, base64.b64decode(meta["wrapped"]))
            key = derive_key(password, salt)  # formato v1: la clave sale directo de la contraseña
            if decrypt_bytes(key, base64.b64decode(meta["check"])) == b"OK":
                return key
        except InvalidTag:
            pass
        return None

    @staticmethod
    def _write_meta(meta: dict):
        tmp = META_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(meta, f)
        unhide(META_PATH)
        os.replace(tmp, META_PATH)
        hide(META_PATH)

    @staticmethod
    def _wrap(master: bytes, password: str) -> dict:
        salt = secrets.token_bytes(16)
        kek = derive_key(password, salt, SCRYPT_N)
        return {"v": 2, "salt": base64.b64encode(salt).decode(), "n": SCRYPT_N,
                "wrapped": base64.b64encode(encrypt_bytes(kek, master)).decode()}

    def create(self, password: str, base=None, remember=True):
        """Crea una bóveda nueva en una carpeta de nombre aleatorio dentro de `base`."""
        folder = new_vault_dir(base)
        set_data_dir(folder)
        os.makedirs(FILES_DIR, exist_ok=True)
        os.makedirs(THUMB_DIR, exist_ok=True)
        self.key = secrets.token_bytes(32)
        self._write_meta(self._wrap(self.key, password))
        self.items, self.albums = [], []
        self.save_index()
        for p in (FILES_DIR, THUMB_DIR, DATA_DIR):
            hide(p)
        write_pointer(folder if remember else None)

    def unlock(self, password: str) -> bool:
        key = self._open_key(self._read_meta(), password)
        if key is None:
            return False
        data = None
        for path in (INDEX_PATH, INDEX_BAK):  # si el índice se dañó, se usa la copia
            try:
                with open(path, "rb") as f:
                    data = json.loads(decrypt_bytes(key, f.read()))
                break
            except Exception:
                continue
        if data is None:
            raise RuntimeError("El índice de la bóveda está dañado y no hay copia de respaldo.")
        self.key = key
        if isinstance(data, list):  # formato antiguo
            data = {"items": data, "albums": []}
        self.items = data.get("items", [])
        self.albums = data.get("albums", [])
        for it in self.items:
            it.setdefault("album", "")
        return True

    def change_password(self, old: str, new: str) -> bool:
        meta = self._read_meta()
        if self._open_key(meta, old) is None:
            return False
        self._write_meta(self._wrap(self.key, new))
        return True

    def save_index(self):
        data = encrypt_bytes(self.key, json.dumps({"items": self.items, "albums": self.albums}).encode())
        tmp = INDEX_PATH + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        if os.path.exists(INDEX_PATH):  # copia de seguridad del índice anterior
            unhide(INDEX_BAK)
            shutil.copyfile(INDEX_PATH, INDEX_BAK)
            hide(INDEX_BAK)
        unhide(INDEX_PATH)  # Windows no deja reemplazar archivos ocultos/sistema
        os.replace(tmp, INDEX_PATH)
        hide(INDEX_PATH)

    @staticmethod
    def kind_of(path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        if ext in IMAGE_EXT:
            return "Imagen"
        if ext in VIDEO_EXT:
            return "Video"
        return "Documento"

    def add(self, path: str, album: str = "") -> dict:
        fid = uuid.uuid4().hex
        dst = os.path.join(FILES_DIR, fid + FILE_EXT)
        encrypt_file(self.key, path, dst)
        hide(dst)
        item = {
            "id": fid,
            "name": os.path.basename(path),
            "type": self.kind_of(path),
            "size": os.path.getsize(path),
            "added": time.strftime("%Y-%m-%d %H:%M"),
            "album": album,
        }
        self.items.append(item)
        self.save_index()
        return item

    def path_of(self, item):
        return os.path.join(FILES_DIR, item["id"] + FILE_EXT)

    def remove(self, item):
        for p in (self.path_of(item), os.path.join(THUMB_DIR, item["id"] + FILE_EXT)):
            try:
                unhide(p)
                os.remove(p)
            except FileNotFoundError:
                pass
        self.items = [i for i in self.items if i["id"] != item["id"]]
        self.save_index()

    def rename(self, item, new_name: str):
        item["name"] = new_name
        self.save_index()

    # --- álbumes
    def add_album(self, name: str) -> bool:
        if not name or name.lower() in (a.lower() for a in self.albums):
            return False
        self.albums.append(name)
        self.save_index()
        return True

    def rename_album(self, old: str, new: str) -> bool:
        if not new or (new.lower() != old.lower() and new.lower() in (a.lower() for a in self.albums)):
            return False
        self.albums = [new if a == old else a for a in self.albums]
        for it in self.items:
            if it.get("album") == old:
                it["album"] = new
        self.save_index()
        return True

    def delete_album(self, name: str):
        """Borra el álbum; sus archivos quedan sin álbum (no se eliminan)."""
        self.albums = [a for a in self.albums if a != name]
        for it in self.items:
            if it.get("album") == name:
                it["album"] = ""
        self.save_index()

    def move_to_album(self, items, album: str):
        ids = {i["id"] for i in items}
        for it in self.items:
            if it["id"] in ids:
                it["album"] = album
        self.save_index()


# ---------------------------------------------------------------- respaldo
_BACKUP_NAME = re.compile(r"^(cfg\.dat|idx\.dat|idx\.bak|st\.dat|(sym|thm)/[0-9a-f]{32}\.dat)$")


def export_backup(dst_zip: str, progress=None):
    """Empaqueta toda la bóveda (ya cifrada) en un solo archivo."""
    names = []
    for n in ("cfg.dat", "idx.dat", "idx.bak", "st.dat"):
        if os.path.exists(os.path.join(DATA_DIR, n)):
            names.append(n)
    for sub in ("sym", "thm"):
        d = os.path.join(DATA_DIR, sub)
        if os.path.isdir(d):
            names += [f"{sub}/{f}" for f in os.listdir(d) if f.endswith(FILE_EXT)]
    with zipfile.ZipFile(dst_zip, "w", zipfile.ZIP_STORED) as z:
        for i, n in enumerate(names, 1):
            z.write(os.path.join(DATA_DIR, *n.split("/")), n)
            if progress:
                progress(i / len(names))


def import_backup(src_zip: str, base=None, progress=None) -> str:
    """Restaura un respaldo en una carpeta nueva y devuelve su ruta."""
    with zipfile.ZipFile(src_zip) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        bad = [n for n in names if not _BACKUP_NAME.match(n)]
        if bad or "cfg.dat" not in names or "idx.dat" not in names:
            raise ValueError("El archivo no es un respaldo válido de la bóveda.")
        folder = new_vault_dir(base)
        os.makedirs(os.path.join(folder, "sym"), exist_ok=True)
        os.makedirs(os.path.join(folder, "thm"), exist_ok=True)
        for i, n in enumerate(names, 1):
            with z.open(n) as fin, open(os.path.join(folder, *n.split("/")), "wb") as fout:
                shutil.copyfileobj(fin, fout)
            if progress:
                progress(i / len(names))
    for root, dirs, files in os.walk(folder):
        for n in files + dirs:
            hide(os.path.join(root, n))
    hide(folder)
    return folder
