from __future__ import annotations

import json
import hashlib
import hmac
from io import BytesIO
import logging
from logging.handlers import RotatingFileHandler
import os
import queue
import re
import shutil
import smtplib
import ssl
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps
from tkinter import filedialog, messagebox

try:
    import keyring
except ImportError:  # pragma: no cover - handled in the UI
    keyring = None

try:
    import cairosvg
except ImportError:  # pragma: no cover - installed for the packaged app
    cairosvg = None

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
try:
    import pygame
except ImportError:  # pragma: no cover - capture still works without sound
    pygame = None


APP_NAME = "Camera Museu DEN"
KEYRING_SERVICE = "CameraMuseuDEN"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = application_dir()
DOCUMENTS_DIR = Path.home() / "Documents"
# Dados e recursos graváveis do usuário ficam fora da pasta do programa, em
# Documentos, para permanecerem disponíveis mesmo quando o app for atualizado.
DATA_DIR = DOCUMENTS_DIR / "Camera_Museu_DEN"
CONFIG_DIR = DATA_DIR
BUNDLED_ASSETS_DIR = (
    Path(getattr(sys, "_MEIPASS")) / "assets"
    if getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None)
    else APP_DIR / "assets"
)
ASSETS_DIR = DATA_DIR / "assets"
LOCAL_BACKGROUNDS_DIR = ASSETS_DIR / "fundos"
PHOTO_DIR = DATA_DIR / "fotos"
LOG_DIR = DATA_DIR / "logs"
SOUND_PATH = ASSETS_DIR / "audio" / "nudge.wav"
ICON_PATH = ASSETS_DIR / "icones" / "camera_museu.ico"
GOOGLE_APP_PASSWORDS_URL = "https://myaccount.google.com/apppasswords"
GOOGLE_APP_PASSWORDS_QR = ASSETS_DIR / "icones" / "google_app_passwords_qr.png"
ADMIN_PASSWORD_SALT = bytes.fromhex("935edb5c2ff4ae173bc4ab6f8a9b3617")
ADMIN_PASSWORD_HASH = bytes.fromhex(
    "89b624e1a8d9928e2d1e7a932c7b3473fc8000582097efe95f474f0a088a9b15"
)
ADMIN_PASSWORD_ITERATIONS = 240_000


def ensure_user_data() -> None:
    """Cria a pasta de dados e copia recursos empacotados apenas quando faltarem."""
    for directory in (DATA_DIR, ASSETS_DIR, LOCAL_BACKGROUNDS_DIR, PHOTO_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    if not BUNDLED_ASSETS_DIR.exists():
        return

    for source in BUNDLED_ASSETS_DIR.rglob("*"):
        if not source.is_file():
            continue
        destination = ASSETS_DIR / source.relative_to(BUNDLED_ASSETS_DIR)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source, destination)


ensure_user_data()


DEFAULT_SETTINGS: dict[str, Any] = {
    "sender_email": "",
    "sender_name": "Museu de Ciências Nucleares",
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 465,
    "smtp_security": "SSL",
    "camera_index": 0,
    "camera_width": 1280,
    "camera_height": 720,
    "camera_scale": 1.0,
    "camera_offset_x": 0,
    "camera_offset_y": 0,
    "countdown_seconds": 3,
    "mirror_preview": True,
    "fullscreen": True,
    "background_folder": str(LOCAL_BACKGROUNDS_DIR),
    "photo_folder": str(PHOTO_DIR),
    "selected_background": "",
}


def configure_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("camera_museu")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(
            LOG_DIR / "camera_museu.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        )
        logger.addHandler(handler)
    return logger


LOGGER = configure_logging()


def mask_email(address: str) -> str:
    if "@" not in address:
        return "endereço informado"
    local, domain = address.split("@", 1)
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}{'*' * max(2, len(local) - len(visible))}@{domain}"


class SettingsStore:
    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.path = CONFIG_DIR / "settings.json"

    def load(self) -> dict[str, Any]:
        data = dict(DEFAULT_SETTINGS)
        try:
            if self.path.exists():
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    loaded.pop("password", None)
                    loaded.pop("smtp_password", None)
                    data.update(loaded)

                    # Migra os caminhos padrão das versões anteriores para a
                    # pasta de dados em Documentos, sem alterar pastas
                    # escolhidas manualmente pelo usuário.
                    old_background = str(data.get("background_folder", ""))
                    legacy_backgrounds = {
                        str(DOCUMENTS_DIR / "Camera"),
                        str(APP_DIR / "assets" / "fundos"),
                    }
                    if old_background in legacy_backgrounds:
                        data["background_folder"] = str(LOCAL_BACKGROUNDS_DIR)

                    old_photo = str(data.get("photo_folder", ""))
                    if old_photo == str(APP_DIR / "fotos"):
                        data["photo_folder"] = str(PHOTO_DIR)
        except Exception as exc:
            LOGGER.warning("Configuração inválida; usando padrões: %s", exc)
        return data

    def save(self, settings: dict[str, Any]) -> None:
        safe = {k: v for k, v in settings.items() if "password" not in k.lower()}
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temp_path.replace(self.path)

    def get_password(self, sender_email: str) -> str:
        if not sender_email or keyring is None:
            return ""
        try:
            return keyring.get_password(KEYRING_SERVICE, sender_email) or ""
        except Exception as exc:
            LOGGER.warning("Não foi possível ler a credencial protegida: %s", exc)
            return ""

    def save_password(self, sender_email: str, password: str) -> None:
        if not password:
            return
        if keyring is None:
            raise RuntimeError("A biblioteca keyring não está instalada.")
        keyring.set_password(KEYRING_SERVICE, sender_email, password)


class CameraService:
    def __init__(self, index: int, width: int, height: int) -> None:
        self.index = index
        self.width = width
        self.height = height
        self.capture: cv2.VideoCapture | None = None
        self.frame = None
        self.lock = threading.Lock()
        self.running = False
        self.thread: threading.Thread | None = None
        self.error = ""

    def start(self) -> None:
        self.stop()
        self.running = True
        self.error = ""
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        try:
            capture = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
            if not capture.isOpened():
                capture.release()
                capture = cv2.VideoCapture(self.index)
            self.capture = capture
            if not capture.isOpened():
                self.error = "Não foi possível abrir a câmera."
                return
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            consecutive_failures = 0
            while self.running:
                ok, frame = capture.read()
                if ok and frame is not None:
                    consecutive_failures = 0
                    with self.lock:
                        self.frame = frame
                else:
                    consecutive_failures += 1
                    if consecutive_failures > 30:
                        self.error = "A câmera parou de fornecer imagens."
                        break
                    time.sleep(0.03)
        except Exception as exc:
            self.error = f"Falha na câmera: {exc}"
            LOGGER.exception("Falha no serviço de câmera")
        finally:
            if self.capture is not None:
                self.capture.release()
            self.capture = None
            self.running = False

    def get_frame(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def stop(self) -> None:
        self.running = False
        if self.capture is not None:
            self.capture.release()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.2)
        self.capture = None
        self.thread = None


class BackgroundRepository:
    def __init__(self, external_folder: str) -> None:
        self.external_folder = Path(external_folder)
        self.items: list[Path] = []
        self.refresh()

    def refresh(self) -> None:
        unique: dict[str, Path] = {}
        for folder in (LOCAL_BACKGROUNDS_DIR, self.external_folder):
            if not folder.exists():
                continue
            for path in folder.iterdir():
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                    # A cópia local torna o projeto portátil. Evita mostrar duas
                    # miniaturas quando a pasta externa contém o mesmo arquivo.
                    unique.setdefault(path.name.lower(), path.resolve())
        self.items = sorted(unique.values(), key=lambda p: p.name.lower())

    def index_of(self, selected: str) -> int:
        if not self.items:
            return -1
        try:
            target = str(Path(selected).resolve()).lower()
        except Exception:
            return 0
        for index, item in enumerate(self.items):
            if str(item).lower() == target:
                return index
        return 0


class ImageComposer:
    _overlay_source_cache: dict[tuple[str, int], np.ndarray] = {}
    _overlay_layer_cache: dict[
        tuple[str, int, tuple[int, int]], tuple[np.ndarray, np.ndarray, np.ndarray]
    ] = {}

    @staticmethod
    def _cover_cv(image: np.ndarray, size: tuple[int, int]) -> np.ndarray:
        target_width, target_height = size
        source_height, source_width = image.shape[:2]
        scale = max(target_width / source_width, target_height / source_height)
        resized_width = max(target_width, int(round(source_width * scale)))
        resized_height = max(target_height, int(round(source_height * scale)))
        interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
        resized = cv2.resize(
            image,
            (resized_width, resized_height),
            interpolation=interpolation,
        )
        left = (resized_width - target_width) // 2
        top = (resized_height - target_height) // 2
        return resized[top : top + target_height, left : left + target_width]

    @classmethod
    def _load_overlay(cls, path: Path) -> tuple[np.ndarray, int]:
        resolved = str(path.resolve())
        modified = path.stat().st_mtime_ns
        key = (resolved, modified)
        cached = cls._overlay_source_cache.get(key)
        if cached is not None:
            return cached, modified

        # imdecode funciona também com caminhos Unicode no Windows.
        encoded = np.fromfile(path, dtype=np.uint8)
        overlay = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
        if overlay is None:
            raise ValueError(f"Não foi possível abrir a moldura: {path.name}")
        if overlay.ndim == 2:
            overlay = cv2.cvtColor(overlay, cv2.COLOR_GRAY2BGRA)
        elif overlay.shape[2] == 3:
            overlay = cv2.cvtColor(overlay, cv2.COLOR_BGR2BGRA)
        cls._overlay_source_cache = {key: overlay}
        return overlay, modified

    @classmethod
    def _overlay_layers(
        cls, path: Path, size: tuple[int, int]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        source, modified = cls._load_overlay(path)
        key = (str(path.resolve()), modified, size)
        cached = cls._overlay_layer_cache.get(key)
        if cached is not None:
            return cached

        fitted = cls._cover_cv(source, size)
        foreground = fitted[:, :, :3].astype(np.uint16)
        alpha = fitted[:, :, 3:4].astype(np.uint16)
        inverse_alpha = 255 - alpha
        layers = (foreground, alpha, inverse_alpha)
        cls._overlay_layer_cache[key] = layers
        while len(cls._overlay_layer_cache) > 6:
            cls._overlay_layer_cache.pop(next(iter(cls._overlay_layer_cache)))
        return layers

    @staticmethod
    def compose(
        frame_bgr,
        overlay_path: Path | None,
        scale: float,
        offset_x: int,
        offset_y: int,
        mirror: bool,
        output_size: tuple[int, int] | None = None,
    ) -> Image.Image:
        camera = cv2.flip(frame_bgr, 1) if mirror else frame_bgr

        if overlay_path and overlay_path.exists():
            overlay_source, _modified = ImageComposer._load_overlay(overlay_path)
            target_size = output_size or (
                int(overlay_source.shape[1]),
                int(overlay_source.shape[0]),
            )
        else:
            target_size = output_size or (int(camera.shape[1]), int(camera.shape[0]))

        width, height = target_size
        base = ImageComposer._cover_cv(camera, target_size)
        safe_scale = max(0.3, float(scale))
        transform = np.array(
            [
                [safe_scale, 0, (1 - safe_scale) * width / 2 + int(offset_x)],
                [0, safe_scale, (1 - safe_scale) * height / 2 + int(offset_y)],
            ],
            dtype=np.float32,
        )
        camera_canvas = cv2.warpAffine(
            base,
            transform,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(28, 20, 8),
        )

        if overlay_path and overlay_path.exists():
            foreground, alpha, inverse_alpha = ImageComposer._overlay_layers(
                overlay_path, target_size
            )
            background = camera_canvas.astype(np.uint16)
            composed_bgr = (
                (foreground * alpha + background * inverse_alpha + 127) // 255
            ).astype(np.uint8)
        else:
            composed_bgr = camera_canvas

        composed_rgb = cv2.cvtColor(composed_bgr, cv2.COLOR_BGR2RGB)
        return Image.fromarray(composed_rgb)


@dataclass
class EmailResult:
    ok: bool
    message: str
    recipient: str = ""


class EmailService:
    @staticmethod
    def connect_and_login(settings: dict[str, Any], password: str):
        host = str(settings["smtp_host"]).strip()
        port = int(settings["smtp_port"])
        security = str(settings["smtp_security"]).upper()
        context = ssl.create_default_context()
        if security == "SSL":
            smtp = smtplib.SMTP_SSL(host, port, timeout=20, context=context)
        else:
            smtp = smtplib.SMTP(host, port, timeout=20)
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
        smtp.login(str(settings["sender_email"]).strip(), password)
        return smtp

    @staticmethod
    def send(
        settings: dict[str, Any], password: str, recipient: str, photo_path: Path
    ) -> None:
        msg = EmailMessage()
        sender_name = str(settings.get("sender_name", "Museu")).strip()
        sender_email = str(settings["sender_email"]).strip()
        msg["Subject"] = "Sua foto no Museu de Ciências Nucleares"
        msg["From"] = f"{sender_name} <{sender_email}>"
        msg["To"] = recipient
        msg.set_content(
            "Olá!\n\nSua foto está anexada. Obrigado pela visita!\n\n"
            "Museu de Ciências Nucleares"
        )
        data = photo_path.read_bytes()
        msg.add_attachment(
            data,
            maintype="image",
            subtype="jpeg",
            filename=photo_path.name,
        )
        with EmailService.connect_and_login(settings, password) as smtp:
            smtp.send_message(msg)


class CameraMuseuApp(ctk.CTk):
    TURQUOISE = "#08AEB7"
    TURQUOISE_HOVER = "#07949B"
    DARK = "#18242A"
    PANEL = "#26343B"
    TEXT = "#F4F8F9"

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        for folder in (
            CONFIG_DIR,
            LOCAL_BACKGROUNDS_DIR,
            PHOTO_DIR,
            LOG_DIR,
            SOUND_PATH.parent,
        ):
            folder.mkdir(parents=True, exist_ok=True)

        self.store = SettingsStore()
        self.settings = self.store.load()
        self.backgrounds = BackgroundRepository(self.settings["background_folder"])
        self.background_index = self.backgrounds.index_of(
            self.settings.get("selected_background", "")
        )
        self.camera = CameraService(
            int(self.settings["camera_index"]),
            int(self.settings["camera_width"]),
            int(self.settings["camera_height"]),
        )
        self.result_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.last_frame = None
        self.preview_image = None
        self.preview_pil: Image.Image | None = None
        self.last_photo: Path | None = None
        self.app_state = "INICIALIZANDO"
        self.closing = False
        self.sound_ready = False
        self.gallery_images: list[ctk.CTkImage] = []
        self.status_hide_job: str | None = None
        self.countdown_number: int | None = None
        self.countdown_size = 160
        self.countdown_font_cache: dict[int, Any] = {}
        self.nav_icons = self._load_nav_icons()

        self.title(APP_NAME)
        if ICON_PATH.exists():
            try:
                self.iconbitmap(str(ICON_PATH))
            except Exception as exc:
                LOGGER.warning("Não foi possível aplicar o ícone do app: %s", exc)
        self.geometry("1180x760")
        self.minsize(900, 600)
        self.configure(fg_color="#0B171D")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<F11>", lambda _event: self.toggle_fullscreen())
        self.bind("<Escape>", lambda _event: self.leave_fullscreen())
        self.bind("<space>", self._space_capture)

        self._build_ui()
        self._init_sound()
        self.camera.start()
        self.app_state = "PRONTO"
        self.set_status("Digite o e-mail e clique em Tirar foto.")
        self._apply_fullscreen(bool(self.settings.get("fullscreen", False)))
        self.after(15, self.update_video)
        self.after(150, self.poll_results)

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # O palco ocupa toda a janela. A navegação fica sobre a arte, como uma
        # navbar de quiosque, sem retirar espaço útil da moldura.
        self.stage = ctk.CTkFrame(self, fg_color="#071116", corner_radius=0)
        self.stage.grid(row=0, column=0, sticky="nsew")
        self.stage.grid_rowconfigure(0, weight=1)
        self.stage.grid_columnconfigure(0, weight=1)

        self.preview_label = ctk.CTkLabel(self.stage, text="", fg_color="#071116")
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        top = ctk.CTkFrame(
            self.stage,
            fg_color="#34383E",
            corner_radius=0,
            height=56,
            border_width=0,
        )
        top.place(relx=0.5, y=18, anchor="n")

        self.capture_button = ctk.CTkButton(
            top,
            text="Tirar Foto",
            image=self.nav_icons["camera"],
            compound="left",
            width=132,
            height=48,
            corner_radius=0,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=self.TURQUOISE,
            hover_color=self.TURQUOISE_HOVER,
            command=self.start_capture,
        )
        self.capture_button.grid(row=0, column=0, padx=(8, 6), pady=6)

        ctk.CTkButton(
            top,
            text="Moldura",
            image=self.nav_icons["moldura"],
            compound="left",
            width=140,
            height=48,
            corner_radius=0,
            fg_color=self.TURQUOISE,
            hover_color=self.TURQUOISE_HOVER,
            font=ctk.CTkFont(size=15),
            command=self.open_gallery,
        ).grid(row=0, column=1, padx=6, pady=6)

        ctk.CTkLabel(
            top,
            text="E-mail:",
            image=self.nav_icons["email"],
            compound="left",
            text_color=self.TEXT,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(
            row=0, column=2, padx=(18, 10)
        )
        self.recipient_entry = ctk.CTkEntry(
            top,
            width=270,
            height=32,
            placeholder_text="visitante@exemplo.com",
            corner_radius=0,
            fg_color="#3B3F45",
            border_color="#E5E8EA",
            border_width=1,
        )
        self.recipient_entry.grid(row=0, column=3, padx=(0, 10))

        ctk.CTkButton(
            top,
            text="",
            image=self.nav_icons["configuracoes"],
            width=54,
            height=48,
            corner_radius=0,
            anchor="center",
            compound="left",
            font=ctk.CTkFont(size=21),
            fg_color=self.TURQUOISE,
            hover_color=self.TURQUOISE_HOVER,
            command=self.open_settings,
        ).grid(row=0, column=4, padx=(4, 8), pady=6)

        self.status_badge = ctk.CTkFrame(
            self.stage,
            fg_color="#20272C",
            corner_radius=8,
            border_width=1,
            border_color="#3D4C53",
        )
        self.status_label = ctk.CTkLabel(
            self.status_badge,
            text="Inicializando…",
            text_color="#D7E4E8",
            font=ctk.CTkFont(size=13),
        )
        self.status_label.pack(padx=14, pady=7)

        # Mantido somente como estado interno para a galeria. O nome da
        # moldura não ocupa mais a parte inferior da tela principal.
        self.background_name_label = ctk.CTkLabel(
            self.stage,
            text="",
            text_color="#A7C4CC",
            font=ctk.CTkFont(size=12),
        )
        self._update_background_name()

    @staticmethod
    def _load_nav_icons() -> dict[str, ctk.CTkImage]:
        icon_dir = ASSETS_DIR / "icones"
        icon_paths = {
            "camera": icon_dir / "camera.svg",
            "moldura": icon_dir / "moldura.png",
            "email": icon_dir / "email.png",
            "configuracoes": icon_dir / "configuracoes.png",
        }
        sizes = {
            "camera": (20, 20),
            "moldura": (20, 20),
            "email": (16, 16),
            "configuracoes": (24, 24),
        }
        icons: dict[str, ctk.CTkImage] = {}
        for name, size in sizes.items():
            path = icon_paths[name]
            if path.suffix.lower() == ".svg":
                if cairosvg is None:
                    raise RuntimeError("A biblioteca cairosvg não está instalada.")
                rendered = cairosvg.svg2png(
                    url=str(path),
                    output_width=size[0] * 4,
                    output_height=size[1] * 4,
                )
                with Image.open(BytesIO(rendered)) as source:
                    image = source.convert("RGBA").copy()
            else:
                with Image.open(path) as source:
                    image = source.convert("RGBA").copy()
            icons[name] = ctk.CTkImage(
                light_image=image,
                dark_image=image,
                size=size,
            )
        return icons

    def current_background(self) -> Path | None:
        if 0 <= self.background_index < len(self.backgrounds.items):
            return self.backgrounds.items[self.background_index]
        return None

    def _update_background_name(self) -> None:
        current = self.current_background()
        self.background_name_label.configure(
            text=f"Moldura: {current.name}" if current else "Sem moldura"
        )

    def _init_sound(self) -> None:
        if pygame is None or not SOUND_PATH.exists():
            LOGGER.warning("Som de captura indisponível")
            return
        try:
            pygame.mixer.init()
            self.shutter_sound = pygame.mixer.Sound(str(SOUND_PATH))
            self.sound_ready = True
        except Exception as exc:
            LOGGER.warning("Não foi possível inicializar o áudio: %s", exc)

    def play_shutter(self) -> None:
        if self.sound_ready:
            try:
                self.shutter_sound.play()
            except Exception as exc:
                LOGGER.warning("Falha ao reproduzir o som: %s", exc)

    def set_status(self, text: str, color: str = "#D7E4E8") -> None:
        self.status_label.configure(text=text, text_color=color)
        self.status_badge.place(relx=0.5, y=84, anchor="n")
        self.status_badge.lift()
        if self.status_hide_job is not None:
            self.after_cancel(self.status_hide_job)
        self.status_hide_job = self.after(4500, self._hide_status)

    def _hide_status(self) -> None:
        self.status_badge.place_forget()
        self.status_hide_job = None

    def update_video(self) -> None:
        if self.closing:
            return
        frame = self.camera.get_frame()
        if frame is not None:
            self.last_frame = frame
            width = max(640, self.preview_label.winfo_width())
            height = max(400, self.preview_label.winfo_height())
            try:
                composed = ImageComposer.compose(
                    frame,
                    self.current_background(),
                    float(self.settings["camera_scale"]),
                    int(self.settings["camera_offset_x"]),
                    int(self.settings["camera_offset_y"]),
                    bool(self.settings["mirror_preview"]),
                    output_size=(width, height),
                )
                composed = self._draw_countdown_overlay(composed)
                self.preview_pil = composed
                display = composed
                self.preview_image = ctk.CTkImage(
                    light_image=display, dark_image=display, size=display.size
                )
                self.preview_label.configure(image=self.preview_image, text="")
            except Exception as exc:
                LOGGER.exception("Falha ao compor a prévia")
                self.set_status(f"Falha ao exibir a imagem: {exc}", "#FFB4A9")
        elif self.camera.error:
            self.preview_label.configure(
                image=None,
                text=f"📷\n\n{self.camera.error}\n\nAbra Configurações para escolher outra câmera.",
                font=ctk.CTkFont(size=20),
                text_color="#C6D5DA",
            )
        self.after(33, self.update_video)

    def _draw_countdown_overlay(self, image: Image.Image) -> Image.Image:
        """Desenha a animação no frame, preservando transparência real."""
        if self.app_state != "CONTAGEM" or self.countdown_number is None:
            return image

        canvas = image.convert("RGBA")
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        width, height = canvas.size
        pulse = self.countdown_size / 160.0
        diameter = int(min(width, height) * 0.28 * pulse)
        center_x, center_y = width // 2, height // 2
        radius = diameter // 2
        circle = (
            center_x - radius,
            center_y - radius,
            center_x + radius,
            center_y + radius,
        )
        outline_width = max(4, diameter // 45)
        draw.ellipse(
            circle,
            fill=(247, 250, 251, 236),
            outline=(8, 174, 183, 255),
            width=outline_width,
        )

        font_size = max(56, int(diameter * 0.58))
        font_path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "segoeuib.ttf"
        font = self.countdown_font_cache.get(font_size)
        if font is None:
            try:
                font = ImageFont.truetype(str(font_path), font_size)
            except OSError:
                font = ImageFont.load_default()
            self.countdown_font_cache[font_size] = font
        draw.text(
            (center_x, center_y - int(diameter * 0.025)),
            str(self.countdown_number),
            font=font,
            fill=(8, 174, 183, 255),
            anchor="mm",
        )
        return Image.alpha_composite(canvas, overlay).convert("RGB")

    def _space_capture(self, _event=None) -> None:
        if self.focus_get() is not self.recipient_entry:
            self.start_capture()

    def start_capture(self) -> None:
        if self.app_state != "PRONTO":
            return
        if self.last_frame is None:
            self.set_status("A câmera ainda não está pronta.", "#FFB4A9")
            return
        recipient = self.recipient_entry.get().strip()
        if recipient and not EMAIL_RE.match(recipient):
            self.set_status("Digite um endereço de e-mail válido.", "#FFB4A9")
            self.recipient_entry.focus_set()
            return
        self.app_state = "CONTAGEM"
        self.capture_button.configure(state="disabled", text="Prepare-se…")
        seconds = max(1, min(10, int(self.settings.get("countdown_seconds", 3))))
        self._countdown_tick(seconds)

    def _countdown_tick(self, number: int) -> None:
        if self.closing or self.app_state != "CONTAGEM":
            return
        if number <= 0:
            self.countdown_number = None
            self._perform_capture()
            return
        self.countdown_number = number
        self._pulse_countdown(number, 0)

    def _pulse_countdown(self, number: int, step: int) -> None:
        if self.app_state != "CONTAGEM":
            return
        sizes = [115, 135, 158, 180, 170, 160]
        if step < len(sizes):
            self.countdown_size = sizes[step]
            self.after(90, lambda: self._pulse_countdown(number, step + 1))
        else:
            delay = max(10, 1000 - len(sizes) * 90)
            self.after(delay, lambda: self._countdown_tick(number - 1))

    def _perform_capture(self) -> None:
        self.app_state = "CAPTURANDO"
        frame = self.camera.get_frame()
        if frame is None:
            self._finish_capture_error("A câmera não entregou a imagem da captura.")
            return
        try:
            final_image = ImageComposer.compose(
                frame,
                self.current_background(),
                float(self.settings["camera_scale"]),
                int(self.settings["camera_offset_x"]),
                int(self.settings["camera_offset_y"]),
                bool(self.settings["mirror_preview"]),
            )
            folder = Path(str(self.settings.get("photo_folder", PHOTO_DIR)))
            dated_folder = folder / datetime.now().strftime("%Y-%m-%d")
            dated_folder.mkdir(parents=True, exist_ok=True)
            path = dated_folder / f"foto_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.jpg"
            final_image.save(path, "JPEG", quality=95, optimize=True)
            self.last_photo = path
            self.play_shutter()
            self._flash()
            LOGGER.info("Foto salva: %s", path)
        except Exception as exc:
            LOGGER.exception("Falha ao salvar a foto")
            self._finish_capture_error(f"Não foi possível salvar a foto: {exc}")
            return

        recipient = self.recipient_entry.get().strip()
        if recipient:
            self._send_photo(recipient, path)
        else:
            self.app_state = "PRONTO"
            self.capture_button.configure(state="normal", text="Tirar Foto")
            self.set_status("Foto salva com sucesso.", "#8BE6B1")

    def _flash(self) -> None:
        flash = ctk.CTkFrame(self.stage, fg_color="white", corner_radius=0)
        flash.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.after(130, flash.destroy)

    def _finish_capture_error(self, message: str) -> None:
        self.app_state = "PRONTO"
        self.capture_button.configure(state="normal", text="Tirar Foto")
        self.set_status(message, "#FFB4A9")

    def _send_photo(self, recipient: str, photo_path: Path) -> None:
        sender = str(self.settings.get("sender_email", "")).strip()
        password = self.store.get_password(sender)
        if not sender or not password:
            self.app_state = "PRONTO"
            self.capture_button.configure(state="normal", text="Tirar Foto")
            self.set_status(
                "Foto salva. Configure o e-mail remetente e a senha para enviar.",
                "#FFD37A",
            )
            return
        self.app_state = "ENVIANDO"
        self.capture_button.configure(text="Enviando…", state="disabled")
        self.set_status(f"Enviando para {mask_email(recipient)}…")
        snapshot = dict(self.settings)

        def worker() -> None:
            try:
                EmailService.send(snapshot, password, recipient, photo_path)
                result = EmailResult(True, "Foto enviada com sucesso!", recipient)
            except Exception as exc:
                LOGGER.warning("Falha no envio SMTP: %s", exc)
                result = EmailResult(False, self._friendly_email_error(exc), recipient)
            self.result_queue.put(("email", result))

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _friendly_email_error(exc: Exception) -> str:
        if isinstance(exc, smtplib.SMTPAuthenticationError):
            return "Autenticação recusada. Verifique o e-mail e a senha de aplicativo."
        if isinstance(exc, (TimeoutError, smtplib.SMTPServerDisconnected)):
            return "O servidor de e-mail não respondeu. A foto continua salva."
        return f"Não foi possível enviar. A foto continua salva. ({exc})"

    def poll_results(self) -> None:
        if self.closing:
            return
        try:
            while True:
                event, payload = self.result_queue.get_nowait()
                if event == "email":
                    result: EmailResult = payload
                    self.app_state = "PRONTO"
                    self.capture_button.configure(state="normal", text="Tirar Foto")
                    if result.ok:
                        self.set_status(
                            f"Foto enviada para {mask_email(result.recipient)}.", "#8BE6B1"
                        )
                        self.recipient_entry.delete(0, "end")
                    else:
                        self.set_status(result.message, "#FFB4A9")
                elif event == "smtp_test":
                    ok, text_value = payload
                    self.set_status(text_value, "#8BE6B1" if ok else "#FFB4A9")
        except queue.Empty:
            pass
        self.after(150, self.poll_results)

    def previous_background(self) -> None:
        if not self.backgrounds.items:
            self.set_status("Nenhuma moldura encontrada.", "#FFD37A")
            return
        self.background_index = (self.background_index - 1) % len(self.backgrounds.items)
        self._persist_background()

    def next_background(self) -> None:
        if not self.backgrounds.items:
            self.set_status("Nenhuma moldura encontrada.", "#FFD37A")
            return
        self.background_index = (self.background_index + 1) % len(self.backgrounds.items)
        self._persist_background()

    def _persist_background(self) -> None:
        current = self.current_background()
        self.settings["selected_background"] = str(current) if current else ""
        self.store.save(self.settings)
        self._update_background_name()

    def choose_background_file(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Escolher fundo ou moldura",
            initialdir=self.settings.get("background_folder", str(APP_DIR)),
            filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp"), ("Todos", "*.*")],
        )
        if not selected:
            return
        path = Path(selected).resolve()
        if path not in self.backgrounds.items:
            self.backgrounds.items.append(path)
        self.background_index = self.backgrounds.items.index(path)
        self._persist_background()

    def open_gallery(self) -> None:
        self.backgrounds.refresh()
        window = ctk.CTkToplevel(self)
        window.title("Fundos e molduras")
        window.geometry("820x620")
        window.transient(self)
        window.grab_set()
        window.grid_rowconfigure(1, weight=1)
        window.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(window, fg_color=self.DARK, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            header, text="Escolha uma moldura", font=ctk.CTkFont(size=22, weight="bold")
        ).pack(side="left", padx=18, pady=16)
        ctk.CTkButton(
            header,
            text="Escolher arquivo…",
            fg_color=self.TURQUOISE,
            command=lambda: (window.destroy(), self.choose_background_file()),
        ).pack(side="right", padx=18)
        ctk.CTkButton(
            header,
            text="Sem moldura",
            width=110,
            fg_color=self.PANEL,
            hover_color="#344952",
            command=lambda: (setattr(self, "background_index", -1), self._persist_background(), window.destroy()),
        ).pack(side="right", padx=(4, 0))

        scroll = ctk.CTkScrollableFrame(window, fg_color="#101D23")
        scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        for column in range(3):
            scroll.grid_columnconfigure(column, weight=1)
        self.gallery_images = []

        def select(index: int) -> None:
            self.background_index = index
            self._persist_background()
            window.destroy()

        for index, path in enumerate(self.backgrounds.items):
            try:
                with Image.open(path) as source:
                    thumb = ImageOps.contain(
                        source.convert("RGBA"), (220, 140), Image.Resampling.LANCZOS
                    )
                    checker = Image.new("RGB", thumb.size, "#294049")
                    checker.paste(thumb, mask=thumb.getchannel("A"))
                ctk_image = ctk.CTkImage(checker, size=checker.size)
                self.gallery_images.append(ctk_image)
                button = ctk.CTkButton(
                    scroll,
                    text=path.name,
                    image=ctk_image,
                    compound="top",
                    height=185,
                    fg_color=self.TURQUOISE if index == self.background_index else self.PANEL,
                    hover_color="#36505A",
                    command=lambda i=index: select(i),
                )
                button.grid(row=index // 3, column=index % 3, padx=8, pady=8, sticky="nsew")
            except Exception as exc:
                LOGGER.warning("Imagem ignorada na galeria (%s): %s", path, exc)

        if not self.backgrounds.items:
            ctk.CTkLabel(
                scroll,
                text="Nenhuma imagem encontrada.\nUse ‘Escolher arquivo…’.",
                font=ctk.CTkFont(size=18),
            ).grid(row=0, column=0, columnspan=3, pady=80)

    def open_settings(self) -> None:
        original_transform = (
            float(self.settings["camera_scale"]),
            int(self.settings["camera_offset_x"]),
            int(self.settings["camera_offset_y"]),
        )
        settings_saved = {"value": False}
        window = ctk.CTkToplevel(self)
        window.title("Configurações")
        if ICON_PATH.exists():
            try:
                window.iconbitmap(str(ICON_PATH))
            except Exception as exc:
                LOGGER.warning("Não foi possível aplicar o ícone às configurações: %s", exc)
        window.geometry("840x760")
        window.minsize(780, 700)
        window.transient(self)
        window.grab_set()
        window.grid_rowconfigure(0, weight=1)
        window.grid_columnconfigure(0, weight=1)

        tabs = ctk.CTkTabview(window, segmented_button_selected_color=self.TURQUOISE)
        tabs.grid(row=0, column=0, sticky="nsew", padx=16, pady=(12, 4))
        email_tab = tabs.add("E-mail")
        camera_tab = tabs.add("Câmera")
        experience_tab = tabs.add("Experiência")
        for tab in (email_tab, camera_tab, experience_tab):
            tab.grid_columnconfigure(1, weight=1)

        stored_sender = str(self.settings["sender_email"]).strip()
        stored_password = self.store.get_password(stored_sender)
        locked_password_text = "•" * 16 if stored_password else ""
        password_unlocked = {"value": False}

        variables: dict[str, Any] = {
            "sender_email": ctk.StringVar(value=str(self.settings["sender_email"])),
            "sender_name": ctk.StringVar(value=str(self.settings["sender_name"])),
            "smtp_host": ctk.StringVar(value=str(self.settings["smtp_host"])),
            "smtp_port": ctk.StringVar(value=str(self.settings["smtp_port"])),
            "smtp_security": ctk.StringVar(value=str(self.settings["smtp_security"])),
            "password": ctk.StringVar(value=locked_password_text),
            "camera_index": ctk.StringVar(value=str(self.settings["camera_index"])),
            "camera_width": ctk.StringVar(value=str(self.settings["camera_width"])),
            "camera_height": ctk.StringVar(value=str(self.settings["camera_height"])),
            "countdown_seconds": ctk.StringVar(value=str(self.settings["countdown_seconds"])),
            "background_folder": ctk.StringVar(value=str(self.settings["background_folder"])),
            "photo_folder": ctk.StringVar(value=str(self.settings["photo_folder"])),
            "mirror_preview": ctk.BooleanVar(value=bool(self.settings["mirror_preview"])),
            "fullscreen": ctk.BooleanVar(value=bool(self.settings["fullscreen"])),
        }

        def add_entry(parent, row: int, label: str, key: str, show: str | None = None):
            ctk.CTkLabel(parent, text=label).grid(row=row, column=0, padx=12, pady=8, sticky="w")
            entry = ctk.CTkEntry(parent, textvariable=variables[key], show=show or "")
            entry.grid(row=row, column=1, padx=12, pady=8, sticky="ew")
            return entry

        add_entry(email_tab, 0, "E-mail remetente", "sender_email")
        add_entry(email_tab, 1, "Nome de exibição", "sender_name")
        password_entry = add_entry(email_tab, 2, "Senha de aplicativo", "password", "•")
        password_entry.configure(state="disabled")
        password_help = ctk.CTkLabel(
            email_tab,
            text=(
                "Credencial protegida e salva no Windows. Desbloqueie para visualizar ou alterar."
                if stored_password
                else "Nenhuma credencial salva. Desbloqueie para cadastrar."
            ),
            text_color="#90AEB8",
        )
        password_help.grid(row=3, column=1, padx=12, sticky="w")

        password_actions = ctk.CTkFrame(email_tab, fg_color="transparent")
        password_actions.grid(row=4, column=1, padx=12, pady=8, sticky="w")
        show_password_var = ctk.BooleanVar(value=False)
        show_password_check = ctk.CTkCheckBox(
            password_actions,
            text="Mostrar senha",
            variable=show_password_var,
            state="disabled",
            command=lambda: password_entry.configure(
                show="" if show_password_var.get() else "•"
            ),
        )
        show_password_check.pack(side="left")

        def unlock_password_field() -> None:
            def unlocked() -> None:
                password_unlocked["value"] = True
                variables["password"].set(stored_password)
                password_entry.configure(state="normal", show="•")
                show_password_var.set(False)
                show_password_check.configure(state="normal")
                unlock_button.configure(text="Senha desbloqueada", state="disabled")
                password_help.configure(
                    text="Acesso administrativo liberado nesta janela.",
                    text_color="#8BE6B1",
                )
                password_entry.focus_set()

            self._request_admin_unlock(window, unlocked)

        unlock_button = ctk.CTkButton(
            password_actions,
            text="Desbloquear para editar",
            width=180,
            height=30,
            fg_color="#52656D",
            hover_color="#647A84",
            command=unlock_password_field,
        )
        unlock_button.pack(side="left", padx=(14, 0))
        add_entry(email_tab, 5, "Servidor SMTP", "smtp_host")
        add_entry(email_tab, 6, "Porta", "smtp_port")
        ctk.CTkLabel(email_tab, text="Segurança").grid(row=7, column=0, padx=12, pady=8, sticky="w")
        ctk.CTkOptionMenu(
            email_tab,
            values=["SSL", "STARTTLS"],
            variable=variables["smtp_security"],
            fg_color=self.TURQUOISE,
        ).grid(row=7, column=1, padx=12, pady=8, sticky="w")

        guide = ctk.CTkFrame(
            email_tab,
            fg_color="#202E35",
            corner_radius=12,
            border_width=1,
            border_color="#3B525C",
        )
        guide.grid(row=8, column=0, columnspan=2, padx=12, pady=(16, 8), sticky="ew")
        guide.grid_columnconfigure(1, weight=1)

        if GOOGLE_APP_PASSWORDS_QR.exists():
            with Image.open(GOOGLE_APP_PASSWORDS_QR) as source:
                qr_pil = source.convert("RGBA").copy()
            window.google_qr_image = ctk.CTkImage(
                light_image=qr_pil,
                dark_image=qr_pil,
                size=(142, 142),
            )
            ctk.CTkLabel(
                guide,
                text="",
                image=window.google_qr_image,
                fg_color="white",
                corner_radius=8,
            ).grid(row=0, column=0, rowspan=4, padx=16, pady=16)

        ctk.CTkLabel(
            guide,
            text="Como configurar o Gmail",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#F2F8FA",
        ).grid(row=0, column=1, padx=(4, 16), pady=(16, 5), sticky="w")
        ctk.CTkLabel(
            guide,
            text=(
                "1. Ative a verificação em duas etapas da Conta Google.\n"
                "2. Leia o QR ou abra a página e crie uma senha de app.\n"
                "3. Informe o Gmail completo e a senha de 16 caracteres acima.\n"
                "4. Clique em Salvar e depois em Testar SMTP."
            ),
            justify="left",
            anchor="w",
            wraplength=520,
            text_color="#C9D9DE",
        ).grid(row=1, column=1, padx=(4, 16), pady=4, sticky="ew")
        ctk.CTkButton(
            guide,
            text="Abrir página de senhas de app",
            height=34,
            width=230,
            fg_color=self.TURQUOISE,
            hover_color=self.TURQUOISE_HOVER,
            command=lambda: webbrowser.open(GOOGLE_APP_PASSWORDS_URL),
        ).grid(row=2, column=1, padx=(4, 16), pady=(8, 4), sticky="w")
        ctk.CTkLabel(
            guide,
            text=GOOGLE_APP_PASSWORDS_URL,
            text_color="#7FCBD0",
            font=ctk.CTkFont(size=11),
        ).grid(row=3, column=1, padx=(4, 16), pady=(0, 14), sticky="w")

        add_entry(camera_tab, 0, "Índice da câmera", "camera_index")
        add_entry(camera_tab, 1, "Largura", "camera_width")
        add_entry(camera_tab, 2, "Altura", "camera_height")
        ctk.CTkCheckBox(
            camera_tab, text="Espelhar imagem", variable=variables["mirror_preview"]
        ).grid(row=3, column=1, padx=12, pady=10, sticky="w")

        movement = ctk.CTkFrame(camera_tab, fg_color=self.PANEL)
        movement.grid(row=4, column=0, columnspan=2, padx=12, pady=18)
        ctk.CTkLabel(movement, text="Posição e zoom", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=5, pady=8
        )
        controls = [
            ("↑", 1, 2, lambda: self.move_camera(0, -12)),
            ("←", 2, 1, lambda: self.move_camera(-12, 0)),
            ("Centralizar", 2, 2, self.reset_camera),
            ("→", 2, 3, lambda: self.move_camera(12, 0)),
            ("↓", 3, 2, lambda: self.move_camera(0, 12)),
            ("−", 2, 0, lambda: self.adjust_scale(-0.05)),
            ("+", 2, 4, lambda: self.adjust_scale(0.05)),
        ]
        for text_value, row, column, command in controls:
            ctk.CTkButton(
                movement,
                text=text_value,
                width=92 if text_value == "Centralizar" else 52,
                fg_color=self.TURQUOISE,
                command=command,
            ).grid(row=row, column=column, padx=5, pady=5)

        add_entry(experience_tab, 0, "Cronômetro (segundos)", "countdown_seconds")
        add_entry(experience_tab, 1, "Pasta de molduras", "background_folder")
        add_entry(experience_tab, 2, "Pasta das fotos", "photo_folder")
        ctk.CTkCheckBox(
            experience_tab, text="Iniciar em tela cheia", variable=variables["fullscreen"]
        ).grid(row=3, column=1, padx=12, pady=10, sticky="w")
        footer = ctk.CTkFrame(window, fg_color="transparent")
        footer.grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 14))
        footer.grid_columnconfigure(0, weight=1)

        def validated_values() -> dict[str, Any]:
            values = {
                key: variable.get() for key, variable in variables.items() if key != "password"
            }
            values["smtp_port"] = int(values["smtp_port"])
            values["camera_index"] = int(values["camera_index"])
            values["camera_width"] = max(320, int(values["camera_width"]))
            values["camera_height"] = max(240, int(values["camera_height"]))
            values["countdown_seconds"] = max(1, min(10, int(values["countdown_seconds"])))
            if values["sender_email"] and not EMAIL_RE.match(values["sender_email"].strip()):
                raise ValueError("O e-mail remetente é inválido.")
            if not values["smtp_host"].strip():
                raise ValueError("Informe o servidor SMTP.")
            return values

        def save_settings(close: bool = True) -> bool:
            try:
                old_camera = (
                    int(self.settings["camera_index"]),
                    int(self.settings["camera_width"]),
                    int(self.settings["camera_height"]),
                )
                values = validated_values()
                self.settings.update(values)
                password = (
                    "".join(variables["password"].get().split())
                    if password_unlocked["value"]
                    else ""
                )
                if password:
                    self.store.save_password(str(values["sender_email"]).strip(), password)
                self.store.save(self.settings)
                self.backgrounds = BackgroundRepository(self.settings["background_folder"])
                self.background_index = self.backgrounds.index_of(
                    self.settings.get("selected_background", "")
                )
                new_camera = (
                    int(self.settings["camera_index"]),
                    int(self.settings["camera_width"]),
                    int(self.settings["camera_height"]),
                )
                if new_camera != old_camera:
                    self.camera.stop()
                    self.camera = CameraService(*new_camera)
                    self.camera.start()
                self._apply_fullscreen(bool(self.settings["fullscreen"]))
                self._update_background_name()
                self.set_status("Configurações salvas.", "#8BE6B1")
                settings_saved["value"] = True
                if close:
                    window.destroy()
                return True
            except Exception as exc:
                messagebox.showerror("Configurações", str(exc), parent=window)
                return False

        def test_smtp() -> None:
            try:
                values = validated_values()
                typed_password = (
                    "".join(variables["password"].get().split())
                    if password_unlocked["value"]
                    else ""
                )
                password = typed_password or self.store.get_password(
                    str(values["sender_email"]).strip()
                )
                if not values["sender_email"] or not password:
                    raise ValueError("Informe o e-mail e a senha de aplicativo.")
            except Exception as exc:
                messagebox.showerror("Teste SMTP", str(exc), parent=window)
                return
            self.set_status("Testando a conexão SMTP…")

            def worker() -> None:
                try:
                    with EmailService.connect_and_login(values, password):
                        pass
                    payload = (True, "Conexão SMTP validada com sucesso.")
                except Exception as exc:
                    payload = (False, self._friendly_email_error(exc))
                self.result_queue.put(("smtp_test", payload))

            threading.Thread(target=worker, daemon=True).start()

        def cancel_settings() -> None:
            if not settings_saved["value"]:
                (
                    self.settings["camera_scale"],
                    self.settings["camera_offset_x"],
                    self.settings["camera_offset_y"],
                ) = original_transform
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", cancel_settings)

        ctk.CTkButton(
            footer,
            text="Testar SMTP",
            fg_color=self.PANEL,
            hover_color="#344952",
            command=test_smtp,
        ).grid(row=0, column=1, padx=5)
        ctk.CTkButton(
            footer,
            text="Cancelar",
            fg_color="#55646A",
            hover_color="#677A82",
            command=cancel_settings,
        ).grid(row=0, column=2, padx=5)
        ctk.CTkButton(
            footer,
            text="Salvar",
            fg_color=self.TURQUOISE,
            hover_color=self.TURQUOISE_HOVER,
            command=save_settings,
        ).grid(row=0, column=3, padx=5)

    @staticmethod
    def _verify_admin_password(candidate: str) -> bool:
        candidate_hash = hashlib.pbkdf2_hmac(
            "sha256",
            candidate.encode("utf-8"),
            ADMIN_PASSWORD_SALT,
            ADMIN_PASSWORD_ITERATIONS,
        )
        return hmac.compare_digest(candidate_hash, ADMIN_PASSWORD_HASH)

    def _request_admin_unlock(
        self, parent: ctk.CTkToplevel, on_success: Callable[[], None]
    ) -> None:
        dialog = ctk.CTkToplevel(parent)
        dialog.title("Acesso administrativo")
        dialog.geometry("430x245")
        dialog.resizable(False, False)
        dialog.transient(parent)
        dialog.grab_set()
        dialog.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            dialog,
            text="Desbloquear senha de e-mail",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, padx=24, pady=(24, 6))
        ctk.CTkLabel(
            dialog,
            text="Digite a senha administrativa para visualizar ou editar a credencial.",
            wraplength=360,
            text_color="#B9CBD1",
        ).grid(row=1, column=0, padx=24, pady=(0, 12))

        admin_entry = ctk.CTkEntry(
            dialog,
            placeholder_text="Senha administrativa",
            show="•",
            width=330,
            height=38,
        )
        admin_entry.grid(row=2, column=0, padx=24)
        error_label = ctk.CTkLabel(dialog, text="", text_color="#FF9E95")
        error_label.grid(row=3, column=0, pady=4)

        def close_dialog() -> None:
            dialog.grab_release()
            dialog.destroy()
            if parent.winfo_exists():
                parent.grab_set()

        def validate_admin(_event=None) -> None:
            candidate = admin_entry.get()
            admin_entry.delete(0, "end")
            if self._verify_admin_password(candidate):
                close_dialog()
                on_success()
            else:
                error_label.configure(text="Senha administrativa incorreta.")
                admin_entry.focus_set()

        buttons = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons.grid(row=4, column=0, pady=(2, 16))
        ctk.CTkButton(
            buttons,
            text="Cancelar",
            width=110,
            fg_color="#526269",
            hover_color="#65777F",
            command=close_dialog,
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            buttons,
            text="Desbloquear",
            width=130,
            fg_color=self.TURQUOISE,
            hover_color=self.TURQUOISE_HOVER,
            command=validate_admin,
        ).pack(side="left", padx=5)
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.bind("<Return>", validate_admin)
        dialog.after(120, admin_entry.focus_set)

    def move_camera(self, dx: int, dy: int) -> None:
        self.settings["camera_offset_x"] = int(self.settings["camera_offset_x"]) + dx
        self.settings["camera_offset_y"] = int(self.settings["camera_offset_y"]) + dy

    def adjust_scale(self, delta: float) -> None:
        current = float(self.settings["camera_scale"])
        self.settings["camera_scale"] = round(max(0.35, min(3.0, current + delta)), 2)

    def reset_camera(self) -> None:
        self.settings["camera_scale"] = 1.0
        self.settings["camera_offset_x"] = 0
        self.settings["camera_offset_y"] = 0

    def toggle_fullscreen(self) -> None:
        self._apply_fullscreen(not bool(self.attributes("-fullscreen")))

    def leave_fullscreen(self) -> None:
        if bool(self.attributes("-fullscreen")):
            self._apply_fullscreen(False)

    def _apply_fullscreen(self, enabled: bool) -> None:
        self.attributes("-fullscreen", enabled)

    def on_close(self) -> None:
        self.closing = True
        try:
            self.store.save(self.settings)
            self.camera.stop()
            if pygame is not None and pygame.mixer.get_init():
                pygame.mixer.quit()
        finally:
            self.destroy()


def main() -> None:
    try:
        app = CameraMuseuApp()
        app.mainloop()
    except Exception as exc:
        LOGGER.exception("Falha fatal")
        try:
            messagebox.showerror(APP_NAME, f"O aplicativo não pôde iniciar:\n\n{exc}")
        except Exception:
            print(f"{APP_NAME}: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
