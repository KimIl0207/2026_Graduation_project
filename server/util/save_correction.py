import shutil
from datetime import datetime
from pathlib import Path


CORRECTION_SAVE_DIR = Path(__file__).resolve().parents[1] / "corrections"
REAL_DIR = CORRECTION_SAVE_DIR / "real"
FAKE_DIR = CORRECTION_SAVE_DIR / "fake"


def save_correction_file(file, correct_label):
    if correct_label not in ["real", "fake"]:
        return {"success": False, "message": "correct_label must be 'real' or 'fake'"}

    save_dir = REAL_DIR if correct_label == "real" else FAKE_DIR
    save_dir.mkdir(parents=True, exist_ok=True)

    original_name = file.filename or "uploaded_image"
    original_path = Path(original_name)
    base_name = original_path.stem or "uploaded_image"
    ext = original_path.suffix or ".jpg"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    save_name = f"{base_name}_{timestamp}{ext}"
    save_path = save_dir / save_name

    with save_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "success": True,
        "message": f"Saved to {correct_label} folder",
        "saved_path": str(save_path)
    }
