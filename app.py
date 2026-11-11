"""Bóveda - interfaz (customtkinter). La lógica de cifrado está en vault.py."""
import ctypes
import glob
import io
import os
import queue
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

import vault as core

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except Exception:  # la app funciona igual sin arrastrar y soltar
    HAS_DND = False

# ---------------------------------------------------------------- estilo
BG = "#0f1016"
PANEL = "#171923"
CARD = "#1f2230"
CARD_SEL = "#2d2f52"
TEXT = "#e8e9f0"
MUTED = "#8b8fa8"
ACCENT = "#7c5cff"
ACCENT_H = "#6a49f0"
ACCENT_DIM = "#2a2550"
DANGER = "#e5484d"
DANGER_H = "#c93a3f"

THUMB = 150          # tamaño en pantalla
TS = 240             # tamaño guardado de la miniatura
CARD_W = THUMB + 20
CARD_H = THUMB + 68
GAP = 12
PAGE = 60            # tarjetas que se dibujan por tanda
MAX_THUMBS = 400     # miniaturas en memoria

CATEGORIES = (
    ("Todos", "Todos", "▦"),
    ("Imagen", "Imágenes", "▣"),
    ("Video", "Videos", "▶"),
    ("Documento", "Documentos", "≡"),
)
SORTS = ("Más recientes", "Más antiguos", "Nombre (A-Z)", "Nombre (Z-A)", "Más grandes", "Más pequeños")
IDLE_CHOICES = {"1 minuto": 1, "2 minutos": 2, "5 minutos": 5, "10 minutos": 10,
                "15 minutos": 15, "30 minutos": 30, "Nunca": 0}


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def fmt_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def shorten(text, n=20):
    return text if len(text) <= n else text[: n - 1] + "…"


def unique_path(folder, name):
    base, ext = os.path.splitext(name)
    path, i = os.path.join(folder, name), 1
    while os.path.exists(path):
        path = os.path.join(folder, f"{base} ({i}){ext}")
        i += 1
    return path


# ---------------------------------------------------------------- sistema
def single_instance() -> bool:
    k = ctypes.windll.kernel32
    k.CreateMutexW(None, False, "Local\\BovedaApp_7d5e2c")
    return k.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def desktop_locked() -> bool:
    """True si Windows está bloqueado (Win+L)."""
    try:
        u = ctypes.windll.user32
        u.OpenInputDesktop.restype = ctypes.c_void_p
        u.CloseDesktop.argtypes = [ctypes.c_void_p]
        h = u.OpenInputDesktop(0, False, 0x0100)
        if not h:
            return True
        u.CloseDesktop(h)
        return False
    except Exception:
        return False


def set_capture_block(win, on: bool):
    """Oculta la ventana de capturas de pantalla y grabaciones (Windows 10 2004+)."""
    try:
        u = ctypes.windll.user32
        hwnd = u.GetParent(win.winfo_id()) or win.winfo_id()
        if not u.SetWindowDisplayAffinity(hwnd, 0x11 if on else 0) and on:
            u.SetWindowDisplayAffinity(hwnd, 0x01)
    except Exception:
        pass


def short_path(p):
    if p.isascii():
        return p
    try:
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(p, buf, 1024):
            return buf.value
    except Exception:
        pass
    return p


def purge_stale_temp():
    """Borra copias temporales que pudieron quedar de una sesión anterior."""
    for d in glob.glob(os.path.join(tempfile.gettempdir(), "vlt_*")):
        if os.path.isdir(d):
            core.secure_rmtree(d)


# ---------------------------------------------------------------- imágenes
_placeholder_cache = {}


def placeholder(kind, name):
    """Icono dibujado para archivos sin miniatura."""
    ext = os.path.splitext(name)[1].lstrip(".").upper()[:4] or "FILE"
    key = (kind, ext if kind != "Imagen" else "")
    if key in _placeholder_cache:
        return _placeholder_cache[key]
    s = THUMB * 2
    img = Image.new("RGB", (s, s), "#262a3f")
    d = ImageDraw.Draw(img)
    if kind == "Imagen":
        d.polygon([(s * 0.18, s * 0.72), (s * 0.42, s * 0.38), (s * 0.58, s * 0.6), (s * 0.7, s * 0.48),
                   (s * 0.84, s * 0.72)], fill="#3c4160")
        d.ellipse((s * 0.64, s * 0.22, s * 0.78, s * 0.36), fill="#3c4160")
    elif kind == "Video":
        c, r = s // 2, int(s * 0.27)
        d.ellipse((c - r, c - r, c + r, c + r), fill=ACCENT)
        d.polygon([(c - r // 3, c - r // 2), (c - r // 3, c + r // 2), (c + r * 2 // 3, c)], fill="white")
        d.text((c, int(s * 0.88)), ext, font=ImageFont.load_default(size=int(s * 0.1)), anchor="mm", fill=MUTED)
    else:
        x0, y0, x1, y1 = int(s * 0.29), int(s * 0.16), int(s * 0.71), int(s * 0.84)
        fold = int(s * 0.12)
        d.polygon([(x0, y0), (x1 - fold, y0), (x1, y0 + fold), (x1, y1), (x0, y1)], fill="#3c4160")
        d.polygon([(x1 - fold, y0), (x1, y0 + fold), (x1 - fold, y0 + fold)], fill="#565c85")
        for i in range(3):
            y = int(s * (0.34 + i * 0.07))
            d.line((x0 + 20, y, x1 - 20, y), fill="#6b7199", width=6)
        d.rounded_rectangle((x0 + 14, int(s * 0.62), x1 - 14, int(s * 0.76)), radius=12, fill=ACCENT)
        d.text(((x0 + x1) // 2, int(s * 0.69)), ext, font=ImageFont.load_default(size=int(s * 0.09)),
               anchor="mm", fill="white")
    out = ctk.CTkImage(light_image=img, dark_image=img, size=(THUMB, THUMB))
    _placeholder_cache[key] = out
    return out


def fit_square(img: Image.Image) -> Image.Image:
    return ImageOps.fit(img.convert("RGB"), (TS, TS), Image.LANCZOS)


def thumb_from_image(img: Image.Image) -> Image.Image:
    try:
        img.draft("RGB", (TS * 2, TS * 2))
    except Exception:
        pass
    return fit_square(ImageOps.exif_transpose(img))


def to_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    return buf.getvalue()


def video_frame(path: str):
    """Primer fotograma útil de un video (necesita el archivo en claro: se usa al agregarlo)."""
    try:
        import cv2
    except Exception:
        return None
    cap = cv2.VideoCapture(short_path(path))
    try:
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        if fps and total > fps * 3:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps))  # ~1 s, evita fundidos negros iniciales
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        if not ok:
            return None
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    finally:
        cap.release()


def add_play_badge(img: Image.Image) -> Image.Image:
    img = img.copy()
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    c, r = img.size[0] // 2, img.size[0] // 7
    d.ellipse((c - r, c - r, c + r, c + r), fill=(0, 0, 0, 150))
    d.polygon([(c - r // 3, c - r // 2), (c - r // 3, c + r // 2), (c + r * 2 // 3, c)], fill=(255, 255, 255, 235))
    return Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")


def make_thumb_from_path(kind: str, path: str):
    """JPEG de la miniatura a partir del archivo original (o None)."""
    if kind == "Imagen":
        with Image.open(path) as im:
            return to_jpeg(thumb_from_image(im))
    if kind == "Video":
        fr = video_frame(path)
        return to_jpeg(add_play_badge(fit_square(fr))) if fr is not None else None
    return None


# ---------------------------------------------------------------- diálogos
def center_over(win, parent, w, h):
    parent.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
    y = parent.winfo_rooty() + max((parent.winfo_height() - h) // 3, 0)
    win.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")


def make_modal(win, tries=10):
    """Hace modal el diálogo cuando ya es visible (sin bloquear el bucle de eventos)."""
    try:
        if not win.winfo_exists():
            return
        win.lift()
        win.focus_force()
        win.grab_set()
    except tk.TclError:
        if tries > 0:
            try:
                win.after(100, lambda: make_modal(win, tries - 1))
            except tk.TclError:
                pass


class TextDialog(ctk.CTkToplevel):
    def __init__(self, parent, title, prompt, initial="", button="Aceptar"):
        super().__init__(parent)
        self.result = None
        self.title(title)
        self.configure(fg_color=PANEL)
        self.resizable(False, False)
        self.transient(parent)
        center_over(self, parent, 380, 190)
        ctk.CTkLabel(self, text=prompt, text_color=TEXT).pack(padx=24, pady=(22, 8), anchor="w")
        self.entry = ctk.CTkEntry(self, height=38, fg_color=CARD, border_color=CARD)
        self.entry.pack(fill="x", padx=24)
        self.entry.insert(0, initial)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=18)
        ctk.CTkButton(row, text=button, width=110, fg_color=ACCENT, hover_color=ACCENT_H,
                      command=self.accept).pack(side="right")
        ctk.CTkButton(row, text="Cancelar", width=100, fg_color=CARD, hover_color=CARD_SEL,
                      command=self.destroy).pack(side="right", padx=8)
        self.bind("<Return>", lambda e: self.accept())
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(150, lambda: (self.entry.focus_set(), self.entry.select_range(0, "end")))
        self.after(50, lambda: make_modal(self))

    def accept(self):
        self.result = self.entry.get().strip()
        self.destroy()


def ask_text(parent, title, prompt, initial="", button="Aceptar"):
    d = TextDialog(parent, title, prompt, initial, button)
    parent.wait_window(d)
    return d.result or None


class PasswordDialog(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Cambiar contraseña")
        self.configure(fg_color=PANEL)
        self.resizable(False, False)
        self.transient(app)
        center_over(self, app, 400, 380)
        self.fields = []
        for label in ("Contraseña actual", "Contraseña nueva (mín. 8)", "Repite la nueva"):
            ctk.CTkLabel(self, text=label, text_color=MUTED).pack(padx=28, pady=(14, 2), anchor="w")
            e = ctk.CTkEntry(self, show="•", height=38, fg_color=CARD, border_color=CARD)
            e.pack(fill="x", padx=28)
            self.fields.append(e)
        self.msg = ctk.CTkLabel(self, text="", text_color=DANGER, wraplength=330)
        self.msg.pack(pady=(10, 0))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=28, pady=12)
        ctk.CTkButton(row, text="Cambiar", width=110, fg_color=ACCENT, hover_color=ACCENT_H,
                      command=self.accept).pack(side="right")
        ctk.CTkButton(row, text="Cancelar", width=100, fg_color=CARD, hover_color=CARD_SEL,
                      command=self.destroy).pack(side="right", padx=8)
        self.bind("<Return>", lambda e: self.accept())
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(150, self.fields[0].focus_set)
        self.after(50, lambda: make_modal(self))
        self.after(200, lambda: self.app.apply_capture_to(self))

    def accept(self):
        old, new, rep = (f.get() for f in self.fields)
        if len(new) < 8:
            return self.msg.configure(text="La nueva contraseña debe tener al menos 8 caracteres.")
        if new != rep:
            return self.msg.configure(text="Las contraseñas nuevas no coinciden.")
        self.msg.configure(text="Procesando…", text_color=MUTED)
        self.update_idletasks()
        try:
            ok = self.app.vault.change_password(old, new)
        except Exception as e:
            return self.msg.configure(text=f"Error: {e}", text_color=DANGER)
        if not ok:
            return self.msg.configure(text="La contraseña actual es incorrecta.", text_color=DANGER)
        messagebox.showinfo("Bóveda", "Contraseña cambiada. Úsala la próxima vez que abras la bóveda.", parent=self)
        self.destroy()


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        s = app.settings
        self.title("Ajustes")
        self.configure(fg_color=PANEL)
        self.resizable(False, False)
        self.transient(app)
        center_over(self, app, 460, 560)

        def section(text):
            ctk.CTkLabel(self, text=text, text_color=MUTED, font=ctk.CTkFont(size=11, weight="bold")
                         ).pack(padx=28, pady=(16, 4), anchor="w")

        section("SEGURIDAD")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=28)
        ctk.CTkLabel(row, text="Bloquear tras inactividad", text_color=TEXT).pack(side="left")
        cur = next((k for k, v in IDLE_CHOICES.items() if v == s.get("idle_minutes", 5)), "5 minutos")
        ctk.CTkOptionMenu(row, values=list(IDLE_CHOICES), width=130, fg_color=CARD, button_color=CARD_SEL,
                          command=lambda v: app.update_setting("idle_minutes", IDLE_CHOICES[v])
                          ).pack(side="right")
        row.winfo_children()[-1].set(cur)
        self._switch("Bloquear al minimizar la ventana", "lock_on_minimize", s)
        self._switch("Ocultar la ventana en capturas de pantalla", "block_capture", s)
        ctk.CTkButton(self, text="Cambiar contraseña…", height=36, fg_color=CARD, hover_color=CARD_SEL,
                      command=lambda: PasswordDialog(app)).pack(fill="x", padx=28, pady=(12, 0))

        section("DISCRECIÓN")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=28)
        self.title_entry = ctk.CTkEntry(row, height=36, fg_color=CARD, border_color=CARD)
        self.title_entry.pack(side="left", fill="x", expand=True)
        self.title_entry.insert(0, s.get("title", "Bóveda"))
        ctk.CTkButton(row, text="Aplicar título", width=110, height=36, fg_color=CARD, hover_color=CARD_SEL,
                      command=self.apply_title).pack(side="right", padx=(8, 0))
        ctk.CTkLabel(self, text="Es el nombre que se ve en la barra de la ventana.", text_color=MUTED,
                     font=ctk.CTkFont(size=11)).pack(padx=28, anchor="w")

        section("RESPALDO")
        ctk.CTkButton(self, text="Respaldar bóveda…", height=36, fg_color=CARD, hover_color=CARD_SEL,
                      command=lambda: (self.destroy(), app.backup_vault())).pack(fill="x", padx=28)
        ctk.CTkLabel(self, text="Para restaurar, usa «Restaurar respaldo» en la pantalla de acceso.",
                     text_color=MUTED, font=ctk.CTkFont(size=11)).pack(padx=28, anchor="w")

        section("UBICACIÓN DE LA BÓVEDA")
        ctk.CTkLabel(self, text=core.DATA_DIR, text_color=TEXT, wraplength=400, justify="left",
                     font=ctk.CTkFont(size=11)).pack(padx=28, anchor="w")
        ctk.CTkLabel(self, text="F12 o Ctrl+L bloquean al instante     ·     by @dairongranadaa",
                     text_color=MUTED, font=ctk.CTkFont(size=11)).pack(side="bottom", pady=14)
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(50, lambda: make_modal(self))
        self.after(200, lambda: app.apply_capture_to(self))

    def _switch(self, text, key, s):
        sw = ctk.CTkSwitch(self, text=text, progress_color=ACCENT, text_color=TEXT,
                           command=lambda: self.app.update_setting(key, bool(sw.get())))
        sw.pack(padx=28, pady=(10, 0), anchor="w")
        if s.get(key):
            sw.select()

    def apply_title(self):
        self.app.update_setting("title", self.title_entry.get().strip() or "Bóveda")


# ---------------------------------------------------------------- tarjeta
class Card(ctk.CTkFrame):
    def __init__(self, master, item, image, on_click, on_open):
        super().__init__(master, width=CARD_W, height=CARD_H, corner_radius=14,
                         fg_color=CARD, border_width=2, border_color=CARD)
        self.pack_propagate(False)
        self.item = item
        self.img_label = ctk.CTkLabel(self, text="", image=image, width=THUMB, height=THUMB)
        self.img_label.pack(padx=8, pady=(8, 4))
        name = ctk.CTkLabel(self, text=shorten(item["name"]), text_color=TEXT,
                            font=ctk.CTkFont(size=12, weight="bold"))
        name.pack()
        sub = ctk.CTkLabel(self, text=f"{item['type']} · {fmt_size(item['size'])}",
                           text_color=MUTED, font=ctk.CTkFont(size=11))
        sub.pack()
        for w in (self, self.img_label, name, sub):
            w.bind("<Button-1>", lambda e, it=item: on_click(it, e))
            w.bind("<Double-Button-1>", lambda e, it=item: on_open(it))

    def set_selected(self, sel):
        self.configure(border_color=ACCENT if sel else CARD, fg_color=CARD_SEL if sel else CARD)

    def set_image(self, image):
        self.img_label.configure(image=image)


# ---------------------------------------------------------------- visor
class Viewer(ctk.CTkToplevel):
    MAX_SCALE = 8.0

    def __init__(self, app, items, idx):
        super().__init__(app)
        self.app, self.items, self.idx = app, items, idx
        self.pil = None
        self.photo = None
        self.scale = self.fit_scale = 1.0
        self.cx = self.cy = 0.0
        self.playing = False
        self._play_job = self._job = None
        self._drag = None
        self._fs = False
        self.title("Visor")
        self.geometry("1100x760")
        self.minsize(560, 420)
        self.configure(fg_color="#08090d")
        self.protocol("WM_DELETE_WINDOW", self.close)

        bar = ctk.CTkFrame(self, fg_color=PANEL, height=56, corner_radius=0)
        bar.pack(side="bottom", fill="x")

        def btn(text, cmd, side, w=44):
            b = ctk.CTkButton(bar, text=text, width=w, height=34, fg_color=CARD, hover_color=CARD_SEL, command=cmd)
            b.pack(side=side, padx=(10, 0) if side == "left" else (0, 10), pady=11)
            return b

        btn("◀", lambda: self.go(-1), "left")
        btn("▶", lambda: self.go(1), "left")
        btn("Pantalla completa", self.toggle_fs, "right", 140)
        self.play_btn = btn("Presentación", self.toggle_play, "right", 110)
        btn("Ajustar", self.reset_view, "right", 80)
        btn("Rotar", self.rotate, "right", 70)
        self.info = ctk.CTkLabel(bar, text="", text_color=TEXT)
        self.info.pack(side="left", expand=True)

        self.canvas = tk.Canvas(self, bg="#08090d", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_cfg)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<ButtonPress-1>", lambda e: setattr(self, "_drag", (e.x, e.y)))
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<Double-Button-1>", lambda e: self.reset_view())
        for seq, fn in (("<Left>", lambda e: self.go(-1)), ("<Right>", lambda e: self.go(1)),
                        ("<plus>", lambda e: self.zoom(1.25)), ("<equal>", lambda e: self.zoom(1.25)),
                        ("<minus>", lambda e: self.zoom(0.8)), ("<0>", lambda e: self.reset_view()),
                        ("<r>", lambda e: self.rotate()), ("<space>", lambda e: self.toggle_play()),
                        ("<F11>", lambda e: self.toggle_fs()), ("<Escape>", lambda e: self.on_escape())):
            self.bind(seq, fn)
        self.after(120, self.focus_force)
        self.after(160, self.load)
        self.after(200, lambda: app.apply_capture_to(self))

    # --- navegación
    def close(self):
        self.playing = False
        for j in (self._play_job, self._job):
            if j:
                try:
                    self.after_cancel(j)
                except Exception:
                    pass
        self.destroy()

    def on_escape(self):
        if self._fs:
            self.toggle_fs()
        else:
            self.close()

    def toggle_fs(self):
        self._fs = not self._fs
        self.attributes("-fullscreen", self._fs)

    def go(self, d):
        self.idx = (self.idx + d) % len(self.items)
        self.load()

    def toggle_play(self):
        self.playing = not self.playing
        self.play_btn.configure(text="Detener" if self.playing else "Presentación")
        if self.playing:
            self._play_job = self.after(3000, self._tick)

    def _tick(self):
        self._play_job = None
        if self.playing:
            self.go(1)
            self._play_job = self.after(3000, self._tick)

    # --- imagen
    def load(self):
        it = self.items[self.idx]
        self.info.configure(text=f"{it['name']}    ·    {self.idx + 1} / {len(self.items)}")
        try:
            data = core.decrypt_to_bytes(self.app.vault.key, self.app.vault.path_of(it))
            self.pil = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
            self.reset_view()
        except Exception as e:
            self.pil = None
            self.canvas.delete("all")
            self.canvas.create_text(self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2,
                                    text=f"No se pudo mostrar la imagen\n{e}", fill=MUTED, justify="center")

    def csize(self):
        return max(self.canvas.winfo_width(), 50), max(self.canvas.winfo_height(), 50)

    def reset_view(self):
        if not self.pil:
            return
        cw, ch = self.csize()
        iw, ih = self.pil.size
        self.fit_scale = min(cw / iw, ch / ih)
        self.scale = self.fit_scale
        self.cx, self.cy = iw / 2, ih / 2
        self.render()

    def rotate(self):
        if self.pil:
            self.pil = self.pil.transpose(Image.ROTATE_270)  # 90° a la derecha (solo en pantalla)
            self.reset_view()

    def render(self):
        if not self.pil:
            return
        cw, ch = self.csize()
        iw, ih = self.pil.size
        s = self.scale
        vw, vh = cw / s, ch / s
        x0 = (iw - vw) / 2 if vw >= iw else min(max(self.cx - vw / 2, 0), iw - vw)
        y0 = (ih - vh) / 2 if vh >= ih else min(max(self.cy - vh / 2, 0), ih - vh)
        self.cx, self.cy = x0 + vw / 2, y0 + vh / 2
        box = (max(x0, 0), max(y0, 0), min(x0 + vw, iw), min(y0 + vh, ih))
        crop = self.pil.crop(tuple(int(round(v)) for v in box))
        size = (max(int(round((box[2] - box[0]) * s)), 1), max(int(round((box[3] - box[1]) * s)), 1))
        img = crop.resize(size, Image.BILINEAR, reducing_gap=2.0)
        self.photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(int(round((box[0] - x0) * s)), int(round((box[1] - y0) * s)),
                                 anchor="nw", image=self.photo)

    def zoom(self, factor, mx=None, my=None):
        if not self.pil:
            return
        cw, ch = self.csize()
        mx = cw / 2 if mx is None else mx
        my = ch / 2 if my is None else my
        s0 = self.scale
        s1 = min(max(s0 * factor, self.fit_scale), max(self.MAX_SCALE, self.fit_scale))
        ix = self.cx - cw / s0 / 2 + mx / s0   # punto de la imagen bajo el cursor
        iy = self.cy - ch / s0 / 2 + my / s0
        self.scale = s1
        self.cx = ix - mx / s1 + cw / s1 / 2
        self.cy = iy - my / s1 + ch / s1 / 2
        self.render()

    def _on_wheel(self, e):
        self.zoom(1.2 if e.delta > 0 else 1 / 1.2, e.x, e.y)

    def _on_drag(self, e):
        if self._drag and self.pil:
            self.cx -= (e.x - self._drag[0]) / self.scale
            self.cy -= (e.y - self._drag[1]) / self.scale
            self._drag = (e.x, e.y)
            self.render()

    def _on_cfg(self, _):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(80, self._cfg_apply)

    def _cfg_apply(self):
        self._job = None
        if not self.pil:
            return
        at_fit = abs(self.scale - self.fit_scale) < 1e-6
        cw, ch = self.csize()
        iw, ih = self.pil.size
        self.fit_scale = min(cw / iw, ch / ih)
        if at_fit or self.scale < self.fit_scale:
            self.scale = self.fit_scale
            self.cx, self.cy = iw / 2, ih / 2
        self.render()


# ---------------------------------------------------------------- app
_Base = (ctk.CTk, TkinterDnD.DnDWrapper) if HAS_DND else (ctk.CTk,)


class App(*_Base):
    def __init__(self):
        super().__init__()
        self.dnd_ok = False
        if HAS_DND:
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                self.dnd_ok = True
            except Exception:
                pass
        ctk.set_appearance_mode("dark")
        self.configure(fg_color=BG)
        purge_stale_temp()
        self.login_state, self.login_dir = core.resolve_location()
        self.settings = core.load_settings()
        self.title(self.settings.get("title") or "Bóveda")
        icon = resource_path("icon.ico")
        if os.path.exists(icon):  # CTk pone su propio icono tras 200 ms
            self.after(300, lambda: self._safe(lambda: self.iconbitmap(icon)))

        self.vault = core.Vault()
        self.tmp_dir = None
        self.view = ("cat", "Todos")
        self.sel = set()
        self.cards, self.order, self.view_items = {}, [], []
        self.rendered = 0
        self.cols = 0
        self._gridded = 0
        self.thumbs = {}
        self.pending = set()
        self.busy = False
        self.gen = 0
        self.create_base = None
        self._layout_job = self._search_job = self._scroll_job = self._cd_job = None
        self.last_activity = time.time()
        self.ui_queue = queue.Queue()
        self.thumb_q = queue.Queue()
        threading.Thread(target=self._thumb_worker, daemon=True).start()
        for seq in ("<Motion>", "<Key>", "<Button>"):
            self.bind_all(seq, self._touch, add="+")
        self.bind_all("<F12>", lambda e: self.panic())
        self.bind_all("<Control-l>", lambda e: self.panic())
        self.bind_all("<Control-a>", self._select_all)
        self.bind_all("<Delete>", self._on_delete_key)
        self.bind("<Unmap>", self._on_unmap)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.show_login()
        self.after(60, self._pump)
        self.after(2000, self._watch)

    # --- infraestructura
    @staticmethod
    def _safe(fn):
        try:
            fn()
        except Exception:
            pass

    def _touch(self, _=None):
        self.last_activity = time.time()

    def post(self, fn, *args):
        self.ui_queue.put((fn, args))

    def _pump(self):
        try:
            while True:
                fn, args = self.ui_queue.get_nowait()
                self._safe(lambda: fn(*args))
        except queue.Empty:
            pass
        self.after(60, self._pump)

    def _watch(self):
        try:
            if self.vault.key:
                idle = self.settings.get("idle_minutes", 5)
                if desktop_locked():
                    self.lock()
                elif idle and not self.busy and time.time() - self.last_activity > idle * 60:
                    self.lock()
        finally:
            self.after(2000, self._watch)

    def _on_unmap(self, e):
        if e.widget is self and self.vault.key and self.settings.get("lock_on_minimize", True):
            self.after(120, self._check_minimized)

    def _check_minimized(self):
        try:
            if self.vault.key and self.state() == "iconic":
                self.lock()
        except tk.TclError:
            pass

    def update_setting(self, key, value):
        self.settings[key] = value
        core.save_settings(self.settings)
        if key == "block_capture":
            for w in [self] + [c for c in self.winfo_children() if isinstance(c, ctk.CTkToplevel)]:
                self.apply_capture_to(w)
        elif key == "title":
            self.title(value)

    def apply_capture_to(self, win):
        self._safe(lambda: set_capture_block(win, bool(self.settings.get("block_capture"))))

    def center(self, w, h):
        x = (self.winfo_screenwidth() - w) // 2
        y = max((self.winfo_screenheight() - h) // 2 - 30, 0)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def clear_window(self):
        for job in (self._layout_job, self._search_job, self._scroll_job, self._cd_job):
            if job:
                self._safe(lambda j=job: self.after_cancel(j))
        self._layout_job = self._search_job = self._scroll_job = self._cd_job = None
        for w in self.winfo_children():
            w.destroy()
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(0, weight=0)
        self.cards, self.order, self.view_items = {}, [], []
        self.rendered = self.cols = self._gridded = 0

    # --- acceso
    def show_login(self):
        self.clear_window()
        self.unbind("<Return>")
        self.title(self.settings.get("title") or "Bóveda")
        self.minsize(400, 560)
        self.center(440, 700)
        state = self.login_state
        creating = state == "create"

        card = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=20)
        card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.88)
        ctk.CTkLabel(card, text="🔒", font=ctk.CTkFont(size=54)).pack(pady=(26, 0))
        ctk.CTkLabel(card, text="Bóveda", font=ctk.CTkFont(size=28, weight="bold"), text_color=TEXT).pack()
        sub = {"create": "Crea tu contraseña maestra", "unlock": "Ingresa para continuar",
               "missing": "No se encuentra la bóveda"}[state]
        ctk.CTkLabel(card, text=sub, text_color=MUTED).pack(pady=(0, 16))

        self.login_msg = ctk.CTkLabel(card, text="", text_color=DANGER, wraplength=320)
        self.login_btn = None
        self.pw2 = None
        if state == "missing":
            ctk.CTkLabel(card, text=f"Ubicación guardada:\n{self.login_dir}\n\nConecta la unidad (por ejemplo la USB) "
                                    "y pulsa Reintentar.", text_color=TEXT, wraplength=320,
                         font=ctk.CTkFont(size=12)).pack(padx=24)
            self.pw1 = None
            self.login_btn = ctk.CTkButton(card, text="Reintentar", height=44, corner_radius=10, fg_color=ACCENT,
                                           hover_color=ACCENT_H, font=ctk.CTkFont(size=14, weight="bold"),
                                           command=self.retry_location)
            self.login_msg.pack(pady=(8, 0))
            self.login_btn.pack(fill="x", padx=28, pady=(8, 10))
        else:
            self.pw1 = ctk.CTkEntry(card, placeholder_text="Contraseña", show="•", height=42, corner_radius=10,
                                    fg_color=CARD, border_color=CARD)
            self.pw1.pack(fill="x", padx=28)
            if creating:
                self.pw2 = ctk.CTkEntry(card, placeholder_text="Repite la contraseña", show="•", height=42,
                                        corner_radius=10, fg_color=CARD, border_color=CARD)
                self.pw2.pack(fill="x", padx=28, pady=(10, 0))
                self.create_base = None
                row = ctk.CTkFrame(card, fg_color="transparent")
                row.pack(fill="x", padx=28, pady=(14, 0))
                self.loc_label = ctk.CTkLabel(row, text="Ubicación: oculta en este PC\n(predeterminada)",
                                              text_color=MUTED, wraplength=230, justify="left", anchor="w",
                                              font=ctk.CTkFont(size=11))
                self.loc_label.pack(side="left", fill="x", expand=True)
                ctk.CTkButton(row, text="Cambiar…", width=80, height=28, fg_color=CARD, hover_color=CARD_SEL,
                              command=self.pick_location).pack(side="right")
                self.remember_var = ctk.BooleanVar(value=True)
                ctk.CTkCheckBox(card, text="Recordar ubicación en este PC", variable=self.remember_var,
                                text_color=MUTED, fg_color=ACCENT, hover_color=ACCENT_H,
                                font=ctk.CTkFont(size=11)).pack(padx=28, pady=(8, 0), anchor="w")
            self.login_msg.pack(pady=(10, 0))
            self.login_btn = ctk.CTkButton(card, text="Crear bóveda" if creating else "Desbloquear", height=44,
                                           corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_H,
                                           font=ctk.CTkFont(size=14, weight="bold"), command=self.submit_login)
            self.login_btn.pack(fill="x", padx=28, pady=(8, 8))
            if creating:
                ctk.CTkLabel(card, text="Mínimo 8 caracteres. Si la olvidas, no hay forma\nde recuperar tus archivos.",
                             text_color=MUTED, font=ctk.CTkFont(size=11)).pack(pady=(0, 6))
            self.bind("<Return>", lambda e: self.submit_login())
            self.after(150, self.pw1.focus_set)

        links = ctk.CTkFrame(card, fg_color="transparent")
        links.pack(pady=(4, 18))
        for text, cmd in (("Abrir otra bóveda…", self.open_other_vault), ("Restaurar respaldo…", self.restore_backup)):
            ctk.CTkButton(links, text=text, width=150, height=26, fg_color="transparent", hover_color=CARD,
                          text_color=MUTED, font=ctk.CTkFont(size=11), command=cmd).pack(side="left", padx=2)
        self.after(250, lambda: self.apply_capture_to(self))
        if state == "unlock":
            self._lock_countdown()

    def _lock_countdown(self):
        self._cd_job = None
        try:
            fails, until = core.attempt_status()
            left = int(until - time.time()) + 1 if until > time.time() else 0
            if left > 0:
                self.login_btn.configure(state="disabled")
                self.login_msg.configure(text=f"Demasiados intentos. Espera {left} s.", text_color=DANGER)
                self._cd_job = self.after(500, self._lock_countdown)
            else:
                self.login_btn.configure(state="normal")
                if self.login_msg.cget("text").startswith("Demasiados"):
                    self.login_msg.configure(text="")
        except tk.TclError:
            pass

    def pick_location(self):
        d = filedialog.askdirectory(title="¿Dónde guardar la bóveda? (por ejemplo una USB)")
        if d:
            self.create_base = d
            self.loc_label.configure(text=f"Ubicación: {d}")

    def retry_location(self):
        self.login_state, self.login_dir = core.resolve_location()
        self.settings = core.load_settings()
        self.show_login()

    def open_other_vault(self):
        d = filedialog.askdirectory(title="Elige la carpeta de la bóveda (o la unidad donde está)")
        if not d:
            return
        found = core.find_vault(d)
        if not found:
            return messagebox.showerror("Bóveda", "No se encontró ninguna bóveda en esa carpeta.")
        remember = messagebox.askyesno("Bóveda", "¿Recordar esta ubicación en este PC?\n\n"
                                                 "Si eliges «No», tendrás que seleccionarla cada vez que abras la app.")
        core.set_data_dir(found)
        core.write_pointer(found if remember else None)
        self.login_dir, self.login_state = found, "unlock"
        self.settings = core.load_settings()
        self.show_login()

    def restore_backup(self):
        src = filedialog.askopenfilename(title="Elige el archivo de respaldo",
                                         filetypes=[("Respaldo de Bóveda", "*.vbk *.zip"), ("Todos", "*.*")])
        if not src:
            return
        self.login_msg.configure(text="Restaurando respaldo…", text_color=MUTED)
        self.update_idletasks()

        def work():
            try:
                folder = core.import_backup(src)
                self.post(self._restore_done, folder, None)
            except Exception as e:
                self.post(self._restore_done, None, str(e))

        threading.Thread(target=work, daemon=True).start()

    def _restore_done(self, folder, err):
        if err:
            self.login_msg.configure(text="", text_color=DANGER)
            return messagebox.showerror("Bóveda", f"No se pudo restaurar:\n{err}")
        core.set_data_dir(folder)
        core.write_pointer(folder)
        self.login_dir, self.login_state = folder, "unlock"
        self.settings = core.load_settings()
        self.show_login()
        messagebox.showinfo("Bóveda", "Respaldo restaurado. Ingresa con la contraseña que tenía esa bóveda.")

    def submit_login(self):
        if self.vault.key or self.login_state == "missing" or self.pw1 is None:
            return
        try:
            p1 = self.pw1.get()
        except tk.TclError:
            return
        if self.login_state == "create":
            if len(p1) < 8:
                return self.login_msg.configure(text="Mínimo 8 caracteres.", text_color=DANGER)
            if p1 != self.pw2.get():
                return self.login_msg.configure(text="Las contraseñas no coinciden.", text_color=DANGER)
            self.login_msg.configure(text="Creando…", text_color=MUTED)
            self.update_idletasks()
            try:
                self.vault.create(p1, base=self.create_base, remember=bool(self.remember_var.get()))
            except Exception as e:
                return self.login_msg.configure(text=f"No se pudo crear: {e}", text_color=DANGER)
            self.login_state = "unlock"
            self.settings = core.load_settings()
        else:
            fails, until = core.attempt_status()
            if until > time.time():
                return self._lock_countdown()
            self.login_msg.configure(text="Verificando…", text_color=MUTED)
            self.update_idletasks()
            try:
                ok = self.vault.unlock(p1)
            except Exception as e:
                return self.login_msg.configure(text=f"Error: {e}", text_color=DANGER)
            if not ok:
                fails, delay = core.register_fail()
                self.pw1.delete(0, "end")
                self.login_msg.configure(text="Contraseña incorrecta.", text_color=DANGER)
                if delay:
                    self._lock_countdown()
                return
            core.register_success()
        self.unbind("<Return>")
        self.show_main()

    # --- pantalla principal
    def show_main(self):
        self.clear_window()
        self.title(self.settings.get("title") or "Bóveda")
        self.minsize(980, 600)
        self.center(1200, 760)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.view = ("cat", "Todos")
        self.sel.clear()

        side = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color=PANEL)
        side.grid(row=0, column=0, sticky="nsew")
        side.pack_propagate(False)
        ctk.CTkButton(side, text="🔒  Bloquear  (F12)", height=38, corner_radius=10, fg_color=CARD,
                      hover_color=CARD_SEL, command=self.lock).pack(side="bottom", fill="x", padx=16, pady=(6, 16))
        ctk.CTkButton(side, text="⚙  Ajustes", height=38, corner_radius=10, fg_color=CARD, hover_color=CARD_SEL,
                      command=lambda: SettingsDialog(self)).pack(side="bottom", fill="x", padx=16, pady=(6, 0))
        self.del_original = ctk.CTkCheckBox(side, text="Triturar originales\nal agregar", text_color=MUTED,
                                            fg_color=ACCENT, hover_color=ACCENT_H, font=ctk.CTkFont(size=12))
        self.del_original.pack(side="bottom", anchor="w", padx=20, pady=(8, 4))
        self.btn_add = ctk.CTkButton(side, text="＋  Agregar archivos", height=46, corner_radius=12,
                                     fg_color=ACCENT, hover_color=ACCENT_H,
                                     font=ctk.CTkFont(size=14, weight="bold"), command=self.add_files)
        self.btn_add.pack(side="bottom", fill="x", padx=16, pady=(8, 0))
        ctk.CTkLabel(side, text="🔒  Bóveda", font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=22, pady=(24, 16))
        self.cat_btns = {}
        for key, label, icon in CATEGORIES:
            b = ctk.CTkButton(side, text="", anchor="w", height=40, corner_radius=10, fg_color="transparent",
                              hover_color=CARD, text_color=TEXT, font=ctk.CTkFont(size=14),
                              command=lambda k=key: self.set_view("cat", k))
            b.pack(fill="x", padx=14, pady=1)
            self.cat_btns[key] = (b, label, icon)
        head = ctk.CTkFrame(side, fg_color="transparent")
        head.pack(fill="x", padx=22, pady=(14, 0))
        ctk.CTkLabel(head, text="ÁLBUMES", text_color=MUTED, font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")
        ctk.CTkButton(head, text="＋", width=28, height=24, fg_color=CARD, hover_color=CARD_SEL,
                      command=self.new_album).pack(side="right")
        self.album_frame = ctk.CTkScrollableFrame(side, fg_color="transparent", scrollbar_button_color=CARD,
                                                  scrollbar_button_hover_color=CARD_SEL)
        self.album_frame.pack(fill="both", expand=True, padx=(8, 2), pady=(4, 0))

        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(2, weight=1)

        top = ctk.CTkFrame(self.content, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 6))
        self.search_entry = ctk.CTkEntry(top, placeholder_text="Buscar por nombre…", width=280, height=40,
                                         corner_radius=20, fg_color=PANEL, border_color=PANEL)
        self.search_entry.pack(side="left")
        self.search_entry.bind("<KeyRelease>", self._on_search)
        self.sort_var = ctk.StringVar(value=SORTS[0])
        ctk.CTkOptionMenu(top, values=list(SORTS), variable=self.sort_var, width=160, height=36,
                          fg_color=PANEL, button_color=CARD, button_hover_color=CARD_SEL,
                          command=lambda _: self.refresh()).pack(side="right")

        acts = ctk.CTkFrame(self.content, fg_color="transparent")
        acts.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 6))
        self.sel_label = ctk.CTkLabel(acts, text="", text_color=MUTED)
        self.sel_label.pack(side="left")

        def abtn(text, cmd, w, color=CARD, hover=CARD_SEL):
            b = ctk.CTkButton(acts, text=text, width=w, height=34, corner_radius=10, fg_color=color,
                              hover_color=hover, command=cmd)
            b.pack(side="right", padx=(6, 0))
            return b

        self.btn_del = abtn("Eliminar", self.delete_selected, 80, DANGER, DANGER_H)
        self.btn_exp = abtn("Exportar", self.export_selected, 80)
        self.btn_move = abtn("Mover a álbum", self.move_menu, 110)
        self.btn_ren = abtn("Renombrar", self.rename_selected, 90)
        self.btn_open = abtn("Abrir", self.open_selected, 70)

        self.gallery = ctk.CTkScrollableFrame(self.content, fg_color=BG, corner_radius=0,
                                              scrollbar_button_color=CARD, scrollbar_button_hover_color=CARD_SEL)
        self.gallery.grid(row=2, column=0, sticky="nsew", padx=(16, 6))
        foot = ctk.CTkFrame(self.content, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=22, pady=(4, 12))
        self.status = ctk.CTkLabel(foot, text="", text_color=MUTED, anchor="w")
        self.status.pack(side="left")
        self.progress = ctk.CTkProgressBar(foot, width=220, progress_color=ACCENT, fg_color=CARD)
        self.progress.set(0)

        self.content.bind("<Configure>", self._on_resize)
        if self.dnd_ok:
            for w in (self, self.content, self.gallery, getattr(self.gallery, "_parent_canvas", None)):
                if w is not None:
                    self._safe(lambda w=w: (w.drop_target_register(DND_FILES), w.dnd_bind("<<Drop>>", self.on_drop)))
        self.refresh()
        self._scroll_job = self.after(350, self._scroll_check)
        self.after(250, lambda: self.apply_capture_to(self))

    # --- álbumes y vistas
    def set_view(self, kind, value):
        self.view = (kind, value)
        self.sel.clear()
        self.refresh()

    def current_album(self):
        return self.view[1] if self.view[0] == "album" else ""

    def refresh_sidebar(self):
        if self.view[0] == "album" and self.view[1] not in self.vault.albums:
            self.view = ("cat", "Todos")
        counts = {k: 0 for k, _, _ in CATEGORIES}
        acount = {}
        for i in self.vault.items:
            counts["Todos"] += 1
            counts[i["type"]] += 1
            if i.get("album"):
                acount[i["album"]] = acount.get(i["album"], 0) + 1
        for key, (btn, label, icon) in self.cat_btns.items():
            active = self.view == ("cat", key)
            btn.configure(text=f"  {icon}   {label}   ({counts[key]})",
                          fg_color=ACCENT_DIM if active else "transparent",
                          text_color="white" if active else TEXT)
        for w in self.album_frame.winfo_children():
            w.destroy()
        if not self.vault.albums:
            ctk.CTkLabel(self.album_frame, text="Sin álbumes.\nPulsa ＋ para crear uno.", text_color=MUTED,
                         font=ctk.CTkFont(size=11), justify="left").pack(anchor="w", padx=10, pady=6)
        for a in self.vault.albums:
            active = self.view == ("album", a)
            b = ctk.CTkButton(self.album_frame, text=f"  ◈   {shorten(a, 16)}   ({acount.get(a, 0)})", anchor="w",
                              height=36, corner_radius=10, hover_color=CARD, font=ctk.CTkFont(size=13),
                              fg_color=ACCENT_DIM if active else "transparent",
                              text_color="white" if active else TEXT,
                              command=lambda n=a: self.set_view("album", n))
            b.pack(fill="x", pady=1)
            b.bind("<Button-3>", lambda e, n=a: self.album_menu(e, n))

    def _menu(self):
        return tk.Menu(self, tearoff=0, bg=CARD, fg=TEXT, activebackground=ACCENT, activeforeground="white",
                       bd=0, relief="flat")

    def album_menu(self, event, name):
        m = self._menu()
        m.add_command(label="Renombrar álbum", command=lambda: self.rename_album(name))
        m.add_command(label="Eliminar álbum (los archivos se conservan)", command=lambda: self.delete_album(name))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def new_album(self, move=None):
        name = ask_text(self, "Nuevo álbum", "Nombre del álbum:", button="Crear")
        if not name:
            return
        if not self.vault.add_album(name):
            return messagebox.showwarning("Bóveda", "Ya existe un álbum con ese nombre.")
        if move:
            self.move_to(move, name)
        else:
            self.refresh()

    def rename_album(self, old):
        new = ask_text(self, "Renombrar álbum", "Nuevo nombre:", initial=old)
        if not new or new == old:
            return
        if not self.vault.rename_album(old, new):
            return messagebox.showwarning("Bóveda", "Ya existe un álbum con ese nombre.")
        if self.view == ("album", old):
            self.view = ("album", new)
        self.refresh()

    def delete_album(self, name):
        if messagebox.askyesno("Eliminar álbum", f"¿Eliminar el álbum «{name}»?\n"
                                                 "Sus archivos NO se borran, quedan sin álbum."):
            self.vault.delete_album(name)
            self.refresh()

    def move_menu(self):
        sel = self.selected()
        if not sel:
            return
        m = self._menu()
        m.add_command(label="Sin álbum", command=lambda: self.move_to(sel, ""))
        for a in self.vault.albums:
            m.add_command(label=a, command=lambda n=a: self.move_to(sel, n))
        m.add_separator()
        m.add_command(label="Nuevo álbum…", command=lambda: self.new_album(move=sel))
        try:
            m.tk_popup(self.btn_move.winfo_rootx(), self.btn_move.winfo_rooty() + self.btn_move.winfo_height())
        finally:
            m.grab_release()

    def move_to(self, items, album):
        self.vault.move_to_album(items, album)
        self.refresh()

    # --- galería
    def _on_search(self, _=None):
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(250, self.refresh)

    def visible_items(self):
        kind, val = self.view
        q = self.search_entry.get().strip().lower()
        items = []
        for i in self.vault.items:
            if kind == "cat" and val != "Todos" and i["type"] != val:
                continue
            if kind == "album" and i.get("album", "") != val:
                continue
            if q and q not in i["name"].lower():
                continue
            items.append(i)
        mode = self.sort_var.get()
        if mode == "Más recientes":
            items.reverse()
        elif mode == "Nombre (A-Z)":
            items.sort(key=lambda i: i["name"].lower())
        elif mode == "Nombre (Z-A)":
            items.sort(key=lambda i: i["name"].lower(), reverse=True)
        elif mode == "Más grandes":
            items.sort(key=lambda i: i["size"], reverse=True)
        elif mode == "Más pequeños":
            items.sort(key=lambda i: i["size"])
        return items

    def refresh(self):
        self._search_job = None
        self.refresh_sidebar()
        self.view_items = self.visible_items()
        self.sel &= {i["id"] for i in self.view_items}
        for w in self.gallery.winfo_children():
            w.destroy()
        self.cards, self.order = {}, []
        self.rendered = self.cols = self._gridded = 0
        if not self.view_items:
            msg = ("Aún no hay archivos aquí.\nPulsa  ＋ Agregar archivos  o arrástralos a esta ventana."
                   if not self.vault.items else "Sin resultados.")
            ctk.CTkLabel(self.gallery, text=msg, text_color=MUTED, font=ctk.CTkFont(size=15)).pack(pady=120)
        else:
            self.render_more(PAGE)
        self.update_actions()
        self._update_status()

    def render_more(self, n=PAGE):
        chunk = self.view_items[self.rendered:self.rendered + n]
        for it in chunk:
            img = self.thumbs.get(it["id"])
            if img is None:
                img = placeholder(it["type"] if it["type"] != "Documento" else "Documento", it["name"])
                if it["type"] in ("Imagen", "Video") and it["id"] not in self.pending:
                    self.pending.add(it["id"])
                    self.thumb_q.put((self.gen, it, self.vault.key, self.vault.path_of(it)))
            card = Card(self.gallery, it, img, self.on_card_click, self.open_item)
            card.set_selected(it["id"] in self.sel)
            self.cards[it["id"]] = card
            self.order.append(it)
        self.rendered += len(chunk)
        self.layout()
        self._update_status()

    def _update_status(self):
        if self.busy:
            return
        total, shown = len(self.vault.items), len(self.view_items)
        txt = f"{shown} de {total} archivos"
        if self.rendered < shown:
            txt += f"  ·  mostrando {self.rendered}"
        self.status.configure(text=txt)

    def _scroll_check(self):
        self._scroll_job = None
        try:
            if self.gallery.winfo_exists():
                if self.rendered < len(self.view_items) and self.order:
                    last = self.cards[self.order[-1]["id"]]
                    canvas = self.gallery._parent_canvas
                    # carga más cuando la última tarjeta está cerca de la parte visible
                    if last.winfo_ismapped() and last.winfo_rooty() < canvas.winfo_rooty() + canvas.winfo_height() + 500:
                        self.render_more()
                self._scroll_job = self.after(350, self._scroll_check)
        except tk.TclError:
            pass

    def layout(self):
        self._layout_job = None
        if not self.order:
            return
        width = self.content.winfo_width() - 70
        cols = max(1, width // (CARD_W + GAP))
        start = self._gridded if cols == self.cols else 0
        for n in range(start, len(self.order)):
            self.cards[self.order[n]["id"]].grid(row=n // cols, column=n % cols, padx=GAP // 2, pady=GAP // 2)
        self.cols, self._gridded = cols, len(self.order)

    def _on_resize(self, _):
        if self._layout_job:
            self.after_cancel(self._layout_job)
        self._layout_job = self.after(120, self.layout)

    def on_card_click(self, item, event):
        self.focus_set()
        iid = item["id"]
        if event.state & 0x0004:  # Ctrl
            self.sel ^= {iid}
        else:
            self.sel = {iid}
        for cid, card in self.cards.items():
            card.set_selected(cid in self.sel)
        self.update_actions()

    def _select_all(self, _=None):
        if not self.vault.key or isinstance(self.focus_get(), tk.Entry):
            return
        self.sel = {i["id"] for i in self.view_items}
        for cid, card in self.cards.items():
            card.set_selected(cid in self.sel)
        self.update_actions()

    def _on_delete_key(self, _=None):
        if self.vault.key and not isinstance(self.focus_get(), tk.Entry):
            self.delete_selected()

    def update_actions(self):
        n = len(self.sel)
        ok = n > 0 and not self.busy
        for b in (self.btn_open, self.btn_exp, self.btn_del, self.btn_move):
            b.configure(state="normal" if ok else "disabled")
        self.btn_ren.configure(state="normal" if n == 1 and not self.busy else "disabled")
        self.sel_label.configure(text=f"{n} seleccionado(s)" if n else "Clic para seleccionar · Ctrl+clic varios · Ctrl+A todos")

    def selected(self):
        return [i for i in self.vault.items if i["id"] in self.sel]

    # --- miniaturas en segundo plano (cacheadas y cifradas)
    def _thumb_worker(self):
        while True:
            gen, item, key, path = self.thumb_q.get()
            img = None
            try:
                data = core.load_thumb(key, item["id"])
                if data:
                    img = Image.open(io.BytesIO(data)).convert("RGB")
                elif item["type"] == "Imagen":
                    img = thumb_from_image(Image.open(io.BytesIO(core.decrypt_to_bytes(key, path))))
                    core.save_thumb(key, item["id"], to_jpeg(img))
            except Exception:
                img = None
            self.post(self._thumb_done, gen, item["id"], img)

    def _thumb_done(self, gen, iid, img):
        self.pending.discard(iid)
        if gen != self.gen or img is None:
            return
        photo = ctk.CTkImage(light_image=img, dark_image=img, size=(THUMB, THUMB))
        self.thumbs[iid] = photo
        while len(self.thumbs) > MAX_THUMBS:
            self.thumbs.pop(next(iter(self.thumbs)))
        card = self.cards.get(iid)
        if card is not None and card.winfo_exists():
            card.set_image(photo)

    # --- acciones
    def set_status(self, text):
        self.status.configure(text=text)

    def set_busy(self, busy):
        self.busy = busy
        self.btn_add.configure(state="disabled" if busy else "normal")
        if busy:
            self.progress.set(0)
            self.progress.pack(side="right")
        else:
            self.progress.pack_forget()
        self.update_actions()

    def _progress(self, gen, frac, text):
        if gen == self.gen:
            self.progress.set(frac)
            self.set_status(text)

    def add_files(self):
        if self.busy:
            return
        paths = filedialog.askopenfilenames(title="Elige archivos a guardar")
        if paths:
            album = self.current_album()
            self.start_add([(p, album) for p in paths])

    def on_drop(self, event):
        if not self.vault.key or self.busy:
            return
        entries = []
        album = self.current_album()
        for p in self.tk.splitlist(event.data):
            if os.path.isdir(p):  # una carpeta soltada se guarda como álbum con su nombre
                name = os.path.basename(p.rstrip("\\/")) or "Carpeta"
                for root, _, files in os.walk(p):
                    entries += [(os.path.join(root, f), name) for f in sorted(files)]
            elif os.path.isfile(p):
                entries.append((p, album))
        self.start_add(entries)

    def start_add(self, entries):
        if self.busy or not entries:
            return
        delete = bool(self.del_original.get())
        if delete and not messagebox.askyesno(
                "Triturar originales",
                f"Se sobrescribirán y borrarán de forma permanente los {len(entries)} archivo(s) originales "
                "después de guardarlos en la bóveda.\n\n¿Continuar?"):
            return
        vault, gen = self.vault, self.gen
        self.set_busy(True)

        def work():
            errors = []
            for n, (p, album) in enumerate(entries, 1):
                self.post(self._progress, gen, (n - 1) / len(entries),
                          f"Cifrando {n}/{len(entries)}: {os.path.basename(p)}")
                try:
                    if album and album not in vault.albums:
                        vault.add_album(album)
                    item = vault.add(p, album or "")
                    try:
                        data = make_thumb_from_path(item["type"], p)
                        if data:
                            core.save_thumb(vault.key, item["id"], data)
                    except Exception:
                        pass
                    if delete:
                        core.shred_file(p)
                except Exception as e:
                    errors.append(f"{os.path.basename(p)}: {e}")
            self.post(self._add_done, gen, errors)

        threading.Thread(target=work, daemon=True).start()

    def _add_done(self, gen, errors):
        if gen != self.gen:
            return
        self.set_busy(False)
        self.refresh()
        if errors:
            messagebox.showerror("Algunos archivos fallaron", "\n".join(errors[:15]))

    def open_selected(self):
        for it in self.selected()[:5]:
            self.open_item(it)

    def open_item(self, item):
        if self.busy:
            return
        if item["type"] == "Imagen":
            imgs = [i for i in self.order if i["type"] == "Imagen"]
            idx = next((n for n, i in enumerate(imgs) if i["id"] == item["id"]), 0)
            Viewer(self, imgs, idx)
        else:
            self.open_external(item)

    def open_external(self, item):
        if not self.tmp_dir:
            self.tmp_dir = tempfile.mkdtemp(prefix="vlt_")
        out = os.path.join(self.tmp_dir, item["id"][:8] + "_" + item["name"])
        if os.path.exists(out):
            return os.startfile(out)
        self.set_status(f"Descifrando {item['name']}…")
        key, src, gen = self.vault.key, self.vault.path_of(item), self.gen

        def work():
            try:
                core.decrypt_to_path(key, src, out)
                self.post(os.startfile, out)
                self.post(self._notify, gen, "Abierto temporalmente. La copia se destruye al bloquear o cerrar.")
            except Exception as e:
                self.post(messagebox.showerror, "Error", str(e))

        threading.Thread(target=work, daemon=True).start()

    def _notify(self, gen, text):
        if gen == self.gen:
            self.set_status(text)

    def rename_selected(self):
        sel = self.selected()
        if len(sel) != 1:
            return
        new = ask_text(self, "Renombrar", "Nuevo nombre:", initial=sel[0]["name"])
        if new and new != sel[0]["name"]:
            self.vault.rename(sel[0], new)
            self.refresh()

    def export_selected(self):
        sel = self.selected()
        if not sel or self.busy:
            return
        folder = filedialog.askdirectory(title="Carpeta destino")
        if not folder:
            return
        vault, gen = self.vault, self.gen
        jobs = [(vault.path_of(i), unique_path(folder, i["name"])) for i in sel]
        self.set_busy(True)

        def work():
            msg = None
            try:
                for n, (src, dst) in enumerate(jobs, 1):
                    self.post(self._progress, gen, (n - 1) / len(jobs), f"Exportando {n}/{len(jobs)}…")
                    core.decrypt_to_path(vault.key, src, dst)
                msg = f"{len(jobs)} archivo(s) exportado(s)."
            except Exception as e:
                self.post(messagebox.showerror, "Error", str(e))
            self.post(self._job_done, gen, msg)

        threading.Thread(target=work, daemon=True).start()

    def _job_done(self, gen, msg):
        if gen != self.gen:
            return
        self.set_busy(False)
        self._update_status()
        if msg:
            self.set_status(msg)

    def backup_vault(self):
        if self.busy:
            return
        dst = filedialog.asksaveasfilename(
            title="Guardar respaldo", defaultextension=".vbk",
            initialfile=f"respaldo-boveda-{time.strftime('%Y%m%d')}.vbk",
            filetypes=[("Respaldo de Bóveda", "*.vbk")])
        if not dst:
            return
        gen = self.gen
        self.set_busy(True)

        def work():
            msg = None
            try:
                core.export_backup(dst, lambda f: self.post(self._progress, gen, f, "Creando respaldo…"))
                msg = "Respaldo guardado. Guárdalo en un lugar seguro: sigue protegido por tu contraseña."
            except Exception as e:
                self.post(messagebox.showerror, "Error", str(e))
            self.post(self._job_done, gen, msg)

        threading.Thread(target=work, daemon=True).start()

    def delete_selected(self):
        sel = self.selected()
        if not sel or self.busy:
            return
        if not messagebox.askyesno("Eliminar", f"¿Eliminar {len(sel)} archivo(s) de la bóveda?\n"
                                               "Esta acción no se puede deshacer."):
            return
        for it in sel:
            self.vault.remove(it)
            self.thumbs.pop(it["id"], None)
        self.sel.clear()
        self.refresh()

    # --- cierre / bloqueo
    def clean_tmp(self):
        if self.tmp_dir:
            core.secure_rmtree(self.tmp_dir)
            self.tmp_dir = None

    def lock(self):
        self.gen += 1
        self.clean_tmp()
        self.vault = core.Vault()
        self.thumbs.clear()
        self.pending.clear()
        self.sel.clear()
        self.busy = False
        self.login_state = "unlock" if os.path.exists(core.META_PATH) else "missing"
        self.login_dir = core.DATA_DIR
        self.show_login()

    def panic(self):
        """Bloqueo inmediato y ventana minimizada."""
        if self.vault.key:
            self.lock()
        self.iconify()

    def on_close(self):
        self.clean_tmp()
        self.destroy()


if __name__ == "__main__":
    if single_instance():
        App().mainloop()
