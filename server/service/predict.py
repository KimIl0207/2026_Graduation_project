import base64
import io

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms


image_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
])

video_transform = transforms.Compose([
    transforms.Resize((256, 256)),
    transforms.ToTensor(),
])

MODEL_WEIGHTS = {
    "sdxl": 0.4,
}


def get_model_weight(model_key):
    return MODEL_WEIGHTS.get(model_key, 1.0)


def _as_prob_list(probs):
    if len(probs) == 1 and isinstance(probs[0], (list, tuple)):
        return list(probs[0])
    return list(probs)


def fuse_model_probs(*probs, weights=None):
    """Combine detector outputs into one AI-like suspicious score."""
    if len(probs) == 1 and isinstance(probs[0], dict):
        probs = list(probs[0].values())
    else:
        probs = _as_prob_list(probs)

    weights = weights or [1.0] * len(probs)
    weighted_probs = [prob * weight for prob, weight in zip(probs, weights)]
    weighted_max = max(weighted_probs)
    weighted_avg = sum(weighted_probs) / sum(weights)
    return weighted_max * 0.7 + weighted_avg * 0.3


def model_disagreement(*probs):
    """Measure how far the detector opinions are spread apart."""
    probs = _as_prob_list(probs)
    return max(probs) - min(probs)


def confidence_level(score, disagreement):
    """Estimate confidence from score strength and model agreement."""
    is_clear_score = score >= 0.75 or score <= 0.25
    is_moderate_score = score >= 0.6 or score <= 0.4

    if disagreement <= 0.25 and is_clear_score:
        return "high"
    if disagreement <= 0.5 and is_moderate_score:
        return "medium"
    return "low"


def has_sdxl_spike(probs):
    return probs.get("sdxl", 0.0) >= 0.9


def _label_for_score(score, force_ai=False):
    return "Suspicious AI-like Image" if score >= 0.5 or force_ai else "Likely Real Image"


def _predict_merged(image, input_tensor, models_dict, include_grad_cam):
    model = models_dict["merged"]

    with torch.no_grad():
        merged_prob = torch.sigmoid(model(input_tensor)).item()

    grad_cam = None
    if include_grad_cam:
        grad_cam = generate_grad_cam(
            image=image,
            input_tensor=input_tensor,
            model=model,
            model_key="merged",
        )

    return {
        "label": _label_for_score(merged_prob),
        "suspicious_score": round(merged_prob, 4),
        "confidence": confidence_level(merged_prob, 0.0),
        "model_probs": {
            "sd": round(merged_prob, 4),
            "mj": round(merged_prob, 4),
            "bg": round(merged_prob, 4),
        },
        "signals": {
            "model_fusion": round(merged_prob, 4),
            "model_disagreement": 0.0,
            "sdxl_spike": False,
        },
        "grad_cam": grad_cam,
    }


def _predict_ensemble(image, input_tensor, models_dict, include_grad_cam):
    model_items = {
        model_key: model
        for model_key, model in models_dict.items()
        if model_key != "mode"
    }

    with torch.no_grad():
        probs = {
            model_key: torch.sigmoid(model(input_tensor)).item()
            for model_key, model in model_items.items()
        }

    weights = [get_model_weight(model_key) for model_key in probs.keys()]
    suspicious_score = fuse_model_probs(*probs.values(), weights=weights)
    disagreement = model_disagreement(*probs.values())
    sdxl_spike = has_sdxl_spike(probs)

    grad_cam = None
    if include_grad_cam:
        explanation_model_key = max(probs, key=probs.get)
        grad_cam = generate_grad_cam(
            image=image,
            input_tensor=input_tensor,
            model=model_items[explanation_model_key],
            model_key=explanation_model_key,
        )

    return {
        "label": _label_for_score(suspicious_score, force_ai=sdxl_spike),
        "suspicious_score": round(suspicious_score, 4),
        "confidence": confidence_level(suspicious_score, disagreement),
        "model_probs": {
            model_key: round(prob, 4)
            for model_key, prob in probs.items()
        },
        "signals": {
            "model_fusion": round(suspicious_score, 4),
            "model_disagreement": round(disagreement, 4),
            "sdxl_spike": sdxl_spike,
        },
        "grad_cam": grad_cam,
    }


def predict_image(image_bytes, models_dict, mode="image", include_grad_cam=True):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if image.size[0] < 224 or image.size[1] < 224:
        return {"error": "Image is too small. Minimum size is 224x224 pixels."}

    if mode == "image":
        input_tensor = image_transform(image)
    elif mode == "video":
        input_tensor = video_transform(image)
    else:
        raise ValueError("Invalid mode")

    input_tensor = input_tensor.unsqueeze(0)

    if models_dict.get("mode") == "merged":
        return _predict_merged(image, input_tensor, models_dict, include_grad_cam)

    return _predict_ensemble(image, input_tensor, models_dict, include_grad_cam)


def predict_images(image_bytes_list, models_dict):
    results = []
    for image_bytes in image_bytes_list:
        result = predict_image(image_bytes, models_dict, mode="video", include_grad_cam=False)
        results.append(result["suspicious_score"])
    return sum(results) / len(results) if results else 0.0


def generate_grad_cam(image, input_tensor, model, model_key):
    """Create a Grad-CAM overlay from EfficientNet-B0's final feature block."""
    activations = []
    gradients = []
    display_image = resize_for_grad_cam(image)
    target_layer = model.features[-1]

    def save_activation(_module, _input, output):
        activations.append(output.detach())

    def save_gradient(_module, _grad_input, grad_output):
        gradients.append(grad_output[0].detach())

    forward_handle = target_layer.register_forward_hook(save_activation)
    backward_handle = target_layer.register_full_backward_hook(save_gradient)

    try:
        model.zero_grad(set_to_none=True)

        output = model(input_tensor)
        score = output.squeeze()
        score.backward()

        if not activations or not gradients:
            return None

        activation = activations[0][0]
        gradient = gradients[0][0]

        weights = gradient.mean(dim=(1, 2), keepdim=True)
        cam = torch.sum(weights * activation, dim=0)
        cam = F.relu(cam)

        if torch.max(cam) == 0:
            return None

        cam = cam / torch.max(cam)
        cam = cam.unsqueeze(0).unsqueeze(0)
        cam = F.interpolate(
            cam,
            size=(display_image.height, display_image.width),
            mode="bilinear",
            align_corners=False,
        )
        heatmap = cam.squeeze().cpu().numpy()

        overlay_image = build_heatmap_overlay(display_image, heatmap)
        buffer = io.BytesIO()
        overlay_image.save(buffer, format="PNG")

        return {
            "model": model_key,
            "image_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
            "note": "Highlighted areas contributed most to the selected AI-generator score.",
        }
    finally:
        forward_handle.remove()
        backward_handle.remove()


def resize_for_grad_cam(image, max_side=768):
    width, height = image.size
    largest_side = max(width, height)
    if largest_side <= max_side:
        return image

    scale = max_side / largest_side
    resized_size = (int(width * scale), int(height * scale))
    return image.resize(resized_size, Image.Resampling.LANCZOS)


def build_heatmap_overlay(image, heatmap, alpha=0.45):
    original = np.array(image).astype(np.float32)
    heatmap = np.clip(heatmap, 0.0, 1.0)

    heatmap_rgb = np.zeros_like(original)
    heatmap_rgb[..., 0] = 255.0
    heatmap_rgb[..., 1] = 255.0 * heatmap
    heatmap_rgb[..., 2] = 0.0

    heatmap_strength = heatmap[..., None] * alpha
    overlay = original * (1.0 - heatmap_strength) + heatmap_rgb * heatmap_strength
    overlay = np.clip(overlay, 0, 255).astype(np.uint8)
    return Image.fromarray(overlay)
