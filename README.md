# pixelmatch-ffi

[mapbox/pixelmatch-cpp](https://github.com/mapbox/pixelmatch-cpp)（JS 版 pixelmatch 8.x とビット一致する C++ 移植）を
Rust でラップして C ABI を公開し、Python / .NET から使えるようにしたもの。

```
vendor/pixelmatch-cpp/    git submodule（v8.0.0 固定）
crates/pixelmatch-sys/    C++ を extern "C" シムでビルド（例外は境界で捕捉）
crates/pixelmatch/        安全な Rust API（寸法・stride・バッファ長を検証）
crates/pixelmatch-ffi/    公開 C ABI（cdylib / staticlib）と include/pixelmatch_ffi.h
bindings/python/          ctypes ラッパー + Pillow / numpy アダプター
bindings/dotnet/          LibraryImport ラッパー + SkiaSharp / System.Drawing アダプター
```

対象プラットフォーム: Linux x64 / arm64 (glibc 2.28+)、Windows x64 / arm64。C++ ランタイムは静的リンク済みで追加インストール不要。

## 開発

```bash
git submodule update --init
mise install          # Rust / uv / .NET SDK / cbindgen（Python 本体は uv が管理）
mise run test         # Rust / Python / .NET の全テスト
mise run lint
mise run header       # C ABI を変えたらヘッダーを再生成
mise run notices      # 依存を変えたら THIRD-PARTY-NOTICES.txt を再生成（cargo-about）
```

## Python

```bash
# ビルド済み wheel（GitHub Pages のインデックス経由）
uv add pixelmatch-ffi --index https://www.jumboly.jp/pixelmatch-ffi/simple
# ソースから（Rust ツールチェインと C++17 コンパイラが必要）
uv add "pixelmatch-ffi @ git+https://github.com/jumboly/pixelmatch-ffi@v0.1.1#subdirectory=bindings/python"
```

```python
from PIL import Image
from pixelmatch_ffi.pil import compare        # extras: pixelmatch-ffi[pillow]

r = compare(Image.open("a.png"), Image.open("b.png"), diff=True, threshold=0.1)
print(r.mismatch); r.diff.save("diff.png")

from pixelmatch_ffi.numpy import compare      # (H, W, 3|4) uint8、RGB 順（OpenCV は BGR なので変換してから）
from pixelmatch_ffi import pixelmatch         # 生 RGBA バッファ API
```

## .NET

GitHub Release に添付した `.nupkg` をローカルフィード等に置いて参照する。

| パッケージ | 内容 |
|---|---|
| `PixelmatchFfi` | 中核（`Span<byte>` の生 RGBA API）。依存なし |
| `PixelmatchFfi.SkiaSharp` | `SKBitmap` を比較（BGRA / 乗算済みアルファは自動変換）。Linux では利用側で `SkiaSharp.NativeAssets.Linux*` を追加 |
| `PixelmatchFfi.SystemDrawing` | `System.Drawing.Bitmap` を比較（Windows 専用） |

```csharp
using var r = SkiaPixelmatch.Compare(bmp1, bmp2, new PixelmatchOptions { Threshold = 0.1 }, createDiff: true);
Console.WriteLine(r.Mismatch);   // r.Diff は SKBitmap
```

## リリース

1. `Cargo.toml` / `bindings/python/pyproject.toml` / `pixelmatch_ffi/__init__.py` / `bindings/dotnet/Directory.Build.props` のバージョンを揃える（`python3 scripts/check_versions.py` で確認）
2. `v<version>` タグを push → wheel / nupkg を GitHub Release に添付（release.yml）。完了後に pages.yml が Pages の PEP 503 インデックスを再生成（手動実行も可）
3. 初回のみ: リポジトリ設定で Pages のソースを「GitHub Actions」にする

## ライセンス

ISC（Copyright (c) 2026, jumboly）。

ネイティブライブラリには pixelmatch-cpp（© Mapbox, ISC）と Rust 標準ライブラリ（MIT）が含まれる。
第三者ライセンスの一覧は [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt) にあり、
`LICENSE` とともに wheel（`pixelmatch_ffi/_lib/`）と各 nupkg（ルート）に同梱している。
