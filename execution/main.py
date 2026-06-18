import queue
import threading
import time
from pathlib import Path


from config import configure_frozen_runtime


configure_frozen_runtime()


from tkinter import BOTH, BOTTOM, DISABLED, END, LEFT, NORMAL, RIGHT, TOP, Canvas, Entry, Frame, Label, Scrollbar, StringVar, Text, Tk, Toplevel, messagebox
from tkinter import ttk

from PIL import Image, ImageTk

from capture_tasks import capture_image as capture_image_task
from capture_tasks import capture_video as capture_video_task
from config import (
    APP_NAME,
    CAPTURE_DIR,
    DEFAULT_CONFIG,
    apply_window_icon,
    enable_dpi_awareness,
    get_asset_path,
    load_config,
    save_config,
)
from hotkeys import HotkeyThread, parse_hotkey


def clamp_box(box):
    left, top, right, bottom = box
    return (
        min(left, right),
        min(top, bottom),
        max(left, right),
        max(top, bottom),
    )


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
        self.canvas.bind("<Escape>", self.cancel)
        self.window.bind_all("<Escape>", self.cancel)
        self.window.focus_force()
        self.window.grab_set()

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
        try:
            self.window.grab_release()
            self.window.unbind_all("<Escape>")
        except Exception:
            pass
        self.window.destroy()

        if box[2] - box[0] < 12 or box[3] - box[1] < 12:
            return

        self.on_done(box)

    def cancel(self, _event=None):
        try:
            self.window.grab_release()
            self.window.unbind_all("<Escape>")
        except Exception:
            pass
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
        apply_window_icon(self.window)

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
        apply_window_icon(self.root)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

        self.server_var = StringVar(value=self.config["server_url"])
        self.image_hotkey_var = StringVar(value=self.config["image_hotkey"])
        self.video_hotkey_var = StringVar(value=self.config["video_hotkey"])
        self.video_seconds_var = StringVar(value=str(self.config["video_seconds"]))
        self.video_fps_var = StringVar(value=str(self.config["video_fps"]))
        self.status_var = StringVar(value="Ready.")
        self.log_text = None
        self.logo_ref = None

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
        logo_path = get_asset_path("adam-logo-header.png")
        if logo_path:
            logo = Image.open(logo_path)
            logo.thumbnail((220, 74), Image.Resampling.LANCZOS)
            self.logo_ref = ImageTk.PhotoImage(logo)
            Label(header, image=self.logo_ref, bg="#eef7f6").pack(anchor="w", pady=(0, 8))
        else:
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
        ttk.Button(card, text="Exit ADAM Capture", style="Soft.TButton", command=self.exit_app).pack(fill=BOTH, padx=18, pady=(0, 18))

        log_card = Frame(page, bg="white", highlightbackground="#d6e3ea", highlightthickness=1)
        log_card.pack(fill=BOTH, expand=True, pady=(16, 0))
        log_header = Frame(log_card, bg="white")
        log_header.pack(fill=BOTH, padx=18, pady=(14, 8))
        Label(log_header, text="Runtime logs", bg="white", fg="#101828", font=("Segoe UI", 13, "bold")).pack(side=LEFT)
        ttk.Button(log_header, text="Clear", style="Soft.TButton", command=self.clear_logs).pack(side=RIGHT)
        self.log_text = Text(
            log_card,
            height=10,
            state=DISABLED,
            relief="flat",
            bg="#0f172a",
            fg="#dbeafe",
            insertbackground="#dbeafe",
            font=("Consolas", 9),
            wrap="word",
        )
        self.log_text.pack(fill=BOTH, expand=True, padx=18, pady=(0, 18))

        Label(page, textvariable=self.status_var, bg="#eef7f6", fg="#334155", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(12, 0))

    def add_field(self, parent, label, variable):
        wrapper = Frame(parent, bg="white")
        wrapper.pack(fill=BOTH, padx=18, pady=(18, 0))
        Label(wrapper, text=label, bg="white", fg="#344054", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        entry = Entry(wrapper, textvariable=variable, relief="flat", bg="#f8fafc", fg="#101828", font=("Segoe UI", 11), highlightthickness=1, highlightbackground="#dbe4ee", highlightcolor="#22d3ee")
        entry.pack(fill=BOTH, ipady=9, pady=(7, 0))

    def log(self, message):
        self.events.put(("log", message))

    def append_log(self, message):
        if not self.log_text:
            return

        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state=NORMAL)
        self.log_text.insert(END, f"[{timestamp}] {message}\n")
        self.log_text.see(END)
        self.log_text.configure(state=DISABLED)

    def clear_logs(self):
        if not self.log_text:
            return

        self.log_text.configure(state=NORMAL)
        self.log_text.delete("1.0", END)
        self.log_text.configure(state=DISABLED)

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
        self.log("Settings saved and hotkeys re-registered.")

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
                self.append_log(f"ERROR: {payload}")
            elif event == "log":
                self.append_log(payload)
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
        self.root.iconify()
        self.status_var.set("Minimized to taskbar. Hotkeys are still active.")
        self.log("Settings window minimized to taskbar. Use Exit button to quit.")

    def exit_app(self):
        self.log("Exit requested.")
        self.hotkeys.stop()
        self.root.destroy()

    def capture_image(self):
        self.status_var.set("Select image area.")
        self.log("Image capture requested. Waiting for area selection.")
        SelectionOverlay(self.root, self.finish_image_capture)

    def capture_video(self):
        self.status_var.set("Select video area.")
        self.log("Video capture requested. Waiting for area selection.")
        SelectionOverlay(self.root, self.finish_video_capture)

    def finish_image_capture(self, box):
        def worker():
            total_start = time.perf_counter()
            self.log(f"Image area selected: {box[2] - box[0]}x{box[3] - box[1]}.")

            try:
                image_path, result = capture_image_task(
                    box,
                    CAPTURE_DIR,
                    self.config["server_url"],
                )
            except Exception as exc:
                image_path = None
                result = {"error": f"Analysis request failed: {exc}"}
                self.log(f"Image API failed: {exc}")

            self.log(f"Image workflow total: {time.perf_counter() - total_start:.2f}s")
            self.events.put(("image_result", (image_path, result)))

        threading.Thread(target=worker, daemon=True).start()
        self.status_var.set("Analyzing image...")

    def finish_video_capture(self, box):
        def worker():
            total_start = time.perf_counter()
            seconds = int(self.config["video_seconds"])
            fps = int(self.config["video_fps"])
            self.log(f"Video area selected: {box[2] - box[0]}x{box[3] - box[1]}, target={seconds}s @ {fps} FPS.")

            try:
                gif_path, result = capture_video_task(
                    box,
                    CAPTURE_DIR,
                    self.config["server_url"],
                    int(self.config["video_seconds"]),
                    int(self.config["video_fps"]),
                )
            except Exception as exc:
                gif_path = None
                result = {"error": f"Video analysis request failed: {exc}"}

            self.log(f"Video workflow total: {time.perf_counter() - total_start:.2f}s")
            self.events.put(("video_result", (gif_path, result)))

        threading.Thread(target=worker, daemon=True).start()
        self.status_var.set("Recording and analyzing video...")

    def run(self):
        self.root.mainloop()
        self.hotkeys.stop()


if __name__ == "__main__":
    SettingsApp().run()
