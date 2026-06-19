import json
import os
import sys
from pathlib import Path


APP_NAME = "ADAM Capture"
APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
CONFIG_PATH = APP_DIR / "settings.json"
CAPTURE_DIR = APP_DIR / "captures"
ASSET_DIR = APP_DIR / "assets"
SOURCE_ASSET_DIR = Path(__file__).resolve().parents[1] / "front" / "public"

DEFAULT_CONFIG = {
    "server_url": "http://localhost:8000",
    "image_hotkey": "Ctrl+Shift+I",
    "video_hotkey": "Ctrl+Shift+V",
    "video_seconds": 5,
    "video_fps": 1,
}


def configure_frozen_runtime():
    if not getattr(sys, "frozen", False):
        return

    runtime_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    sys.path.insert(0, str(runtime_dir))
    os.environ.setdefault("TCL_LIBRARY", str(runtime_dir / "tcl" / "tcl8.6"))
    os.environ.setdefault("TK_LIBRARY", str(runtime_dir / "tcl" / "tk8.6"))


def load_config():
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return DEFAULT_CONFIG.copy()

    config = DEFAULT_CONFIG.copy()
    config.update({k: v for k, v in data.items() if k in config})
    return config


def save_config(config):
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def get_asset_path(name):
    bundled = ASSET_DIR / name
    if bundled.exists():
        return bundled

    source = SOURCE_ASSET_DIR / name
    if source.exists():
        return source

    return None


def apply_window_icon(window):
    ico_path = get_asset_path("favicon.ico")
    png_path = get_asset_path("adam-icon.png")

    try:
        if ico_path:
            window.iconbitmap(str(ico_path))
            return
    except Exception:
        pass

    try:
        if png_path:
            from PIL import Image, ImageTk

            icon = ImageTk.PhotoImage(Image.open(png_path))
            window.iconphoto(True, icon)
            window._adam_icon_ref = icon
    except Exception:
        pass


def enable_dpi_awareness():
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
