"""mapbox/pixelmatch (C++ 版) のネイティブ実装を使ったピクセル単位の画像比較。

入力は RGBA8 の生バイト列（bytes / bytearray / memoryview / numpy 配列などバッファプロトコル対応の
C 連続オブジェクト）。PNG 等のデコードは Pillow など利用側のライブラリで行う。
"""

from __future__ import annotations

import ctypes
from contextlib import ExitStack
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    # collections.abc.Buffer は 3.12+ のため、実行時には import せず型チェック専用にする
    from collections.abc import Buffer as _BufferLike

from ._native import Buffer, PmColor, PmImage, PmOptions, lib

__all__ = ["pixelmatch", "PixelmatchError", "__version__", "native_version"]
__version__ = "0.1.0"

Color = Tuple[int, int, int]

_STATUS_OUT_OF_MEMORY = 9


class PixelmatchError(ValueError):
    """ネイティブライブラリがエラーを返した。`status` は C ABI の PmStatus 値。"""

    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(lib.pm_status_message(status).decode())


def native_version() -> str:
    return lib.pm_version().decode()


def _color(c: Color) -> PmColor:
    r, g, b = c
    return PmColor(r, g, b)


def pixelmatch(
    img1: _BufferLike,
    img2: _BufferLike,
    width: int,
    height: int,
    output: Optional[_BufferLike] = None,
    *,
    threshold: float = 0.1,
    include_aa: bool = False,
    alpha: float = 0.1,
    aa_color: Color = (255, 255, 0),
    diff_color: Color = (255, 0, 0),
    diff_color_alt: Optional[Color] = None,
    diff_mask: bool = False,
    checkerboard: bool = True,
    ignore_mask: Optional[_BufferLike] = None,
    window_size: int = 0,
    stride1: int = 0,
    stride2: int = 0,
) -> int:
    """2 枚の RGBA8 画像を比較し、差分ピクセル数を返す。

    Args:
        output: 書き込み可能な ``width * height * 4`` バイトのバッファ。指定すると diff 画像を書き込む。
        ignore_mask: ``width * height`` バイト。非 0 のピクセルは比較しない。
        window_size: 非 0 なら N×N 窓内の差分数の最大値を返す。
        stride1, stride2: 行のバイト数。0 なら ``width * 4``。

    Raises:
        PixelmatchError: 寸法やバッファ長が不正。
        MemoryError: ネイティブ側でメモリ確保に失敗。
    """
    if not (0 <= width <= 0xFFFFFFFF and 0 <= height <= 0xFFFFFFFF):
        raise ValueError("width and height must fit in uint32")

    opts = PmOptions()
    lib.pm_options_init(ctypes.byref(opts))
    opts.threshold = threshold
    opts.alpha = alpha
    opts.include_aa = bool(include_aa)
    opts.aa_color = _color(aa_color)
    opts.diff_color = _color(diff_color)
    if diff_color_alt is not None:
        opts.diff_color_alt = _color(diff_color_alt)
        opts.has_diff_color_alt = 1
    opts.diff_mask = bool(diff_mask)
    opts.checkerboard = bool(checkerboard)
    opts.window_size = window_size

    with ExitStack() as stack:
        p1, n1 = stack.enter_context(Buffer(img1))
        p2, n2 = stack.enter_context(Buffer(img2))
        out_ptr, out_len = (None, 0)
        if output is not None:
            out_ptr, out_len = stack.enter_context(Buffer(output, writable=True))
        mask_ptr, mask_len = (None, 0)
        if ignore_mask is not None:
            mask_ptr, mask_len = stack.enter_context(Buffer(ignore_mask))

        i1 = PmImage(p1, n1, stride1)
        i2 = PmImage(p2, n2, stride2)
        count = ctypes.c_uint64()
        status = lib.pm_pixelmatch(
            ctypes.byref(i1),
            ctypes.byref(i2),
            width,
            height,
            out_ptr,
            out_len,
            mask_ptr,
            mask_len,
            ctypes.byref(opts),
            ctypes.byref(count),
        )

    if status == _STATUS_OUT_OF_MEMORY:
        raise MemoryError("pixelmatch: out of memory")
    if status != 0:
        raise PixelmatchError(status)
    return count.value
