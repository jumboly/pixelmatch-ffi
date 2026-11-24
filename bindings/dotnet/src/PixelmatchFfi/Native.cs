using System;
using System.Runtime.InteropServices;

namespace PixelmatchFfi;

// crates/pixelmatch-ffi/include/pixelmatch_ffi.h と 1:1 で対応させること。
// Sequential レイアウトは C の構造体レイアウト規則と一致するため、ポインタでそのまま渡せる。

[StructLayout(LayoutKind.Sequential)]
internal struct PmColor
{
    public byte R, G, B;

    public static implicit operator PmColor(Rgb c) => new() { R = c.R, G = c.G, B = c.B };
}

[StructLayout(LayoutKind.Sequential)]
internal unsafe struct PmImage
{
    public byte* Data;
    public nuint Len;
    public nuint Stride;
}

[StructLayout(LayoutKind.Sequential)]
internal struct PmOptions
{
    public uint StructSize;
    public double Threshold;
    public double Alpha;
    public PmColor AaColor;
    public PmColor DiffColor;
    public PmColor DiffColorAlt;
    public byte HasDiffColorAlt;
    public byte IncludeAA;
    public byte DiffMask;
    public byte Checkerboard;
    public ulong WindowSize;
}

internal static unsafe partial class Native
{
    private const string Lib = "pixelmatch_ffi";
    internal const uint AbiVersion = 1;

    [LibraryImport(Lib)]
    internal static partial uint pm_abi_version();

    [LibraryImport(Lib)]
    internal static partial nint pm_version();

    [LibraryImport(Lib)]
    internal static partial nint pm_status_message(int status);

    [LibraryImport(Lib)]
    internal static partial int pm_options_init(PmOptions* opts);

    [LibraryImport(Lib)]
    internal static partial int pm_pixelmatch(
        PmImage* img1,
        PmImage* img2,
        uint width,
        uint height,
        byte* output,
        nuint outputLen,
        byte* ignoreMask,
        nuint ignoreMaskLen,
        PmOptions* opts,
        ulong* outCount);

    private static readonly Lazy<bool> s_checked = new(() =>
    {
        // ラッパーとネイティブの版ずれは構造体の読み違いによる無言のメモリ破壊につながるため、最初の呼び出しで拒否する
        uint abi = pm_abi_version();
        if (abi != AbiVersion)
        {
            throw new InvalidOperationException(
                $"pixelmatch_ffi ABI mismatch: native {abi}, managed {AbiVersion}");
        }
        return true;
    });

    internal static void EnsureCompatible() => _ = s_checked.Value;

    internal static string StatusMessage(int status) =>
        Marshal.PtrToStringUTF8(pm_status_message(status)) ?? "unknown status";
}
