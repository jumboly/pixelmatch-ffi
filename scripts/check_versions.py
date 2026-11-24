"""Cargo / pyproject / .NET (Directory.Build.props) / Python パッケージのバージョンが一致しているか検証する。

配布物ごとにバージョンを持つため、リリースタグと食い違ったまま公開されるのを防ぐ。
使い方: python scripts/check_versions.py [期待するバージョン (例: 0.1.0 または v0.1.0)]
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def versions() -> dict[str, str]:
    cargo = tomllib.loads((ROOT / "Cargo.toml").read_text())["workspace"]["package"]["version"]
    py = tomllib.loads((ROOT / "bindings/python/pyproject.toml").read_text())["project"]["version"]
    init = re.search(
        r'__version__ = "([^"]+)"', (ROOT / "bindings/python/src/pixelmatch_ffi/__init__.py").read_text()
    )
    csproj = re.search(
        r"<Version>([^<]+)</Version>",
        (ROOT / "bindings/dotnet/Directory.Build.props").read_text(),
    )
    return {
        "Cargo.toml": cargo,
        "pyproject.toml": py,
        "pixelmatch_ffi.__version__": init.group(1) if init else "?",
        "dotnet Directory.Build.props": csproj.group(1) if csproj else "?",
    }


def main() -> int:
    found = versions()
    expected = sys.argv[1].removeprefix("v") if len(sys.argv) > 1 else found["Cargo.toml"]
    bad = {k: v for k, v in found.items() if v != expected}
    for k, v in found.items():
        print(f"{'NG' if k in bad else 'ok'}  {k}: {v}")
    if bad:
        print(f"expected {expected}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
