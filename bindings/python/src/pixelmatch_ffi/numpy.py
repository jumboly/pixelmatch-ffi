"""numpy 配列用アダプター。`pip install pixelmatch-ffi[numpy]` が必要。

形状 (H, W, 4) または (H, W, 3) の uint8 配列を RGB(A) 順として扱う。
OpenCV の配列は BGR(A) 順なので、cv2.cvtColor で RGB(A) に変換してから渡すこと。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from . import pixelmatch
from ._result import CompareResult

__all__ = ["compare", "CompareResult"]


def _rgba(a: np.ndarray, name: str) -> np.ndarray:
    if a.dtype != np.uint8 or a.ndim != 3 or a.shape[2] not in (3, 4):
        raise ValueError(f"{name} must be a uint8 array of shape (H, W, 3|4), got {a.dtype} {a.shape}")
    if a.shape[2] == 3:
        alpha = np.full(a.shape[:2] + (1,), 255, dtype=np.uint8)
        return np.concatenate([a, alpha], axis=2)
    # 切り出し (a[y0:y1, x0:x1]) などの非連続ビューはバッファとして渡せないため、その場合だけコピーする
    return np.ascontiguousarray(a)


def compare(
    img1: np.ndarray,
    img2: np.ndarray,
    *,
    diff: bool = False,
    ignore_mask: np.ndarray | None = None,
    **options: Any,
) -> CompareResult[np.ndarray]:
    """2 枚の画像配列を比較する。

    Args:
        diff: True なら diff 画像 (H, W, 4) の uint8 配列も返す。
        ignore_mask: 形状 (H, W) の配列。非 0 / True のピクセルは比較しない。
        **options: :func:`pixelmatch_ffi.pixelmatch` のキーワード引数（threshold など）。
    """
    a, b = _rgba(img1, "img1"), _rgba(img2, "img2")
    if a.shape[:2] != b.shape[:2]:
        raise ValueError(f"image shapes do not match: {img1.shape} vs {img2.shape}")
    h, w = a.shape[:2]
    if ignore_mask is not None:
        if ignore_mask.shape != (h, w):
            raise ValueError(f"ignore_mask must have shape {(h, w)}, got {ignore_mask.shape}")
        options["ignore_mask"] = np.ascontiguousarray(ignore_mask, dtype=np.uint8)
    out = np.empty((h, w, 4), dtype=np.uint8) if diff else None
    n = pixelmatch(a, b, w, h, out, **options)
    return CompareResult(n, out)
