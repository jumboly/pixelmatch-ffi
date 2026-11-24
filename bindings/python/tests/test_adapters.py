"""Pillow / numpy アダプターが生バッファ API と同じ結果を返し、型変換を正しく行うことを検証する。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pixelmatch_ffi import numpy as pm_np
from pixelmatch_ffi import pil as pm_pil

FIXTURES = Path(__file__).resolve().parents[3] / "vendor" / "pixelmatch-cpp" / "test" / "fixtures"


def open_fixture(name: str) -> Image.Image:
    with Image.open(FIXTURES / f"{name}.png") as im:
        im.load()
        return im.copy()


def expected_diff(name: str) -> bytes:
    return open_fixture(name).convert("RGBA").tobytes()


def test_pil_matches_fixture():
    r = pm_pil.compare(open_fixture("1a"), open_fixture("1b"), diff=True, threshold=0.05)
    assert r.mismatch == 152
    assert r.diff is not None and r.diff.mode == "RGBA" and r.diff.size == (r.diff.width, r.diff.height)
    assert r.diff.tobytes() == expected_diff("1diff")


def test_pil_converts_modes_and_skips_diff():
    a, b = open_fixture("1a"), open_fixture("1b")
    # RGB や乗算済み RGBa でも RGBA に正規化されて比較される（1a/1b は不透明なので結果は同じ）
    r = pm_pil.compare(a.convert("RGB"), b.convert("RGBa"), threshold=0.05)
    assert r == (152, None)


def test_pil_size_mismatch():
    with pytest.raises(ValueError):
        pm_pil.compare(Image.new("RGBA", (2, 2)), Image.new("RGBA", (2, 3)))


def test_numpy_matches_fixture_and_accepts_views():
    a = np.asarray(open_fixture("1a").convert("RGBA"))
    b = np.asarray(open_fixture("1b").convert("RGBA"))
    r = pm_np.compare(a, b, diff=True, threshold=0.05)
    assert r.mismatch == 152
    assert r.diff is not None and r.diff.tobytes() == expected_diff("1diff")

    # 非連続ビュー（部分切り出し）と RGB 3 チャンネル入力
    crop = (slice(10, 40), slice(5, 50))
    full = pm_np.compare(a[crop].copy(), b[crop].copy(), threshold=0.05).mismatch
    assert pm_np.compare(a[crop], b[crop], threshold=0.05).mismatch == full
    assert pm_np.compare(a[..., :3], b[..., :3], threshold=0.05).mismatch == 152


def test_numpy_ignore_mask():
    a = np.asarray(open_fixture("9a").convert("RGBA"))
    b = np.asarray(open_fixture("9b").convert("RGBA"))
    h, w = a.shape[:2]
    mask = (np.arange(h * w) <= h * w // 2).reshape(h, w)
    assert pm_np.compare(a, b, ignore_mask=mask, threshold=0.05).mismatch == 12422


def test_numpy_rejects_bad_shape():
    with pytest.raises(ValueError):
        pm_np.compare(np.zeros((2, 2), np.uint8), np.zeros((2, 2), np.uint8))
