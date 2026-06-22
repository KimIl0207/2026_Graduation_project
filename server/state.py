from service.ai_text_detector_engine import AITextDetector
from service.model_loader import load_models


models_dict = load_models()
text_detector = None


def get_text_detector():
    global text_detector

    if text_detector is None:
        text_detector = AITextDetector()

    return text_detector
