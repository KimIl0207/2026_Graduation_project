import ctypes
import threading
from ctypes import wintypes
from dataclasses import dataclass


WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
HOTKEY_IMAGE_ID = 101
HOTKEY_VIDEO_ID = 102


@dataclass
class Hotkey:
    modifiers: int
    vk: int


def parse_hotkey(value):
    parts = [part.strip().upper() for part in value.split("+") if part.strip()]
    if not parts:
        raise ValueError("Hotkey is empty.")

    modifiers = 0
    key = None

    for part in parts:
        if part in {"CTRL", "CONTROL"}:
            modifiers |= MOD_CONTROL
        elif part == "ALT":
            modifiers |= MOD_ALT
        elif part == "SHIFT":
            modifiers |= MOD_SHIFT
        elif part in {"WIN", "WINDOWS"}:
            modifiers |= MOD_WIN
        else:
            key = part

    if not key:
        raise ValueError("Hotkey needs a key, for example Ctrl+Shift+I.")

    if len(key) == 1:
        vk = ord(key)
    elif key.startswith("F") and key[1:].isdigit():
        num = int(key[1:])
        if not 1 <= num <= 24:
            raise ValueError("Function key must be F1 through F24.")
        vk = 0x70 + num - 1
    else:
        raise ValueError("Use a letter, number, or F1-F24 as the final key.")

    return Hotkey(modifiers, vk)


class HotkeyThread(threading.Thread):
    def __init__(self, event_queue, config):
        super().__init__(daemon=True)
        self.event_queue = event_queue
        self.config = config
        self.stop_event = threading.Event()
        self.user32 = ctypes.windll.user32
        self.thread_id = None

    def update_config(self, config):
        self.config = config
        if self.thread_id:
            self.user32.PostThreadMessageW(self.thread_id, 0x0400, 0, 0)

    def stop(self):
        self.stop_event.set()
        if self.thread_id:
            self.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)

    def register_hotkeys(self):
        self.user32.UnregisterHotKey(None, HOTKEY_IMAGE_ID)
        self.user32.UnregisterHotKey(None, HOTKEY_VIDEO_ID)

        image_hotkey = parse_hotkey(self.config["image_hotkey"])
        video_hotkey = parse_hotkey(self.config["video_hotkey"])

        ok_image = self.user32.RegisterHotKey(
            None, HOTKEY_IMAGE_ID, image_hotkey.modifiers, image_hotkey.vk
        )
        ok_video = self.user32.RegisterHotKey(
            None, HOTKEY_VIDEO_ID, video_hotkey.modifiers, video_hotkey.vk
        )

        if not ok_image or not ok_video:
            raise RuntimeError("Could not register one or more hotkeys.")

    def run(self):
        self.thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        try:
            self.register_hotkeys()
            self.event_queue.put(("status", "Hotkeys active."))
        except Exception as exc:
            self.event_queue.put(("error", str(exc)))

        msg = wintypes.MSG()
        while not self.stop_event.is_set():
            result = self.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result == 0:
                break

            if msg.message == WM_HOTKEY:
                if msg.wParam == HOTKEY_IMAGE_ID:
                    self.event_queue.put(("capture_image", None))
                elif msg.wParam == HOTKEY_VIDEO_ID:
                    self.event_queue.put(("capture_video", None))
            elif msg.message == 0x0400:
                try:
                    self.register_hotkeys()
                    self.event_queue.put(("status", "Hotkeys updated."))
                except Exception as exc:
                    self.event_queue.put(("error", str(exc)))

        self.user32.UnregisterHotKey(None, HOTKEY_IMAGE_ID)
        self.user32.UnregisterHotKey(None, HOTKEY_VIDEO_ID)
