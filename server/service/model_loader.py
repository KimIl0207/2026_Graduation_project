import os
import torch
import torch.nn as nn
from torchvision import models


def load_single_model(model_path: str):
    model = models.efficientnet_b0(weights=None)
    model.classifier[1] = nn.Linear(1280, 1)
    model.load_state_dict(torch.load(model_path, map_location="cpu"))
    model.eval()
    return model


def load_models():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mode = os.getenv("ADAM_IMAGE_MODEL_MODE", "merged").strip().lower()

    if mode == "merged":
        merged_model_path = os.path.join(
            base_dir,
            "model",
            "merged",
            "efficientnet_b0_adam_merged_3way.pth",
        )
        return {
            "mode": "merged",
            "merged": load_single_model(merged_model_path),
        }

    sd_model_path = os.path.join(base_dir, "model", "best_efficientnet_b0_Diffusion.pth")
    midjourney_model_path = os.path.join(base_dir, "model", "best_efficientnet_b0_Midjourney.pth")
    biggan_model_path = os.path.join(base_dir, "model", "best_efficientnet_b0_BigGAN.pth")

    models_dict = {
        "mode": "ensemble",
        "sd": load_single_model(sd_model_path),
        "midjourney": load_single_model(midjourney_model_path),
        "biggan": load_single_model(biggan_model_path),
    }

    return models_dict
