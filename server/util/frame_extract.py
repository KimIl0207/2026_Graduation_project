from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path
from typing import Literal

import numpy as np


SampleRate = int | float | tuple[int, int]
ColorFormat = Literal["rgb", "bgr"]

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / ".frame_cache"
_MEMORY_CACHE: dict[str, list[np.ndarray]] = {}


def _normalize_sample_rate(samples_per_second: SampleRate) -> SampleRate:
    if isinstance(samples_per_second, tuple):
        if len(samples_per_second) != 2:
            raise ValueError("samples_per_second tuple must be (min_count, max_count).")

        min_count, max_count = samples_per_second
        if min_count < 0 or max_count < 0:
            raise ValueError("samples_per_second values must be non-negative.")
        if min_count > max_count:
            raise ValueError("samples_per_second min_count cannot exceed max_count.")
        return min_count, max_count

    if samples_per_second <= 0:
        raise ValueError("samples_per_second must be greater than 0.")

    return samples_per_second


def _cache_key(
    video_path: Path,
    samples_per_second: SampleRate,
    seed: int | None,
    color_format: ColorFormat,
    max_duration_seconds: float | None,
) -> str:
    stat = video_path.stat()
    payload = {
        "path": str(video_path),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "samples_per_second": samples_per_second,
        "max_duration_seconds": max_duration_seconds,
        "seed": seed,
        "color_format": color_format,
    }
    raw_key = json.dumps(payload, sort_keys=True, default=list).encode("utf-8")
    return hashlib.sha256(raw_key).hexdigest()


def _cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.npz"


def _copy_frames(frames: list[np.ndarray]) -> list[np.ndarray]:
    return [frame.copy() for frame in frames]


def _load_cached_frames(cache_file: Path) -> list[np.ndarray] | None:
    if not cache_file.exists():
        return None

    with np.load(cache_file) as data:
        frames = data["frames"]
        return [frame.copy() for frame in frames]


def _save_cached_frames(cache_file: Path, frames: list[np.ndarray]) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache_file, frames=np.asarray(frames))


def _sample_count_for_second(samples_per_second: SampleRate, rng: random.Random) -> int:
    if isinstance(samples_per_second, tuple):
        return rng.randint(samples_per_second[0], samples_per_second[1])

    whole_count = int(samples_per_second)
    fractional = float(samples_per_second) - whole_count
    if fractional > 0 and rng.random() < fractional:
        whole_count += 1

    return whole_count


def _pick_frame_indices(
    frame_count: int,
    fps: float,
    samples_per_second: SampleRate,
    rng: random.Random,
    max_duration_seconds: float | None = None,
) -> list[int]:
    duration_seconds = frame_count / fps
    if max_duration_seconds is not None:
        if max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be greater than 0.")
        duration_seconds = min(duration_seconds, max_duration_seconds)

    max_frame_count = min(frame_count, int(math.ceil(duration_seconds * fps)))
    selected_indices: list[int] = []

    for second in range(math.ceil(duration_seconds)):
        start_frame = int(second * fps)
        end_frame = min(int((second + 1) * fps), max_frame_count)
        if start_frame >= end_frame:
            continue

        second_frame_count = end_frame - start_frame
        sample_count = min(
            _sample_count_for_second(samples_per_second, rng),
            second_frame_count,
        )
        if sample_count <= 0:
            continue

        selected_indices.extend(
            rng.sample(range(start_frame, end_frame), sample_count),
        )

    return sorted(selected_indices)


def extract_random_frames(
    video_path: str | Path,
    samples_per_second: SampleRate = 1,
    *,
    max_duration_seconds: float | None = 5,
    cache_dir: str | Path | None = DEFAULT_CACHE_DIR,
    seed: int | None = None,
    color_format: ColorFormat = "rgb",
    force_refresh: bool = False,
) -> list[np.ndarray]:
    """Extract random video frames and return a cached result.

    Args:
        video_path: Path to the video file.
        samples_per_second: Number of frames to sample per second. A tuple like
            ``(1, 2)`` randomly picks 1 to 2 frames per second.
        max_duration_seconds: Only sample frames from the first N seconds.
            Pass ``None`` to sample from the full video.
        cache_dir: Directory for disk cache. Pass ``None`` to use memory cache only.
        seed: Optional random seed. Use this for reproducible sampling.
        color_format: Return frames as RGB or OpenCV's native BGR.
        force_refresh: Ignore existing cache and extract frames again.

    Returns:
        A list of ``numpy.ndarray`` frames.
    """
    try:
        import cv2
    except ImportError as exc:
        raise ImportError(
            "OpenCV is required for frame extraction. Install it with "
            "`pip install opencv-python`.",
        ) from exc

    path = Path(video_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Video file was not found: {path}")
    if color_format not in {"rgb", "bgr"}:
        raise ValueError("color_format must be 'rgb' or 'bgr'.")

    normalized_sample_rate = _normalize_sample_rate(samples_per_second)
    key = _cache_key(path, normalized_sample_rate, seed, color_format, max_duration_seconds)

    if not force_refresh and key in _MEMORY_CACHE:
        return _copy_frames(_MEMORY_CACHE[key])

    cache_file = None
    if cache_dir is not None:
        cache_file = _cache_path(Path(cache_dir).expanduser().resolve(), key)
        if not force_refresh:
            cached_frames = _load_cached_frames(cache_file)
            if cached_frames is not None:
                _MEMORY_CACHE[key] = _copy_frames(cached_frames)
                return cached_frames

    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError(f"Could not open video file: {path}")

        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0 or frame_count <= 0:
            raise ValueError(f"Could not read video metadata: {path}")

        rng = random.Random(seed)
        frame_indices = _pick_frame_indices(
            frame_count,
            fps,
            normalized_sample_rate,
            rng,
            max_duration_seconds,
        )

        frames: list[np.ndarray] = []
        for frame_index in frame_indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok:
                continue

            if color_format == "rgb":
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(frame)
    finally:
        capture.release()

    _MEMORY_CACHE[key] = _copy_frames(frames)
    if cache_file is not None:
        _save_cached_frames(cache_file, frames)

    return _copy_frames(frames)


def clear_frame_cache(cache_dir: str | Path | None = DEFAULT_CACHE_DIR) -> None:
    """Clear in-memory cache and optionally remove cached frame files."""
    _MEMORY_CACHE.clear()

    if cache_dir is None:
        return

    path = Path(cache_dir).expanduser().resolve()
    if not path.exists():
        return

    for cache_file in path.glob("*.npz"):
        cache_file.unlink()
