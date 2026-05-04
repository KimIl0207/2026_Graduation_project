import io
import torch
from PIL import Image
from torchvision import transforms

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
])

def predict_image(image_bytes, models_dict):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    input_tensor = transform(image).unsqueeze(0)

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
