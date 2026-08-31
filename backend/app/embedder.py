"""CLIP embeddings for images and text.

Uses openai/clip-vit-base-patch32 - ~600 MB, free, runs locally. Vectors are
L2-normalised so cosine distance in pgvector is a straight similarity measure.
"""
import logging
import threading

import numpy as np
import torch
from PIL import Image, ImageFile
from transformers import CLIPModel, CLIPProcessor

from . import config

# Mac photo libraries are full of HEIC; register the decoder if available.
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:  # pragma: no cover - optional codec
    pass

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None

log = logging.getLogger(__name__)

_model: CLIPModel | None = None
_processor: CLIPProcessor | None = None
_device = "cpu"
_load_lock = threading.Lock()
# Torch modules are not thread-safe for concurrent forward passes on MPS.
_infer_lock = threading.Lock()


def _pick_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"  # Apple Silicon GPU
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def load() -> None:
    """Load the model once. Downloads on first run, then uses the local cache."""
    global _model, _processor, _device
    if _model is not None:
        return
    with _load_lock:
        if _model is not None:
            return
        _device = _pick_device()
        log.info("Loading %s on %s", config.CLIP_MODEL, _device)
        processor = CLIPProcessor.from_pretrained(config.CLIP_MODEL)
        model = CLIPModel.from_pretrained(config.CLIP_MODEL).to(_device).eval()
        _processor, _model = processor, model
        log.info("Model ready")


def info() -> dict:
    return {
        "model": config.CLIP_MODEL,
        "device": _device,
        "loaded": _model is not None,
        "dimensions": config.EMBED_DIM,
    }


def _normalize(vecs: torch.Tensor) -> np.ndarray:
    vecs = vecs / vecs.norm(p=2, dim=-1, keepdim=True)
    return vecs.detach().cpu().numpy().astype(np.float32)


def embed_images(images: list[Image.Image]) -> np.ndarray:
    """Embed a batch of PIL images into normalised 512-d vectors."""
    load()
    rgb = [im.convert("RGB") for im in images]
    with _infer_lock:
        inputs = _processor(images=rgb, return_tensors="pt").to(_device)
        with torch.no_grad():
            feats = _model.get_image_features(**inputs)
        return _normalize(feats)


def embed_text(text: str) -> np.ndarray:
    """Embed a search phrase into the same vector space as the images."""
    load()
    with _infer_lock:
        inputs = _processor(
            text=[text], return_tensors="pt", padding=True, truncation=True
        ).to(_device)
        with torch.no_grad():
            feats = _model.get_text_features(**inputs)
        return _normalize(feats)[0]
