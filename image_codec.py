import base64
import io
import zipfile

import comfy.utils
import numpy as np
from PIL import Image, ImageOps
import torch


def image_to_base64(image):
    pixels = 255.0 * image[0].cpu().numpy()
    pil_image = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))
    output = io.BytesIO()
    pil_image.save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode()


def mask_to_base64(image):
    pixels = np.clip(255.0 * image[0].cpu().numpy(), 0, 255).astype(np.uint8)
    alpha = np.uint8((np.sum(pixels, axis=-1) > 0) * 255)
    rgba = np.dstack((pixels, alpha))
    output = io.BytesIO()
    Image.fromarray(rgba).save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode()


def bytes_to_image(image_bytes, keep_alpha=True):
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes)))
    if not keep_alpha:
        image = image.convert("RGB")
    pixels = np.array(image).astype(np.float32) / 255.0
    return torch.from_numpy(pixels)[None,]


def first_image_from_zip(archive):
    with zipfile.ZipFile(io.BytesIO(archive)) as images:
        for entry in images.infolist():
            if not entry.is_dir() and entry.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                return images.read(entry)
    raise RuntimeError("NovelAI response did not contain an image.")


def blank_image():
    return torch.tensor([[[0]]])


def resize_image(image, size):
    width, height = size
    samples = image.movedim(-1, 1)
    samples = comfy.utils.common_upscale(samples, width, height, "bilinear", "disabled")
    return samples.movedim(1, -1)


def resize_mask(mask, image_size=None, is_v4=False):
    samples = mask.movedim(-1, 1)
    width, height = (samples.shape[3], samples.shape[2]) if image_size is None else image_size
    width = int(np.ceil(width / 64) * 8)
    height = int(np.ceil(height / 64) * 8)
    samples = comfy.utils.common_upscale(samples, width, height, "nearest-exact", "disabled")
    if is_v4:
        samples = comfy.utils.common_upscale(samples, width * 8, height * 8, "nearest-exact", "disabled")
    return samples.movedim(1, -1)


def calculate_resolution(pixel_count, aspect_ratio):
    pixel_count /= 4096
    width, height = aspect_ratio
    scale = (pixel_count * width / height) ** 0.5
    return int(np.floor(scale) * 64), int(np.floor(scale * height / width) * 64)


def calculate_skip_cfg_above_sigma(width, height):
    return (width * height / 1011712) ** 0.5 * 19
