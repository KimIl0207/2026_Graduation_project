# ADAM 3-way merged image model

This directory contains a weight-averaged EfficientNet-B0 detector made from:

- `best_efficientnet_b0_Diffusion.pth`
- `best_efficientnet_b0_Midjourney.pth`
- `best_efficientnet_b0_BigGAN.pth`

`best_efficientnet_b0_v2.pth` is intentionally excluded.

## Outputs

- `efficientnet_b0_adam_merged_3way.pth`
  - PyTorch `state_dict`
  - Same architecture as current server image models:
    `torchvision.models.efficientnet_b0(weights=None)` with `classifier[1] = nn.Linear(1280, 1)`
- `efficientnet_b0_adam_merged_3way.torchscript.pt`
  - TorchScript export for Python/native runtime use
- `efficientnet_b0_adam_merged_3way.onnx`
  - ONNX export
  - Input: `input`, shape `[batch, 3, 224, 224]`
  - Output: `logit`, shape `[batch, 1]`
  - Apply sigmoid to get AI probability

## Rebuild

```powershell
python server\tools\merge_image_models.py
```

The ONNX export requires `onnx` and `onnxscript` to be installed.
