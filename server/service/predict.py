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


FUSION_MODEL_THRESHOLDS = {
    "mj": 0.972,
    "sd3": 0.85,
    "mj6": 0.90,
}


def calibrate_model_prob(model_key, prob):
    threshold = FUSION_MODEL_THRESHOLDS.get(model_key)
    if threshold is None:
        return None

    if prob < threshold:
        return 0.5 * (prob / threshold)

    if threshold >= 1.0:
        return 1.0

    return 0.5 + 0.5 * ((prob - threshold) / (1.0 - threshold))


def calibrate_model_probs(probs):
    return {
        model_key: calibrated_prob
        for model_key, prob in probs.items()
        if (calibrated_prob := calibrate_model_prob(model_key, prob)) is not None
    }


def fuse_model_probs(probs):
    """Use max over calibrated specialist detectors."""
    calibrated_probs = calibrate_model_probs(probs)
    if not calibrated_probs:
        return 0.0

    return max(calibrated_probs.values())


def confidence_level():
    return "ADAM 판단"


def _label_for_score(score, force_ai=False):
    return "Suspicious AI-like Image" if score >= 0.5 or force_ai else "Likely Real Image"


def _predict_model_prob(model, image, input_tensor):
    if hasattr(model, "predict_prob"):
        return model.predict_prob(image)
    return torch.sigmoid(model(input_tensor)).item()


def _grad_cam_model_items(model_items):
    return {
        model_key: model
        for model_key, model in model_items.items()
        if hasattr(model, "features")
    }


def _predict_ensemble(image, input_tensor, models_dict, include_grad_cam):
    model_items = {
        model_key: model
        for model_key, model in models_dict.items()
        if model_key != "mode"
    }

    with torch.no_grad():
        probs = {
            model_key: _predict_model_prob(model, image, input_tensor)
            for model_key, model in model_items.items()
        }

    fusion_model_scores = calibrate_model_probs(probs)
    suspicious_score = fuse_model_probs(probs)

    grad_cam = None
    if include_grad_cam:
        cam_models = _grad_cam_model_items(model_items)
        cam_probs = {
            model_key: prob
            for model_key, prob in probs.items()
            if model_key in cam_models
        }
        if cam_probs:
            explanation_model_key = max(cam_probs, key=cam_probs.get)
            grad_cam = generate_grad_cam(
                image=image,
                input_tensor=input_tensor,
                model=cam_models[explanation_model_key],
                model_key=explanation_model_key,
            )

    return {
        "label": _label_for_score(suspicious_score),
        "suspicious_score": round(suspicious_score, 4),
        "confidence": confidence_level(),
        "model_probs": {
            model_key: round(prob, 4)
            for model_key, prob in probs.items()
        },
        "signals": {
            "model_fusion": round(suspicious_score, 4),
            "fusion_model_scores": {
                model_key: round(prob, 4)
                for model_key, prob in fusion_model_scores.items()
            },
            "active_fusion_models": sorted(FUSION_MODEL_THRESHOLDS),
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

    return _predict_ensemble(image, input_tensor, models_dict, include_grad_cam)


def predict_images(image_bytes_list, models_dict):
    results = predict_image_scores(image_bytes_list, models_dict)
    return robust_frame_score(results)


def robust_frame_score(scores):
    """Average frame scores after damping one-off high/low outliers."""
    if not scores:
        return 0.0
    if len(scores) < 3:
        return sum(scores) / len(scores)

    ordered = sorted(scores)
    damped_scores = [ordered[1], *ordered[1:-1], ordered[-2]]
    return sum(damped_scores) / len(damped_scores)


def predict_image_scores(image_bytes_list, models_dict):
    results = []
    for image_bytes in image_bytes_list:
        result = predict_image(image_bytes, models_dict, mode="video", include_grad_cam=False)
        if "suspicious_score" in result:
            results.append(result["suspicious_score"])
    return results


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
