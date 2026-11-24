"""Pillow (PIL.Image) 用アダプター。`pip install pixelmatch-ffi[pillow]` が必要。"""

from __future__ import annotations

from typing import Any

from PIL import Image

from . import pixelmatch
from ._result import CompareResult

__all__ = ["compare", "CompareResult"]


def _rgba(im: Image.Image) -> bytes:
    # pixelmatch は非乗算 RGBA8 前提。P / L / RGB / RGBa(乗算済み) などは Pillow に正しく変換させる
    return (im if im.mode == "RGBA" else im.convert("RGBA")).tobytes()


def compare(
    img1: Image.Image,
    img2: Image.Image,
    *,
    diff: bool = False,
    **options: Any,
) -> CompareResult[Image.Image]:
    """2 枚の画像を比較する。

    Args:
        diff: True なら diff 画像 (RGBA の PIL.Image) も返す。
        **options: :func:`pixelmatch_ffi.pixelmatch` のキーワード引数（threshold など）。
    """
    if img1.size != img2.size:
        raise ValueError(f"image sizes do not match: {img1.size} vs {img2.size}")
    w, h = img1.size
    out = bytearray(w * h * 4) if diff else None
    n = pixelmatch(_rgba(img1), _rgba(img2), w, h, out, **options)
    # frombuffer は bytearray をコピーせず共有する（out はこの関数でしか参照されない）
    image = Image.frombuffer("RGBA", (w, h), out, "raw", "RGBA", 0, 1) if out is not None else None
    return CompareResult(n, image)
