import base64
import ctypes
import io
import json
import os
import queue
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path


if getattr(sys, "frozen", False):
    runtime_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    sys.path.insert(0, str(runtime_dir))
    os.environ.setdefault("TCL_LIBRARY", str(runtime_dir / "tcl" / "tcl8.6"))
    os.environ.setdefault("TK_LIBRARY", str(runtime_dir / "tcl" / "tk8.6"))


from tkinter import BOTH, BOTTOM, DISABLED, END, LEFT, NORMAL, RIGHT, TOP, Canvas, Entry, Frame, Label, Scrollbar, StringVar, Tk, Toplevel, messagebox
from tkinter import ttk

from PIL import Image, ImageGrab, ImageTk


APP_NAME = "ADAM Capture"
APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
CONFIG_PATH = APP_DIR / "settings.json"
CAPTURE_DIR = APP_DIR / "captures"

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
HOTKEY_IMAGE_ID = 101
HOTKEY_VIDEO_ID = 102

DEFAULT_CONFIG = {
    "server_url": "http://localhost:8000",
    "image_hotkey": "Ctrl+Shift+I",
    "video_hotkey": "Ctrl+Shift+V",
    "video_seconds": 5,
    "video_fps": 4,
}


def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


@dataclass
class Hotkey:
    modifiers: int
    vk: int


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


def build_multipart(field_name, file_path, mime_type):
    boundary = f"----ADAMBoundary{int(time.time() * 1000)}"
    file_name = Path(file_path).name
    body = io.BytesIO()
    body.write(f"--{boundary}\r\n".encode())
    body.write(
        f'Content-Disposition: form-data; name="{field_name}"; filename="{file_name}"\r\n'.encode()
    )
    body.write(f"Content-Type: {mime_type}\r\n\r\n".encode())
    body.write(Path(file_path).read_bytes())
    body.write(f"\r\n--{boundary}--\r\n".encode())
    return body.getvalue(), f"multipart/form-data; boundary={boundary}"


def post_image(server_url, endpoint, file_path):
    body, content_type = build_multipart("file", file_path, "image/png")
    request = urllib.request.Request(
        f"{server_url.rstrip('/')}{endpoint}",
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def clamp_box(box):
    left, top, right, bottom = box
    return (
        min(left, right),
        min(top, bottom),
        max(left, right),
        max(top, bottom),
    )


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


class SelectionOverlay:
    def __init__(self, root, on_done):
        self.root = root
        self.on_done = on_done
        self.start_x = 0
        self.start_y = 0
        self.rect_id = None

        self.window = Toplevel(root)
        self.window.attributes("-fullscreen", True)
        self.window.attributes("-alpha", 0.28)
        self.window.attributes("-topmost", True)
        self.window.configure(bg="#0f172a")
        self.window.overrideredirect(True)

        self.canvas = Canvas(self.window, cursor="crosshair", bg="#0f172a", highlightthickness=0)
        self.canvas.pack(fill=BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.window.bind("<Escape>", self.cancel)

        self.hint = self.canvas.create_text(
            self.window.winfo_screenwidth() // 2,
            48,
            text="Drag to select capture area. Press Esc to cancel.",
            fill="white",
            font=("Segoe UI", 16, "bold"),
        )

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="#22d3ee", width=3
        )

    def on_drag(self, event):
        if self.rect_id:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        box = clamp_box((self.start_x, self.start_y, event.x, event.y))
        self.window.destroy()

        if box[2] - box[0] < 12 or box[3] - box[1] < 12:
            return

        self.on_done(box)

    def cancel(self, _event=None):
        self.window.destroy()


class ResultWindow:
    def __init__(self, root, title, image_path, result):
        self.image_path = Path(image_path) if image_path else None
        self.preview_ref = None
        self.preview_canvas = None

        self.window = Toplevel(root)
        self.window.title(title)
        self.window.geometry("760x520")
        self.window.minsize(560, 420)
        self.window.configure(bg="#eef7f6")

        shell = Frame(self.window, bg="#eef7f6")
        shell.pack(fill=BOTH, expand=True, padx=18, pady=18)

        card = Frame(shell, bg="white", highlightbackground="#d6e3ea", highlightthickness=1)
        card.pack(fill=BOTH, expand=True)

        left = Frame(card, bg="white")
        left.pack(side=LEFT, fill=BOTH, expand=True, padx=18, pady=18)

        right = Frame(card, bg="white")
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=18, pady=18)

        Label(left, text="Capture", bg="white", fg="#101828", font=("Segoe UI", 16, "bold")).pack(anchor="w")

        self.preview_frame = Frame(left, bg="white")
        self.preview_frame.pack(fill=BOTH, expand=True, pady=18)
        self.preview_canvas = Canvas(self.preview_frame, bg="white", highlightthickness=0)
        self.preview_canvas.pack(fill=BOTH, expand=True)
        self.preview_frame.bind("<Configure>", self.render_preview)
        self.render_preview()

        Label(right, text="Analysis Result", bg="white", fg="#101828", font=("Segoe UI", 18, "bold")).pack(anchor="w")

        if result.get("error"):
            Label(
                right,
                text=f"Error: {result['error']}",
                bg="#fff1f0",
                fg="#b42318",
                font=("Segoe UI", 11, "bold"),
                wraplength=320,
                justify=LEFT,
                padx=14,
                pady=12,
            ).pack(fill=BOTH, pady=16)
            return

        score = result.get("suspicious_score")
        if score is not None and score <= 1:
            score_text = f"{round(score * 100)}%"
        elif score is not None:
            score_text = f"{round(score)}%"
        else:
            score_text = "-"

        Label(right, text=result.get("label", "Result ready"), bg="white", fg="#1d4ed8", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(18, 8))
        Label(right, text=score_text, bg="white", fg="#101828", font=("Segoe UI", 46, "bold")).pack(anchor="w")

        details = [
            ("Confidence", result.get("confidence")),
            ("Frames", result.get("frame_count")),
            ("Frame scores", ", ".join(map(str, result.get("frame_predictions", []))) if result.get("frame_predictions") else None),
        ]

        info = Frame(right, bg="#f8fafc", highlightbackground="#dbe4ee", highlightthickness=1)
        info.pack(fill=BOTH, pady=18)
        for name, value in details:
            if value is None:
                continue
            Label(info, text=f"{name}: {value}", bg="#f8fafc", fg="#334155", font=("Segoe UI", 10, "bold"), anchor="w").pack(fill=BOTH, padx=12, pady=7)

    def render_preview(self, _event=None):
        if not self.image_path or not self.image_path.exists() or not self.preview_canvas:
            return

        width = max(self.preview_frame.winfo_width() - 12, 220)
        height = max(self.preview_frame.winfo_height() - 12, 180)

        image = Image.open(self.image_path)
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        self.preview_ref = ImageTk.PhotoImage(image)
        self.window.preview_ref = self.preview_ref
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(
            max(width // 2, 1),
            max(height // 2, 1),
            image=self.preview_ref,
            anchor="center",
        )


class SettingsApp:
    def __init__(self):
        enable_dpi_awareness()
        CAPTURE_DIR.mkdir(exist_ok=True)
        self.config = load_config()
        self.events = queue.Queue()
        self.root = Tk()
        self.root.title(APP_NAME)
        self.root.geometry("520x560")
        self.root.configure(bg="#eef7f6")
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

        self.server_var = StringVar(value=self.config["server_url"])
        self.image_hotkey_var = StringVar(value=self.config["image_hotkey"])
        self.video_hotkey_var = StringVar(value=self.config["video_hotkey"])
        self.video_seconds_var = StringVar(value=str(self.config["video_seconds"]))
        self.video_fps_var = StringVar(value=str(self.config["video_fps"]))
        self.status_var = StringVar(value="Ready.")

        self.build_ui()
        self.hotkeys = HotkeyThread(self.events, self.config)
        self.hotkeys.start()
        self.root.after(120, self.process_events)

    def build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Accent.TButton", background="#2563eb", foreground="white", padding=10, font=("Segoe UI", 10, "bold"))
        style.configure("Soft.TButton", background="#e0f2fe", foreground="#0f172a", padding=10, font=("Segoe UI", 10, "bold"))

        shell = Frame(self.root, bg="#eef7f6")
        shell.pack(fill=BOTH, expand=True)

        canvas = Canvas(shell, bg="#eef7f6", highlightthickness=0)
        scrollbar = Scrollbar(shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill="y")
        canvas.pack(side=LEFT, fill=BOTH, expand=True)

        content = Frame(canvas, bg="#eef7f6")
        content_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def update_content_width(event):
            canvas.itemconfigure(content_id, width=event.width)

        def scroll_with_wheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        content.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_content_width)
        canvas.bind_all("<MouseWheel>", scroll_with_wheel)

        page = Frame(content, bg="#eef7f6")
        page.pack(fill=BOTH, expand=True, padx=20, pady=20)

        header = Frame(page, bg="#eef7f6")
        header.pack(fill=BOTH)
        Label(header, text="ADAM Capture", bg="#eef7f6", fg="#101828", font=("Segoe UI", 24, "bold")).pack(anchor="w")
        Label(header, text="Background capture assistant for image and video detection.", bg="#eef7f6", fg="#607086", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4, 18))

        card = Frame(page, bg="white", highlightbackground="#d6e3ea", highlightthickness=1)
        card.pack(fill=BOTH, expand=True)

        self.add_field(card, "Server URL", self.server_var)
        self.add_field(card, "Image capture hotkey", self.image_hotkey_var)
        self.add_field(card, "Video capture hotkey", self.video_hotkey_var)
        self.add_field(card, "Video seconds", self.video_seconds_var)
        self.add_field(card, "Video FPS", self.video_fps_var)

        buttons = Frame(card, bg="white")
        buttons.pack(fill=BOTH, padx=18, pady=18)
        ttk.Button(buttons, text="Save settings", style="Accent.TButton", command=self.save_settings).pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 8))
        ttk.Button(buttons, text="Capture image now", style="Soft.TButton", command=self.capture_image).pack(side=LEFT, fill=BOTH, expand=True, padx=(8, 0))

        ttk.Button(card, text="Capture video now", style="Soft.TButton", command=self.capture_video).pack(fill=BOTH, padx=18, pady=(0, 18))

        Label(page, textvariable=self.status_var, bg="#eef7f6", fg="#334155", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(12, 0))

    def add_field(self, parent, label, variable):
        wrapper = Frame(parent, bg="white")
        wrapper.pack(fill=BOTH, padx=18, pady=(18, 0))
        Label(wrapper, text=label, bg="white", fg="#344054", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        entry = Entry(wrapper, textvariable=variable, relief="flat", bg="#f8fafc", fg="#101828", font=("Segoe UI", 11), highlightthickness=1, highlightbackground="#dbe4ee", highlightcolor="#22d3ee")
        entry.pack(fill=BOTH, ipady=9, pady=(7, 0))

    def save_settings(self):
        try:
            parse_hotkey(self.image_hotkey_var.get())
            parse_hotkey(self.video_hotkey_var.get())
            seconds = max(1, min(30, int(self.video_seconds_var.get())))
            fps = max(1, min(12, int(self.video_fps_var.get())))
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return

        self.config = {
            "server_url": self.server_var.get().strip() or DEFAULT_CONFIG["server_url"],
            "image_hotkey": self.image_hotkey_var.get().strip(),
            "video_hotkey": self.video_hotkey_var.get().strip(),
            "video_seconds": seconds,
            "video_fps": fps,
        }
        save_config(self.config)
        self.hotkeys.update_config(self.config)
        self.status_var.set("Settings saved.")

    def process_events(self):
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event == "capture_image":
                self.capture_image()
            elif event == "capture_video":
                self.capture_video()
            elif event == "status":
                self.status_var.set(payload)
            elif event == "error":
                self.status_var.set(payload)
            elif event == "image_result":
                image_path, result = payload
                ResultWindow(self.root, "Image result", image_path, result)
                self.status_var.set("Image analysis complete.")
            elif event == "video_result":
                image_path, result = payload
                ResultWindow(self.root, "Video result", image_path, result)
                self.status_var.set("Video analysis complete.")

        self.root.after(120, self.process_events)

    def hide_window(self):
        self.root.withdraw()
        self.status_var.set("Running in background. Re-run app to show settings.")

    def capture_image(self):
        self.status_var.set("Select image area.")
        SelectionOverlay(self.root, self.finish_image_capture)

    def capture_video(self):
        self.status_var.set("Select video area.")
        SelectionOverlay(self.root, self.finish_video_capture)

    def finish_image_capture(self, box):
        def worker():
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            image_path = CAPTURE_DIR / f"capture_{timestamp}.png"
            ImageGrab.grab(bbox=box).save(image_path)

            try:
                result = post_image(self.config["server_url"], "/predict", image_path)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                result = {"error": f"Analysis request failed: {exc}"}

            self.events.put(("image_result", (image_path, result)))

        threading.Thread(target=worker, daemon=True).start()
        self.status_var.set("Analyzing image...")

    def finish_video_capture(self, box):
        def worker():
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            seconds = int(self.config["video_seconds"])
            fps = int(self.config["video_fps"])
            delay = 1 / fps
            frames = []
            frame_paths = []
            end_time = time.time() + seconds
            index = 0

            while time.time() < end_time:
                frame = ImageGrab.grab(bbox=box).convert("RGB")
                frames.append(frame)
                frame_path = CAPTURE_DIR / f"video_{timestamp}_{index:03d}.png"
                frame.save(frame_path)
                frame_paths.append(frame_path)
                index += 1
                time.sleep(delay)

            gif_path = CAPTURE_DIR / f"video_{timestamp}.gif"
            if frames:
                frames[0].save(
                    gif_path,
                    save_all=True,
                    append_images=frames[1:],
                    duration=int(delay * 1000),
                    loop=0,
                )

            scores = []
            for frame_path in frame_paths:
                try:
                    frame_result = post_image(self.config["server_url"], "/predict-frame", frame_path)
                except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                    continue

                if "suspicious_score" in frame_result:
                    scores.append(float(frame_result["suspicious_score"]))

            if scores:
                avg = sum(scores) / len(scores)
                result = {
                    "label": "Suspicious AI-like Video" if avg >= 0.5 else "Likely Real Video",
                    "suspicious_score": round(avg, 4),
                    "frame_count": len(scores),
                    "frame_predictions": [round(score, 4) for score in scores],
                }
            else:
                result = {"error": "No video frames could be analyzed."}

            self.events.put(("video_result", (gif_path, result)))

        threading.Thread(target=worker, daemon=True).start()
        self.status_var.set("Recording and analyzing video...")

    def run(self):
        self.root.mainloop()
        self.hotkeys.stop()


if __name__ == "__main__":
    SettingsApp().run()
