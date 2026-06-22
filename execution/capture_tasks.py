import time

from PIL import ImageGrab

from api_client import image_to_jpeg_bytes, post_image_bytes, post_images_bytes


VIDEO_PREVIEW_MAX_SIDE = 640


def capture_image(box, capture_dir, server_url):
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    image_path = capture_dir / f"capture_{timestamp}.png"
    image = ImageGrab.grab(bbox=box).convert("RGB")
    image.save(image_path)

    result = post_image_bytes(
        server_url,
        "/predict",
        image_to_jpeg_bytes(image),
        file_name=f"capture_{timestamp}.jpg",
    )
    return image_path, result


def capture_video(box, capture_dir, server_url, seconds, fps):
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    delay = 1 / fps
    end_time = time.perf_counter() + seconds
    next_frame_time = time.perf_counter()
    preview_frames = []
    upload_frames = []
    index = 0

    while time.perf_counter() < end_time:
        frame = ImageGrab.grab(bbox=box).convert("RGB")
        upload_frames.append(
            (f"frame_{index + 1}.jpg", image_to_jpeg_bytes(frame))
        )
        preview_frames.append(make_preview_frame(frame))

        index += 1
        next_frame_time += delay
        sleep_for = next_frame_time - time.perf_counter()
        if sleep_for > 0:
            time.sleep(sleep_for)

    gif_path = capture_dir / f"video_{timestamp}.gif"
    if preview_frames:
        preview_frames[0].save(
            gif_path,
            save_all=True,
            append_images=preview_frames[1:],
            duration=int(delay * 1000),
            loop=0,
        )

    if not upload_frames:
        return gif_path, {"error": "No video frames could be captured."}

    result = post_images_bytes(server_url, "/predict_images", upload_frames)
    return gif_path, result


def make_preview_frame(frame):
    preview = frame.copy()
    preview.thumbnail((VIDEO_PREVIEW_MAX_SIDE, VIDEO_PREVIEW_MAX_SIDE))
    return preview
