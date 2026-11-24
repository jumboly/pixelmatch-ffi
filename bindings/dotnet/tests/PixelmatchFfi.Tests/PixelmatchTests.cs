using StbImageSharp;

namespace PixelmatchFfi.Tests;

// 上流 pixelmatch-cpp の fixtures で、.NET → C ABI の受け渡しに欠落がないことを検証する
public class PixelmatchTests
{
    private static readonly string Fixtures = Path.GetFullPath(Path.Combine(
        AppContext.BaseDirectory, "../../../../../../../vendor/pixelmatch-cpp/test/fixtures"));

    private static (byte[] Data, int W, int H) Load(string name)
    {
        using var s = File.OpenRead(Path.Combine(Fixtures, name + ".png"));
        var img = ImageResult.FromStream(s, ColorComponents.RedGreenBlueAlpha);
        return (img.Data, img.Width, img.Height);
    }

    private static readonly PixelmatchOptions T005 = new() { Threshold = 0.05 };

    public static TheoryData<string, string, string, PixelmatchOptions, ulong, bool> Cases => new()
    {
        { "1a", "1b", "1diff", T005, 152, false },
        { "1a", "1b", "1diffdefaultthreshold", PixelmatchOptions.Default, 121, false },
        { "1a", "1b", "1diffmask", T005 with { DiffMask = true }, 152, false },
        { "1a", "1a", "1emptydiffmask", new() { Threshold = 0, DiffMask = true }, 0, false },
        { "2a", "2b", "2diff", T005 with { Alpha = 0.5, AaColor = new(0, 192, 0), DiffColor = new(255, 0, 255) }, 12821, false },
        { "3a", "3b", "3diff", T005, 220, false },
        { "4a", "4b", "4diff", T005, 36563, false },
        { "5a", "5b", "5diff", T005, 0, false },
        { "6a", "6b", "6diff", T005, 51, false },
        { "6a", "6a", "6empty", new() { Threshold = 0 }, 0, false },
        { "7a", "7b", "7diff", new() { DiffColorAlt = new(0, 255, 0) }, 2440, false },
        { "8a", "5b", "8diff", T005, 32896, false },
        { "9a", "9b", "9diff", T005, 12422, true },
        { "10a", "10b", "10diff", T005, 0, true },
    };

    [Theory]
    [MemberData(nameof(Cases))]
    public void MatchesUpstreamFixtures(string a, string b, string diff, PixelmatchOptions options, ulong expected, bool ignoreHalf)
    {
        var (d1, w, h) = Load(a);
        var (d2, _, _) = Load(b);
        byte[] mask = ignoreHalf
            ? Enumerable.Range(0, w * h).Select(i => (byte)(i <= w * h / 2 ? 1 : 0)).ToArray()
            : [];

        var output = new byte[w * h * 4];
        Assert.Equal(expected, Pixelmatch.Compare(d1, d2, w, h, output, options, mask));
        Assert.Equal(expected, Pixelmatch.Compare(d1, d2, w, h, default, options, mask));
        Assert.Equal(Load(diff).Data, output);
    }

    [Fact]
    public void StrideMatchesPacked()
    {
        var (d1, w, h) = Load("1a");
        var (d2, _, _) = Load("1b");
        const int pad = 12;
        byte[] Pad(byte[] d) => d.Chunk(w * 4).SelectMany(r => r.Concat(Enumerable.Repeat((byte)0xAB, pad))).ToArray();
        Assert.Equal(
            Pixelmatch.Compare(d1, d2, w, h, options: T005),
            Pixelmatch.Compare(Pad(d1), w * 4 + pad, Pad(d2), w * 4 + pad, w, h, options: T005));
    }

    [Fact]
    public void LayoutMatchesNative()
    {
        var (nativeSize, managedSize) = Pixelmatch.OptionsLayout();
        Assert.Equal(48u, nativeSize);
        Assert.Equal((int)nativeSize, managedSize);
        Assert.Equal("0.1.0", Pixelmatch.NativeVersion);
    }

    [Fact]
    public void Errors()
    {
        Assert.Throws<ArgumentException>(() => Pixelmatch.Compare(new byte[7], new byte[8], 1, 2));
        Assert.Throws<ArgumentException>(() => Pixelmatch.Compare(new byte[8], new byte[8], 1, 2, new byte[7]));
        Assert.Throws<ArgumentOutOfRangeException>(() => Pixelmatch.Compare(new byte[8], new byte[8], -1, 2));
    }

    [Fact]
    public void Parallel()
    {
        var (d1, w, h) = Load("4a");
        var (d2, _, _) = Load("4b");
        var results = Enumerable.Range(0, 8).AsParallel().Select(_ => Pixelmatch.Compare(d1, d2, w, h, options: T005)).ToArray();
        Assert.All(results, r => Assert.Equal(36563ul, r));
    }
}
