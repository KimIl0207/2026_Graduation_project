import os
import torch
import torch.nn as nn
from torchvision import models

from service.univfd import load_univfd_detector


def load_single_model(model_path: str):
    model = models.efficientnet_b0(weights=None)
    model.classifier[1] = nn.Linear(1280, 1)
    model.load_state_dict(torch.load(model_path, map_location="cpu"))
    model.eval()
    return model


def load_models():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    sd_model_path = os.path.join(base_dir, "model", "best_efficientnet_b0_Diffusion.pth")
    midjourney_model_path = os.path.join(base_dir, "model", "best_efficientnet_b0_Midjourney_6.pth")
    biggan_model_path = os.path.join(base_dir, "model", "best_efficientnet_b0_BigGAN.pth")
    sd3_model_path = os.path.join(base_dir, "model", "best_efficientnet_b0_SD3_finetuned.pth")
    dalle3_model_path = os.path.join(base_dir, "model", "best_efficientnet_b0_DALL_E_3_finetuned.pth")

    models_dict = {
        "mode": "ensemble",
        "sd": load_single_model(sd_model_path),
        "mj": load_single_model(midjourney_model_path),
        "bg": load_single_model(biggan_model_path),
        "sd3": load_single_model(sd3_model_path),
        "dalle3": load_single_model(dalle3_model_path),
    }

    univfd_detector = load_univfd_detector(base_dir)
    if univfd_detector is not None:
        models_dict["univfd"] = univfd_detector

    return models_dict
