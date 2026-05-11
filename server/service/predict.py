import io
import base64
import torch
import torch.nn.functional as F
import numpy as np
from PIL import Image
from torchvision import transforms

image_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    # transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

video_transform = transforms.Compose([
    transforms.Resize((256, 256)),
    transforms.ToTensor(),
    # transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

MODEL_KEYS = {
    "sd": "sd",
    "mj": "midjourney",
    "bg": "biggan",
}


def predict_image(image_bytes, models_dict, mode="image"):
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

    sd_model = models_dict["sd"]
    mj_model = models_dict["midjourney"]
    bg_model = models_dict["biggan"]

    with torch.no_grad():
        sd_prob = torch.sigmoid(sd_model(input_tensor)).item()
        mj_prob = torch.sigmoid(mj_model(input_tensor)).item()
        bg_prob = torch.sigmoid(bg_model(input_tensor)).item()

    probs = {
        "sd": sd_prob,
        "mj": mj_prob,
        "bg": bg_prob,
    }

    generator_model = max(probs, key=probs.get)
    probability = probs[generator_model]
    if probability >= 0.5:
        label = "AI Generated"
    else:
        label = "Real Image"
        generator_model = "Not an ai"

    # Grad-CAM은 "최종 판정"에 가장 큰 영향을 준 후보 모델의 마지막 convolution feature를 사용한다.
    # Real Image로 판정되어도 max 점수를 낸 모델을 설명 대상으로 유지해,
    # 어떤 AI 생성기 특징이 가장 강하게/약하게 감지됐는지 확인할 수 있게 한다.
    explanation_model_key = max(probs, key=probs.get)
    grad_cam = generate_grad_cam(
        image=image,
        input_tensor=input_tensor,
        model=models_dict[MODEL_KEYS[explanation_model_key]],
        model_key=explanation_model_key,
    )

    return {
        "label": label,
        "probability": round(probability, 4),
        "generator_model": generator_model,
        "probs": {
            "sd": round(sd_prob, 4),
            "mj": round(mj_prob, 4),
            "bg": round(bg_prob, 4),
        },
        "avg_prob": round((sd_prob + mj_prob + bg_prob) / 3, 4),
        "grad_cam": grad_cam,
    }


def generate_grad_cam(image, input_tensor, model, model_key):
    """EfficientNet-B0의 마지막 feature map으로 Grad-CAM heatmap overlay를 만든다."""
    activations = []
    gradients = []
    display_image = resize_for_grad_cam(image)

    # torchvision EfficientNet은 features[-1]이 classifier 직전의 마지막 convolution block이다.
    target_layer = model.features[-1]

    def save_activation(_module, _input, output):
        activations.append(output.detach())

    def save_gradient(_module, _grad_input, grad_output):
        gradients.append(grad_output[0].detach())

    forward_handle = target_layer.register_forward_hook(save_activation)
    backward_handle = target_layer.register_full_backward_hook(save_gradient)

    try:
        model.zero_grad(set_to_none=True)

        # Grad-CAM은 gradient가 필요하므로 torch.no_grad()를 사용하지 않는다.
        output = model(input_tensor)
        score = output.squeeze()
        score.backward()

        if not activations or not gradients:
            return None

        activation = activations[0][0]
        gradient = gradients[0][0]

        # 채널별 gradient 평균을 feature map 가중치로 사용한다.
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
    """모바일/API 응답이 너무 커지지 않도록 설명용 overlay 크기만 제한한다."""
    width, height = image.size
    largest_side = max(width, height)
    if largest_side <= max_side:
        return image

    scale = max_side / largest_side
    resized_size = (int(width * scale), int(height * scale))
    return image.resize(resized_size, Image.Resampling.LANCZOS)


def build_heatmap_overlay(image, heatmap, alpha=0.45):
    """외부 colormap 의존성 없이 빨강-노랑 heatmap을 원본 이미지에 합성한다."""
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
