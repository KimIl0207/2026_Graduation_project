import os
from pathlib import Path

import torch
import torch.nn as nn
from torchvision import transforms
from transformers import CLIPModel


DEFAULT_CLIP_MODEL_ID = "openai/clip-vit-large-patch14"
DEFAULT_CHECKPOINT_NAME = "univfd_linear.pth"

univfd_transform = transforms.Compose([
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.48145466, 0.4578275, 0.40821073],
        std=[0.26862954, 0.26130258, 0.27577711],
    ),
])


class UnivFDDetector:
    def __init__(self, clip_model, classifier):
        self.clip_model = clip_model
        self.classifier = classifier
        self.clip_model.eval()
        self.classifier.eval()

    @torch.no_grad()
    def predict_prob(self, image):
        pixel_values = univfd_transform(image).unsqueeze(0)
        image_features = self.clip_model.get_image_features(pixel_values=pixel_values)
        if not torch.is_tensor(image_features):
            extracted_features = getattr(image_features, "image_embeds", None)
            if extracted_features is None:
                extracted_features = getattr(image_features, "pooler_output", None)
            image_features = extracted_features
        if image_features is None:
            raise RuntimeError("Could not extract UnivFD CLIP image features.")
        logit = self.classifier(image_features).squeeze()
        return torch.sigmoid(logit).item()


def _state_dict_from_checkpoint(checkpoint):
    if isinstance(checkpoint, dict):
        for key in ("state_dict", "model_state_dict", "classifier", "linear"):
            value = checkpoint.get(key)
            if isinstance(value, dict):
                return value
    return checkpoint


def _normalize_linear_keys(state_dict):
    normalized = {}
    for key, value in state_dict.items():
        short_key = key
        for prefix in ("module.", "classifier.", "linear.", "fc."):
            if short_key.startswith(prefix):
                short_key = short_key[len(prefix):]
        normalized[short_key] = value
    return normalized


def _build_classifier(state_dict):
    state_dict = _normalize_linear_keys(state_dict)
    weight = state_dict.get("weight")
    bias = state_dict.get("bias")
    if weight is None:
        raise ValueError("UnivFD checkpoint needs a linear classifier weight.")

    out_features, in_features = weight.shape
    classifier = nn.Linear(in_features, out_features)
    classifier.load_state_dict({
        "weight": weight,
        "bias": bias if bias is not None else torch.zeros(out_features),
    })
    return classifier


def load_univfd_detector(base_dir):
    checkpoint_path = os.getenv("ADAM_UNIVFD_CHECKPOINT")
    if checkpoint_path:
        checkpoint_path = Path(checkpoint_path)
    else:
        checkpoint_path = Path(base_dir) / "model" / DEFAULT_CHECKPOINT_NAME

    if not checkpoint_path.exists():
        return None

    clip_model_id = os.getenv("ADAM_UNIVFD_CLIP_MODEL", DEFAULT_CLIP_MODEL_ID)
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    state_dict = _state_dict_from_checkpoint(checkpoint)
    classifier = _build_classifier(state_dict)

    clip_model = CLIPModel.from_pretrained(clip_model_id)
    return UnivFDDetector(clip_model, classifier)
