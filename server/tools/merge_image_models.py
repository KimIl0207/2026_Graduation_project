from pathlib import Path

import torch
import torch.nn as nn
from torchvision import models


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "model"
OUTPUT_DIR = MODEL_DIR / "merged"
SOURCE_MODELS = [
    MODEL_DIR / "best_efficientnet_b0_Diffusion.pth",
    MODEL_DIR / "best_efficientnet_b0_Midjourney.pth",
    MODEL_DIR / "best_efficientnet_b0_BigGAN.pth",
]


def build_model():
    model = models.efficientnet_b0(weights=None)
    model.classifier[1] = nn.Linear(1280, 1)
    return model


def load_state_dict(path):
    checkpoint = torch.load(path, map_location="cpu")
    if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
        return checkpoint["state_dict"]
    if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
        return checkpoint["model_state_dict"]
    return checkpoint


def merge_state_dicts(state_dicts):
    base_keys = list(state_dicts[0].keys())
    for index, state_dict in enumerate(state_dicts[1:], start=2):
        if list(state_dict.keys()) != base_keys:
            raise ValueError(f"State dict key mismatch at model #{index}")

    merged = {}
    for key in base_keys:
        values = [state_dict[key] for state_dict in state_dicts]
        shapes = {tuple(value.shape) for value in values}
        if len(shapes) != 1:
            raise ValueError(f"Shape mismatch at key {key}: {shapes}")

        if torch.is_floating_point(values[0]):
            merged[key] = torch.stack([value.float() for value in values], dim=0).mean(dim=0)
        else:
            merged[key] = values[0].clone()

    return merged


def export_onnx(model, output_path):
    dummy = torch.randn(1, 3, 224, 224)
    torch.onnx.export(
        model,
        dummy,
        output_path,
        input_names=["input"],
        output_names=["logit"],
        dynamic_axes={
            "input": {0: "batch"},
            "logit": {0: "batch"},
        },
        opset_version=17,
        dynamo=False,
    )


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Merging models:")
    for path in SOURCE_MODELS:
        print(f"  - {path.name}")

    state_dicts = [load_state_dict(path) for path in SOURCE_MODELS]
    merged_state_dict = merge_state_dicts(state_dicts)

    pth_path = OUTPUT_DIR / "efficientnet_b0_adam_merged_3way.pth"
    torch.save(merged_state_dict, pth_path)
    print(f"Saved PTH: {pth_path}")

    model = build_model()
    missing, unexpected = model.load_state_dict(merged_state_dict, strict=True)
    if missing or unexpected:
        raise RuntimeError(f"Load mismatch: missing={missing}, unexpected={unexpected}")
    model.eval()

    scripted_path = OUTPUT_DIR / "efficientnet_b0_adam_merged_3way.torchscript.pt"
    scripted = torch.jit.script(model)
    scripted.save(str(scripted_path))
    print(f"Saved TorchScript: {scripted_path}")

    try:
        onnx_path = OUTPUT_DIR / "efficientnet_b0_adam_merged_3way.onnx"
        export_onnx(model, onnx_path)
        print(f"Saved ONNX: {onnx_path}")
    except Exception as exc:
        print(f"ONNX export skipped: {exc}")

    dummy = torch.randn(1, 3, 224, 224)
    with torch.no_grad():
        logit = model(dummy)
        prob = torch.sigmoid(logit).item()
    print(f"Smoke test prob: {prob:.4f}")


if __name__ == "__main__":
    main()
