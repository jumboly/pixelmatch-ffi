using System;
using System.Runtime.InteropServices;

namespace PixelmatchFfi;

/// <summary>diff 画像の描画色 (RGB)。</summary>
public readonly record struct Rgb(byte R, byte G, byte B);

/// <summary>比較オプション。既定値は pixelmatch 本家と同じ。</summary>
public sealed record PixelmatchOptions
{
    /// <summary>既定値のインスタンス。</summary>
    public static PixelmatchOptions Default { get; } = new();

    /// <summary>一致とみなす色差の上限 (0〜1)。小さいほど敏感。</summary>
    public double Threshold { get; init; } = 0.1;

    /// <summary><c>true</c> ならアンチエイリアス検出を無効化し、AA ピクセルも差分として数える。</summary>
    public bool IncludeAA { get; init; }

    /// <summary>diff 出力で変化のないピクセルに重ねる元画像の不透明度。</summary>
    public double Alpha { get; init; } = 0.1;

    /// <summary>アンチエイリアスと判定したピクセルの色。</summary>
    public Rgb AaColor { get; init; } = new(255, 255, 0);

    /// <summary>差分ピクセルの色。</summary>
    public Rgb DiffColor { get; init; } = new(255, 0, 0);

    /// <summary>img2 側が暗くなった差分の色。<c>null</c> なら <see cref="DiffColor"/>。</summary>
    public Rgb? DiffColorAlt { get; init; }

    /// <summary>透明背景に差分だけを描く。</summary>
    public bool DiffMask { get; init; }

    /// <summary>半透明ピクセルを市松模様に合成して比較する（<c>false</c> なら白）。</summary>
    public bool Checkerboard { get; init; } = true;

    /// <summary>0 以外なら N×N 窓内の差分数の最大値を返す。0 なら総数。</summary>
    public int WindowSize { get; init; }
}

/// <summary>ネイティブ側の想定外エラー。</summary>
public sealed class PixelmatchException(int status, string message) : Exception(message)
{
    /// <summary>C ABI の PmStatus 値。</summary>
    public int Status { get; } = status;
}

/// <summary>mapbox/pixelmatch (C++ 版) によるピクセル単位の画像比較。スレッドセーフ。</summary>
public static class Pixelmatch
{
    private const int StatusOutOfMemory = 9;
    private const int StatusInternal = 99;

    /// <summary>ネイティブライブラリのバージョン。</summary>
    public static string NativeVersion
    {
        get
        {
            Native.EnsureCompatible();
            return Marshal.PtrToStringUTF8(Native.pm_version()) ?? "";
        }
    }

    /// <summary>行間に詰め物のない RGBA8 画像 2 枚を比較し、差分ピクセル数を返す。</summary>
    /// <param name="img1">比較元 (<c>width * height * 4</c> バイト)。</param>
    /// <param name="img2">比較先。</param>
    /// <param name="width">幅 (px)。</param>
    /// <param name="height">高さ (px)。</param>
    /// <param name="output">空でなければ <c>width * height * 4</c> バイトの diff 画像を書き込む。</param>
    /// <param name="options">比較オプション。<c>null</c> なら既定値。</param>
    /// <param name="ignoreMask">空でなければ <c>width * height</c> バイト。非 0 のピクセルを比較しない。</param>
    public static ulong Compare(
        ReadOnlySpan<byte> img1,
        ReadOnlySpan<byte> img2,
        int width,
        int height,
        Span<byte> output = default,
        PixelmatchOptions? options = null,
        ReadOnlySpan<byte> ignoreMask = default) =>
        Compare(img1, 0, img2, 0, width, height, output, options, ignoreMask);

    /// <summary>行ごとに stride バイトで並ぶ RGBA8 画像 2 枚を比較する。stride が 0 なら <c>width * 4</c>。</summary>
    /// <param name="img1">比較元。</param>
    /// <param name="stride1">img1 の行のバイト数。</param>
    /// <param name="img2">比較先。</param>
    /// <param name="stride2">img2 の行のバイト数。</param>
    /// <param name="width">幅 (px)。</param>
    /// <param name="height">高さ (px)。</param>
    /// <param name="output">空でなければ <c>width * height * 4</c> バイト（詰め物なし）の diff 画像を書き込む。</param>
    /// <param name="options">比較オプション。<c>null</c> なら既定値。</param>
    /// <param name="ignoreMask">空でなければ <c>width * height</c> バイト。非 0 のピクセルを比較しない。</param>
    public static unsafe ulong Compare(
        ReadOnlySpan<byte> img1,
        int stride1,
        ReadOnlySpan<byte> img2,
        int stride2,
        int width,
        int height,
        Span<byte> output = default,
        PixelmatchOptions? options = null,
        ReadOnlySpan<byte> ignoreMask = default)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(width);
        ArgumentOutOfRangeException.ThrowIfNegative(height);
        ArgumentOutOfRangeException.ThrowIfNegative(stride1);
        ArgumentOutOfRangeException.ThrowIfNegative(stride2);
        options ??= PixelmatchOptions.Default;
        ArgumentOutOfRangeException.ThrowIfNegative(options.WindowSize, nameof(options.WindowSize));
        Native.EnsureCompatible();

        PmOptions o;
        Native.pm_options_init(&o);
        o.Threshold = options.Threshold;
        o.Alpha = options.Alpha;
        o.IncludeAA = options.IncludeAA ? (byte)1 : (byte)0;
        o.AaColor = options.AaColor;
        o.DiffColor = options.DiffColor;
        if (options.DiffColorAlt is { } alt)
        {
            o.DiffColorAlt = alt;
            o.HasDiffColorAlt = 1;
        }
        o.DiffMask = options.DiffMask ? (byte)1 : (byte)0;
        o.Checkerboard = options.Checkerboard ? (byte)1 : (byte)0;
        o.WindowSize = (ulong)options.WindowSize;

        ulong count;
        int status;
        // 空の Span を fixed すると null になり、C ABI 側で「指定なし」と解釈される
        fixed (byte* p1 = img1)
        fixed (byte* p2 = img2)
        fixed (byte* pOut = output)
        fixed (byte* pMask = ignoreMask)
        {
            var i1 = new PmImage { Data = p1, Len = (nuint)img1.Length, Stride = (nuint)stride1 };
            var i2 = new PmImage { Data = p2, Len = (nuint)img2.Length, Stride = (nuint)stride2 };
            status = Native.pm_pixelmatch(
                &i1, &i2, (uint)width, (uint)height,
                pOut, (nuint)output.Length,
                pMask, (nuint)ignoreMask.Length,
                &o, &count);
        }

        return status switch
        {
            0 => count,
            StatusOutOfMemory => throw new OutOfMemoryException("pixelmatch: out of memory"),
            StatusInternal => throw new PixelmatchException(status, Native.StatusMessage(status)),
            _ => throw new ArgumentException(Native.StatusMessage(status)),
        };
    }

    // テストから構造体レイアウトを検証するための内部 API
    internal static unsafe (uint NativeSize, int ManagedSize) OptionsLayout()
    {
        PmOptions o;
        Native.pm_options_init(&o);
        return (o.StructSize, sizeof(PmOptions));
    }
}
