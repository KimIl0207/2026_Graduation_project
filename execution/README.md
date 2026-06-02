# ADAM Capture

Windows background capture helper for the ADAM detector.

## Run

To install, run:

```powershell
installer\ADAMCaptureSetup.exe
```

The installer copies the app to `%LOCALAPPDATA%\ADAMCapture` and creates Desktop and Start Menu shortcuts.

Double-click `adam_capture.pyw` for no console window.

You can also double-click `run_adam_capture.bat`, or run:

```powershell
python main.py
```

## Defaults

- Image capture hotkey: `Ctrl+Shift+I`
- Video capture hotkey: `Ctrl+Shift+V`
- Server URL: `http://localhost:8000`
- Video capture: 5 seconds at 4 FPS

## Notes

- Drag an area after pressing a hotkey.
- Image capture calls `/predict`.
- Video capture records a GIF preview, analyzes sampled frames with `/predict-frame`, and averages the score.
- Captures are saved under `execution/captures`.
- Settings are saved in `execution/settings.json`.
