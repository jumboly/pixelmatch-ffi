from __future__ import annotations

from typing import Generic, NamedTuple, Optional, TypeVar

T = TypeVar("T")


class CompareResult(NamedTuple, Generic[T]):
    """画像型アダプターの戻り値。`diff` は要求しなかった場合 None。"""

    mismatch: int
    diff: Optional[T]
