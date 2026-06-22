import json
from datetime import datetime, timezone
from pathlib import Path
import uuid


LOG_PATH = Path(__file__).resolve().parents[1] / "corrections" / "logs.jsonl"


def save_log(data):
    log_entry = {
        "id": str(uuid.uuid4()),
        "filepath": data.get("filepath"),
        "correct_label": data.get("correct_label"),
        "predicted_label": data.get("predicted_label"),
        "predicted_probability": data.get("predicted_probability"),
        "selected_generator_model": data.get("selected_generator_model"),
        "sd_prob": data.get("sd_prob"),
        "mj_prob": data.get("mj_prob"),
        "mj6_prob": data.get("mj6_prob"),
        "bg_prob": data.get("bg_prob"),
        "sd3_prob": data.get("sd3_prob"),
        "dalle3_prob": data.get("dalle3_prob"),
        "univfd_prob": data.get("univfd_prob"),
        "source": data.get("source", "unknown"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
