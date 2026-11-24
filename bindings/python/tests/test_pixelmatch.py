"""上流 pixelmatch-cpp の fixtures で、Python → C ABI の受け渡しに欠落がないことを検証する。"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from PIL import Image

from pixelmatch_ffi import PixelmatchError, __version__, native_version, pixelmatch

FIXTURES = Path(__file__).resolve().parents[3] / "vendor" / "pixelmatch-cpp" / "test" / "fixtures"


def load(name: str) -> tuple[bytes, int, int]:
    with Image.open(FIXTURES / f"{name}.png") as im:
        rgba = im.convert("RGBA")
        return rgba.tobytes(), rgba.width, rgba.height


CASES = [
    ("1a", "1b", "1diff", {"threshold": 0.05}, 152, False),
    ("1a", "1b", "1diffdefaultthreshold", {}, 121, False),
    ("1a", "1b", "1diffmask", {"threshold": 0.05, "diff_mask": True}, 152, False),
    ("1a", "1a", "1emptydiffmask", {"threshold": 0, "diff_mask": True}, 0, False),
    (
        "2a",
        "2b",
        "2diff",
        {"threshold": 0.05, "alpha": 0.5, "aa_color": (0, 192, 0), "diff_color": (255, 0, 255)},
        12821,
        False,
    ),
    ("3a", "3b", "3diff", {"threshold": 0.05}, 220, False),
    ("4a", "4b", "4diff", {"threshold": 0.05}, 36563, False),
    ("5a", "5b", "5diff", {"threshold": 0.05}, 0, False),
    ("6a", "6b", "6diff", {"threshold": 0.05}, 51, False),
    ("6a", "6a", "6empty", {"threshold": 0}, 0, False),
    ("7a", "7b", "7diff", {"diff_color_alt": (0, 255, 0)}, 2440, False),
    ("8a", "5b", "8diff", {"threshold": 0.05}, 32896, False),
    ("9a", "9b", "9diff", {"threshold": 0.05}, 12422, True),
    ("10a", "10b", "10diff", {"threshold": 0.05}, 0, True),
]


@pytest.mark.parametrize(("a", "b", "diff", "opts", "expected", "ignore_half"), CASES)
def test_fixtures(a, b, diff, opts, expected, ignore_half):
    d1, w, h = load(a)
    d2, _, _ = load(b)
    if ignore_half:
        opts = {**opts, "ignore_mask": bytes(int(i <= w * h // 2) for i in range(w * h))}
    out = bytearray(w * h * 4)
    assert pixelmatch(d1, d2, w, h, out, **opts) == expected
    assert pixelmatch(d1, d2, w, h, **opts) == expected
    assert bytes(out) == load(diff)[0]


def test_accepts_readonly_memoryview_and_bytearray():
    d1, w, h = load("1a")
    d2, _, _ = load("1b")
    assert pixelmatch(memoryview(d1), bytearray(d2), w, h, threshold=0.05) == 152


def test_errors():
    with pytest.raises(PixelmatchError) as e:
        pixelmatch(b"\0" * 7, b"\0" * 8, 1, 2)
    assert e.value.status == 4  # PM_STATUS_IMAGE_TOO_SMALL
    with pytest.raises(PixelmatchError):
        pixelmatch(b"\0" * 8, b"\0" * 8, 1, 2, bytearray(7))
    with pytest.raises(BufferError):
        pixelmatch(b"\0" * 8, b"\0" * 8, 1, 2, b"\0" * 8)  # 出力に読み取り専用バッファ


def test_threads():
    d1, w, h = load("4a")
    d2, _, _ = load("4b")
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(pixelmatch(d1, d2, w, h, threshold=0.05)))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [36563] * 4


def test_version():
    # ラッパーと同梱ネイティブライブラリの版ずれを検出する（リリースごとに書き換えずに済むよう固定値にしない）
    assert native_version() == __version__
