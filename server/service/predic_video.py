import cv2
import os
import tempfile
from pathlib import Path

from util.frame_extract import extract_random_frames
from service.predict import predict_image

async def predict_video(file, models_dict):
    suffix = Path(file.filename or "").suffix or ".mp4"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            temp_file.write(await file.read())

        frames = extract_random_frames(temp_path, color_format="bgr", samples_per_second=(1,2), max_duration_seconds=5)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

    if not frames:
        return {"error": "No frames extracted from the video."}
    
    predictions = []
    for frame in frames:
        success, buffer = cv2.imencode('.jpg', frame)
        if not success:
            continue

        image_bytes = buffer.tobytes()
        result = predict_image(image_bytes, models_dict, mode="video", include_grad_cam=False)
        predictions.append(max(result["probs"].values()))

    if not predictions:
        return {"error": "No readable frames found in the video."}
    
    average_probability = sum(predictions) / len(predictions)
    final_prediction = "AI Generated Video" if average_probability >= 0.5 else "Real Video"
    return {
        "label": final_prediction,
        "probability": round(average_probability, 4),
        "frame_count": len(predictions),
        "frame_predictions": predictions,
    }
