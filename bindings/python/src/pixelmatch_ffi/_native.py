"""ネイティブライブラリのロードと C ABI の ctypes 定義。

構造体定義は crates/pixelmatch-ffi/include/pixelmatch_ffi.h と 1:1 で対応させること。
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

ABI_VERSION = 1


class PmColor(ctypes.Structure):
    _fields_ = [("r", ctypes.c_uint8), ("g", ctypes.c_uint8), ("b", ctypes.c_uint8)]


class PmImage(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.c_void_p),
        ("len", ctypes.c_size_t),
        ("stride", ctypes.c_size_t),
    ]


class PmOptions(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("threshold", ctypes.c_double),
        ("alpha", ctypes.c_double),
        ("aa_color", PmColor),
        ("diff_color", PmColor),
        ("diff_color_alt", PmColor),
        ("has_diff_color_alt", ctypes.c_uint8),
        ("include_aa", ctypes.c_uint8),
        ("diff_mask", ctypes.c_uint8),
        ("checkerboard", ctypes.c_uint8),
        ("window_size", ctypes.c_uint64),
    ]


def _lib_filename() -> str:
    if sys.platform == "win32":
        return "pixelmatch_ffi.dll"
    if sys.platform == "darwin":
        return "libpixelmatch_ffi.dylib"
    return "libpixelmatch_ffi.so"


def _find_library() -> Path:
    # 開発時に cargo の出力を直接使えるよう、環境変数（ファイルかディレクトリ）を最優先にする
    override = os.environ.get("PIXELMATCH_FFI_LIBRARY")
    if override:
        path = Path(override)
        return path / _lib_filename() if path.is_dir() else path
    return Path(__file__).with_name("_lib") / _lib_filename()


def _load() -> ctypes.CDLL:
    path = _find_library()
    if not path.is_file():
        raise ImportError(f"pixelmatch-ffi native library not found: {path}")
    # CDLL は呼び出し中に GIL を解放するため、別スレッドでの並列比較がそのまま効く
    lib = ctypes.CDLL(str(path))

    lib.pm_abi_version.argtypes = []
    lib.pm_abi_version.restype = ctypes.c_uint32
    lib.pm_version.argtypes = []
    lib.pm_version.restype = ctypes.c_char_p
    lib.pm_status_message.argtypes = [ctypes.c_int]
    lib.pm_status_message.restype = ctypes.c_char_p
    lib.pm_options_init.argtypes = [ctypes.POINTER(PmOptions)]
    lib.pm_options_init.restype = ctypes.c_int
    lib.pm_pixelmatch.argtypes = [
        ctypes.POINTER(PmImage),
        ctypes.POINTER(PmImage),
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.POINTER(PmOptions),
        ctypes.POINTER(ctypes.c_uint64),
    ]
    lib.pm_pixelmatch.restype = ctypes.c_int

    abi = lib.pm_abi_version()
    if abi != ABI_VERSION:
        raise ImportError(f"pixelmatch-ffi ABI mismatch: library {abi}, wrapper {ABI_VERSION}")
    return lib


lib = _load()


# --- バッファプロトコル -------------------------------------------------------
# ctypes の from_buffer は書き込み可能なバッファにしか使えないため、bytes や読み取り専用の
# numpy 配列もコピーなしで渡せるよう、CPython の PyObject_GetBuffer を直接使う。


class _PyBuffer(ctypes.Structure):
    _fields_ = [
        ("buf", ctypes.c_void_p),
        ("obj", ctypes.c_void_p),
        ("len", ctypes.c_ssize_t),
        ("itemsize", ctypes.c_ssize_t),
        ("readonly", ctypes.c_int),
        ("ndim", ctypes.c_int),
        ("format", ctypes.c_char_p),
        ("shape", ctypes.c_void_p),
        ("strides", ctypes.c_void_p),
        ("suboffsets", ctypes.c_void_p),
        ("internal", ctypes.c_void_p),
    ]


_PyBUF_SIMPLE = 0  # C 連続でないバッファはエクスポーター側で BufferError になる
_PyBUF_WRITABLE = 1

_get_buffer = ctypes.pythonapi.PyObject_GetBuffer
_get_buffer.argtypes = [ctypes.py_object, ctypes.POINTER(_PyBuffer), ctypes.c_int]
_get_buffer.restype = ctypes.c_int
_release_buffer = ctypes.pythonapi.PyBuffer_Release
_release_buffer.argtypes = [ctypes.POINTER(_PyBuffer)]
_release_buffer.restype = None


class Buffer:
    """with 文の間だけバッファを固定し、(アドレス, バイト長) を提供する。"""

    def __init__(self, obj: object, *, writable: bool = False) -> None:
        self._obj = obj
        self._flags = _PyBUF_WRITABLE if writable else _PyBUF_SIMPLE
        self._view = _PyBuffer()

    def __enter__(self) -> tuple[int, int]:
        _get_buffer(self._obj, ctypes.byref(self._view), self._flags)
        return self._view.buf or 0, self._view.len

    def __exit__(self, *exc: object) -> None:
        _release_buffer(ctypes.byref(self._view))
