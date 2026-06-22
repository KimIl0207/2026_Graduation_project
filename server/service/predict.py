import base64
import io

import cv2
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
        focus = analyze_heatmap_focus(display_image, heatmap)
        buffer = io.BytesIO()
        overlay_image.save(buffer, format="PNG")

        return {
            "model": model_key,
            "image_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
            "note": "Highlighted areas contributed most to the selected AI-generator score.",
            "focus": focus,
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


def analyze_heatmap_focus(image, heatmap):
    heatmap = np.clip(heatmap.astype(np.float32), 0.0, 1.0)
    total_heat = float(heatmap.sum())
    if total_heat <= 1e-6:
        return {
            "stage": "empty",
            "interpretation": "히트맵 반응이 약해 범위를 판단하기 어렵습니다.",
            "distribution": {
                "entropy": 0.0,
                "hot_area_ratio": 0.0,
                "top_10_mass_ratio": 0.0,
                "is_diffuse": False,
            },
            "person_detected": False,
            "region_scores": {},
        }

    distribution = heatmap_distribution(heatmap, total_heat)
    if distribution["is_diffuse"]:
        return {
            "stage": "diffuse",
            "interpretation": "히트맵이 넓게 퍼져 있어 전체 이미지 생성 반응에 가깝습니다.",
            "distribution": distribution,
            "person_detected": False,
            "region_scores": {},
        }

    detections = detect_person_regions(image)
    if not detections["person_detected"]:
        return {
            "stage": "localized",
            "interpretation": "특정 영역 중심 반응입니다. 사람 영역은 감지되지 않았습니다.",
            "distribution": distribution,
            "person_detected": False,
            "region_scores": {
                "localized": 1.0,
            },
        }

    region_scores = heatmap_region_scores(heatmap, detections["masks"], total_heat)
    primary_region = max(region_scores, key=region_scores.get) if region_scores else "unknown"
    return {
        "stage": "person_regions",
        "interpretation": region_interpretation(primary_region),
        "distribution": distribution,
        "person_detected": True,
        "region_scores": region_scores,
        "detections": {
            "face_count": len(detections["faces"]),
            "body_count": len(detections["bodies"]),
        },
    }


def heatmap_distribution(heatmap, total_heat):
    flat = heatmap.reshape(-1)
    probabilities = flat / (total_heat + 1e-8)
    entropy = float(-(probabilities * np.log(probabilities + 1e-8)).sum() / np.log(len(flat)))
    hot_area_ratio = float((heatmap >= 0.5).mean())
    top_count = max(1, int(len(flat) * 0.1))
    top_10_mass_ratio = float(np.partition(flat, -top_count)[-top_count:].sum() / (total_heat + 1e-8))
    is_diffuse = entropy >= 0.86 and hot_area_ratio >= 0.25 and top_10_mass_ratio <= 0.35
    return {
        "entropy": round(entropy, 4),
        "hot_area_ratio": round(hot_area_ratio, 4),
        "top_10_mass_ratio": round(top_10_mass_ratio, 4),
        "is_diffuse": is_diffuse,
    }


def detect_person_regions(image):
    width, height = image.size
    rgb = np.array(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    face_boxes = detect_faces(gray)
    body_boxes = detect_bodies(rgb)

    face_mask = boxes_to_mask(face_boxes, width, height)
    body_mask = boxes_to_mask(body_boxes, width, height)
    body_mask = np.logical_and(body_mask, np.logical_not(face_mask))
    person_mask = np.logical_or(face_mask, body_mask)
    background_mask = np.logical_not(person_mask)

    return {
        "person_detected": bool(face_boxes or body_boxes),
        "faces": face_boxes,
        "bodies": body_boxes,
        "masks": {
            "face": face_mask,
            "body": body_mask,
            "background": background_mask,
        },
    }


def detect_faces(gray):
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)
    if detector.empty():
        return []

    boxes = detector.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(32, 32),
    )
    return [(int(x), int(y), int(w), int(h)) for x, y, w, h in boxes]


def detect_bodies(rgb):
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    boxes, _weights = hog.detectMultiScale(
        cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
        winStride=(8, 8),
        padding=(8, 8),
        scale=1.05,
    )
    return [(int(x), int(y), int(w), int(h)) for x, y, w, h in boxes]


def boxes_to_mask(boxes, width, height):
    mask = np.zeros((height, width), dtype=bool)
    for x, y, w, h in boxes:
        left = max(0, x)
        top = max(0, y)
        right = min(width, x + w)
        bottom = min(height, y + h)
        if right > left and bottom > top:
            mask[top:bottom, left:right] = True
    return mask


def heatmap_region_scores(heatmap, masks, total_heat):
    scores = {}
    assigned_mask = np.zeros_like(heatmap, dtype=bool)
    for key in ("face", "body", "background"):
        mask = masks.get(key)
        if mask is None or not mask.any():
            continue
        scores[key] = round(float(heatmap[mask].sum() / (total_heat + 1e-8)), 4)
        assigned_mask = np.logical_or(assigned_mask, mask)

    other_mask = np.logical_not(assigned_mask)
    if other_mask.any():
        scores["other"] = round(float(heatmap[other_mask].sum() / (total_heat + 1e-8)), 4)

    return scores


def region_interpretation(region):
    messages = {
        "face": "얼굴 영역 중심 반응입니다. 얼굴 보정 또는 합성 가능성을 우선 검토하세요.",
        "body": "몸/인물 영역 중심 반응입니다. 인물 보정 또는 합성 가능성을 우선 검토하세요.",
        "background": "배경 영역 중심 반응입니다. 배경 생성 또는 합성 가능성을 우선 검토하세요.",
        "other": "분류되지 않은 국소 영역 중심 반응입니다. 객체 단위 분석이 필요할 수 있습니다.",
    }
    return messages.get(region, "국소 영역 중심 반응입니다.")
