using System;
using SkiaSharp;

namespace PixelmatchFfi.SkiaSharp;

/// <summary>SkiaSharp の <see cref="SKBitmap"/> を直接比較するアダプター。</summary>
public static class SkiaPixelmatch
{
    /// <summary>2 枚のビットマップを比較する。ピクセル形式は自動で非乗算 RGBA8 に変換する。</summary>
    /// <param name="img1">比較元。</param>
    /// <param name="img2">比較先。</param>
    /// <param name="options">比較オプション。<c>null</c> なら既定値。</param>
    /// <param name="createDiff"><c>true</c> なら diff 画像（Rgba8888 / Unpremul）を返す。</param>
    /// <param name="ignoreMask">空でなければ <c>width * height</c> バイト。非 0 のピクセルを比較しない。</param>
    public static ImageCompareResult<SKBitmap> Compare(
        SKBitmap img1,
        SKBitmap img2,
        PixelmatchOptions? options = null,
        bool createDiff = false,
        ReadOnlySpan<byte> ignoreMask = default)
    {
        ArgumentNullException.ThrowIfNull(img1);
        ArgumentNullException.ThrowIfNull(img2);
        if (img1.Width != img2.Width || img1.Height != img2.Height)
        {
            throw new ArgumentException(
                $"image sizes do not match: {img1.Width}x{img1.Height} vs {img2.Width}x{img2.Height}");
        }
        int w = img1.Width, h = img1.Height;

        using var p1 = Rgba.From(img1);
        using var p2 = Rgba.From(img2);

        if (!createDiff)
        {
            ulong n = Pixelmatch.Compare(p1.Span, p1.RowBytes, p2.Span, p2.RowBytes, w, h, default, options, ignoreMask);
            return new ImageCompareResult<SKBitmap>(n, null);
        }

        var diff = new SKBitmap(new SKImageInfo(w, h, SKColorType.Rgba8888, SKAlphaType.Unpremul));
        try
        {
            ulong n;
            if (diff.RowBytes == w * 4)
            {
                n = Pixelmatch.Compare(p1.Span, p1.RowBytes, p2.Span, p2.RowBytes, w, h, Rgba.Pixels(diff), options, ignoreMask);
            }
            else
            {
                // pixelmatch の出力は行詰めなしのため、行に詰め物があるビットマップには一時バッファ経由で書く
                var tmp = new byte[w * h * 4];
                n = Pixelmatch.Compare(p1.Span, p1.RowBytes, p2.Span, p2.RowBytes, w, h, tmp, options, ignoreMask);
                var dst = Rgba.Pixels(diff);
                for (int y = 0; y < h; y++)
                {
                    tmp.AsSpan(y * w * 4, w * 4).CopyTo(dst.Slice(y * diff.RowBytes));
                }
            }
            diff.NotifyPixelsChanged();
            return new ImageCompareResult<SKBitmap>(n, diff);
        }
        catch
        {
            diff.Dispose();
            throw;
        }
    }

    /// <summary>非乗算 RGBA8 のピクセル列。必要なときだけ変換用のビットマップを持つ。</summary>
    private readonly ref struct Rgba
    {
        private readonly SKBitmap? _converted;
        public readonly ReadOnlySpan<byte> Span;
        public readonly int RowBytes;

        private Rgba(SKBitmap source, SKBitmap? converted)
        {
            _converted = converted;
            var bmp = converted ?? source;
            Span = Pixels(bmp);
            RowBytes = bmp.RowBytes;
        }

        public static Rgba From(SKBitmap bmp)
        {
            // 既に非乗算 RGBA8 ならコピーせず stride 付きで直接渡す（不透明画像は乗算の有無が結果に影響しない）
            if (bmp.ColorType == SKColorType.Rgba8888 &&
                bmp.AlphaType is SKAlphaType.Unpremul or SKAlphaType.Opaque)
            {
                return new Rgba(bmp, null);
            }
            // BGRA や乗算済みアルファ (多くのプラットフォームの既定) は Skia 自身に正しく変換させる
            var info = new SKImageInfo(bmp.Width, bmp.Height, SKColorType.Rgba8888, SKAlphaType.Unpremul);
            var converted = new SKBitmap(info);
            using var pixmap = bmp.PeekPixels();
            if (pixmap is null || !pixmap.ReadPixels(converted.Info, converted.GetPixels(), converted.RowBytes))
            {
                converted.Dispose();
                throw new ArgumentException($"unsupported bitmap format: {bmp.ColorType}/{bmp.AlphaType}");
            }
            return new Rgba(bmp, converted);
        }

        public static unsafe Span<byte> Pixels(SKBitmap bmp)
        {
            // 最終行は RowBytes 分の詰め物がない場合もあるため、厳密な長さで切る
            long len = bmp.Height == 0 ? 0 : (long)bmp.RowBytes * (bmp.Height - 1) + (long)bmp.Width * bmp.BytesPerPixel;
            return new Span<byte>((void*)bmp.GetPixels(), checked((int)len));
        }

        public void Dispose() => _converted?.Dispose();
    }
}
