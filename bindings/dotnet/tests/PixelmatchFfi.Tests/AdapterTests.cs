using System.Drawing;
using System.Runtime.Versioning;
using PixelmatchFfi.SkiaSharp;
using PixelmatchFfi.SystemDrawing;
using SkiaSharp;
using StbImageSharp;

namespace PixelmatchFfi.Tests;

/// <summary>System.Drawing は .NET 7 以降 Windows 以外で例外になるため、Windows でのみ実行する。</summary>
public sealed class WindowsFactAttribute : FactAttribute
{
    public WindowsFactAttribute()
    {
        if (!OperatingSystem.IsWindows()) Skip = "System.Drawing is Windows only";
    }
}

public class AdapterTests
{
    private static readonly string Fixtures = Path.GetFullPath(Path.Combine(
        AppContext.BaseDirectory, "../../../../../../../vendor/pixelmatch-cpp/test/fixtures"));

    private static string FixturePath(string name) => Path.Combine(Fixtures, name + ".png");

    private static byte[] ExpectedRgba(string name)
    {
        using var s = File.OpenRead(FixturePath(name));
        return ImageResult.FromStream(s, ColorComponents.RedGreenBlueAlpha).Data;
    }

    private static readonly PixelmatchOptions T005 = new() { Threshold = 0.05 };

    [Fact]
    public void SkiaDecodedBitmapsMatchFixture()
    {
        // Decode の既定形式はプラットフォーム依存（多くは Bgra8888/Premul）なので変換経路も検証される
        using var a = SKBitmap.Decode(FixturePath("1a"));
        using var b = SKBitmap.Decode(FixturePath("1b"));
        using var r = SkiaPixelmatch.Compare(a, b, T005, createDiff: true);

        Assert.Equal(152ul, r.Mismatch);
        Assert.NotNull(r.Diff);
        Assert.Equal(SKColorType.Rgba8888, r.Diff.ColorType);
        Assert.Equal(ExpectedRgba("1diff"), r.Diff.Bytes);
    }

    [Theory]
    [InlineData(SKColorType.Rgba8888, SKAlphaType.Unpremul)]
    [InlineData(SKColorType.Bgra8888, SKAlphaType.Premul)]
    [InlineData(SKColorType.Bgra8888, SKAlphaType.Unpremul)]
    public void SkiaConvertsPixelFormats(SKColorType colorType, SKAlphaType alphaType)
    {
        using var a = DecodeAs("1a", colorType, alphaType);
        using var b = DecodeAs("1b", colorType, alphaType);
        Assert.Equal((colorType, alphaType), (a.ColorType, a.AlphaType));

        using var r = SkiaPixelmatch.Compare(a, b, T005);
        Assert.Equal(152ul, r.Mismatch);
        Assert.Null(r.Diff);
    }

    private static SKBitmap DecodeAs(string name, SKColorType colorType, SKAlphaType alphaType)
    {
        using var src = SKBitmap.Decode(FixturePath(name));
        var dst = new SKBitmap(new SKImageInfo(src.Width, src.Height, colorType, alphaType));
        using var pixmap = src.PeekPixels();
        Assert.True(pixmap.ReadPixels(dst.Info, dst.GetPixels(), dst.RowBytes));
        return dst;
    }

    [Fact]
    public void SkiaSizeMismatch()
    {
        using var a = new SKBitmap(2, 2);
        using var b = new SKBitmap(2, 3);
        Assert.Throws<ArgumentException>(() => SkiaPixelmatch.Compare(a, b));
    }

    [WindowsFact]
    [SupportedOSPlatform("windows")]
    public void DrawingMatchesFixture()
    {
        using var a = new Bitmap(FixturePath("1a"));
        using var b = new Bitmap(FixturePath("1b"));
        using var r = DrawingPixelmatch.Compare(a, b, T005, createDiff: true);
        Assert.Equal(152ul, r.Mismatch);
        Assert.NotNull(r.Diff);

        // diff を RGBA に戻して期待画像と比較する
        var expected = ExpectedRgba("1diff");
        for (int y = 0; y < r.Diff.Height; y++)
        {
            for (int x = 0; x < r.Diff.Width; x++)
            {
                var c = r.Diff.GetPixel(x, y);
                int i = (y * r.Diff.Width + x) * 4;
                Assert.Equal((expected[i], expected[i + 1], expected[i + 2], expected[i + 3]), (c.R, c.G, c.B, c.A));
            }
        }
    }
}
