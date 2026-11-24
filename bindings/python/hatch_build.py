"""wheel ビルド時にネイティブライブラリ (pixelmatch_ffi の cdylib) を同梱する hatchling フック。

- CI: 環境変数 PIXELMATCH_FFI_PREBUILT にビルド済みライブラリのパスを渡す（再ビルドしない）
- Git 直接指定 / ローカル開発: リポジトリ直下で `cargo build --release` を実行する
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


def _lib_filename() -> str:
    if sys.platform == "win32":
        return "pixelmatch_ffi.dll"
    if sys.platform == "darwin":
        return "libpixelmatch_ffi.dylib"
    return "libpixelmatch_ffi.so"


def _platform_tag() -> str:
    # ctypes 経由で呼ぶため Python の ABI には依存せず、OS/CPU だけでタグ付けできる。
    # Linux の manylinux タグ付けは CI 上の auditwheel repair に任せる
    if sys.platform == "darwin":
        # sysconfig はインタプリタのビルド環境の OS 版を返し不必要に新しくなるため、
        # rustc の既定デプロイ対象 (arm64: 11.0 / x86_64: 10.12) に合わせる（macOS は開発用途のみ）
        import platform

        return "macosx_11_0_arm64" if platform.machine() == "arm64" else "macosx_10_12_x86_64"
    return sysconfig.get_platform().replace("-", "_").replace(".", "_")


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:
        lib = self._locate_or_build()
        name = _lib_filename()

        build_data["pure_python"] = False
        build_data["tag"] = f"py3-none-{_platform_tag()}"

        if version == "editable":
            # editable インストールではソースツリーのパッケージがそのまま import されるため、そこへ置く
            dest = Path(self.root, "src", "pixelmatch_ffi", "_lib")
            dest.mkdir(exist_ok=True)
            shutil.copy2(lib, dest / name)
        else:
            build_data["force_include"][str(lib)] = f"pixelmatch_ffi/_lib/{name}"
            # ISC 等は「複製物に著作権表示を含めること」が条件のため、ネイティブライブラリと一緒に同梱する。
            # license-files はプロジェクト外 (../../) を指すと wheel 内に不正なパスが生じるため使わない
            repo_root = Path(self.root).resolve().parents[1]
            for notice in ("LICENSE", "THIRD-PARTY-NOTICES.txt"):
                src = repo_root / notice
                if not src.is_file():
                    raise FileNotFoundError(f"{src} not found; it must be shipped with the wheel")
                build_data["force_include"][str(src)] = f"pixelmatch_ffi/_lib/{notice}"

    def _locate_or_build(self) -> Path:
        prebuilt = os.environ.get("PIXELMATCH_FFI_PREBUILT")
        if prebuilt:
            path = Path(prebuilt)
            if not path.is_file():
                raise FileNotFoundError(f"PIXELMATCH_FFI_PREBUILT={prebuilt} is not a file")
            return path

        repo_root = Path(self.root).resolve().parents[1]
        manifest = repo_root / "Cargo.toml"
        if not manifest.is_file():
            raise RuntimeError(
                "Rust workspace not found. Install from the Git repository "
                "(git+https://...#subdirectory=bindings/python) or set PIXELMATCH_FFI_PREBUILT."
            )
        if shutil.which("cargo") is None:
            raise RuntimeError(
                "cargo not found. Building pixelmatch-ffi from source requires a Rust toolchain "
                "and a C++17 compiler (https://rustup.rs)."
            )
        subprocess.run(
            ["cargo", "build", "--release", "-p", "pixelmatch-ffi", "--manifest-path", str(manifest)],
            check=True,
        )
        target_dir = Path(os.environ.get("CARGO_TARGET_DIR", repo_root / "target"))
        return target_dir / "release" / _lib_filename()
