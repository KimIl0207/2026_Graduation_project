import io
import torch
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

def predict_image(image_bytes, models_dict, mode="image"):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
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

    return {
        "label": label,
        "probability": round(probability, 4),
        "generator_model": generator_model,
        "probs": {
            "sd": round(sd_prob, 4),
            "mj": round(mj_prob, 4),
            "bg": round(bg_prob, 4),
        },
        "avg_prob": round((sd_prob + mj_prob + bg_prob) / 3, 4)
    }
