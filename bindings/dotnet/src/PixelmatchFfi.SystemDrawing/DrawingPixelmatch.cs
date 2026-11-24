using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.Versioning;

namespace PixelmatchFfi.SystemDrawing;

/// <summary>System.Drawing の <see cref="Bitmap"/> を直接比較するアダプター（Windows 専用）。</summary>
[SupportedOSPlatform("windows")]
public static class DrawingPixelmatch
{
    /// <summary>2 枚のビットマップを比較する。ピクセル形式は自動で非乗算 RGBA8 に変換する。</summary>
    /// <param name="img1">比較元。</param>
    /// <param name="img2">比較先。</param>
    /// <param name="options">比較オプション。<c>null</c> なら既定値。</param>
    /// <param name="createDiff"><c>true</c> なら diff 画像（Format32bppArgb）を返す。</param>
    /// <param name="ignoreMask">空でなければ <c>width * height</c> バイト。非 0 のピクセルを比較しない。</param>
    public static ImageCompareResult<Bitmap> Compare(
        Bitmap img1,
        Bitmap img2,
        PixelmatchOptions? options = null,
        bool createDiff = false,
        ReadOnlySpan<byte> ignoreMask = default)
    {
        ArgumentNullException.ThrowIfNull(img1);
        ArgumentNullException.ThrowIfNull(img2);
        if (img1.Size != img2.Size)
        {
            throw new ArgumentException($"image sizes do not match: {img1.Size} vs {img2.Size}");
        }
        int w = img1.Width, h = img1.Height;

        byte[] a = ToRgba(img1);
        byte[] b = ToRgba(img2);
        if (!createDiff)
        {
            return new ImageCompareResult<Bitmap>(Pixelmatch.Compare(a, b, w, h, default, options, ignoreMask), null);
        }

        var output = new byte[w * h * 4];
        ulong n = Pixelmatch.Compare(a, b, w, h, output, options, ignoreMask);
        return new ImageCompareResult<Bitmap>(n, FromRgba(output, w, h));
    }

    private static unsafe byte[] ToRgba(Bitmap bmp)
    {
        int w = bmp.Width, h = bmp.Height;
        var rgba = new byte[w * h * 4];
        // Format32bppArgb を指定すると GDI+ が任意の形式から非乗算 ARGB に変換してくれる。
        // メモリ上はリトルエンディアンで B,G,R,A の順なので R と B を入れ替える
        var data = bmp.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        try
        {
            for (int y = 0; y < h; y++)
            {
                // Stride はボトムアップ形式で負になりうるため、行ごとにポインタを計算する
                var src = new ReadOnlySpan<byte>((byte*)data.Scan0 + (long)y * data.Stride, w * 4);
                var dst = rgba.AsSpan(y * w * 4, w * 4);
                for (int i = 0; i < dst.Length; i += 4)
                {
                    dst[i] = src[i + 2];
                    dst[i + 1] = src[i + 1];
                    dst[i + 2] = src[i];
                    dst[i + 3] = src[i + 3];
                }
            }
        }
        finally
        {
            bmp.UnlockBits(data);
        }
        return rgba;
    }

    private static unsafe Bitmap FromRgba(byte[] rgba, int w, int h)
    {
        var bmp = new Bitmap(w, h, PixelFormat.Format32bppArgb);
        var data = bmp.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
        try
        {
            for (int y = 0; y < h; y++)
            {
                var src = rgba.AsSpan(y * w * 4, w * 4);
                var dst = new Span<byte>((byte*)data.Scan0 + (long)y * data.Stride, w * 4);
                for (int i = 0; i < src.Length; i += 4)
                {
                    dst[i] = src[i + 2];
                    dst[i + 1] = src[i + 1];
                    dst[i + 2] = src[i];
                    dst[i + 3] = src[i + 3];
                }
            }
        }
        finally
        {
            bmp.UnlockBits(data);
        }
        return bmp;
    }
}
