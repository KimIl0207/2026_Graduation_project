import io
import json
import time
import urllib.request


def image_to_jpeg_bytes(image, quality=90):
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def build_multipart(parts):
    boundary = f"----ADAMBoundary{int(time.time() * 1000)}"
    body = io.BytesIO()

    for field_name, file_name, mime_type, data in parts:
        body.write(f"--{boundary}\r\n".encode())
        body.write(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{file_name}"\r\n'.encode()
        )
        body.write(f"Content-Type: {mime_type}\r\n\r\n".encode())
        body.write(data)
        body.write(b"\r\n")

    body.write(f"--{boundary}--\r\n".encode())
    return body.getvalue(), f"multipart/form-data; boundary={boundary}"


def post_multipart(server_url, endpoint, parts):
    body, content_type = build_multipart(parts)
    request = urllib.request.Request(
        f"{server_url.rstrip('/')}{endpoint}",
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def post_image_bytes(server_url, endpoint, image_bytes, file_name="capture.jpg"):
    return post_multipart(
        server_url,
        endpoint,
        [("file", file_name, "image/jpeg", image_bytes)],
    )


def post_images_bytes(server_url, endpoint, images):
    parts = [
        ("files", file_name, "image/jpeg", image_bytes)
        for file_name, image_bytes in images
    ]
    return post_multipart(server_url, endpoint, parts)
