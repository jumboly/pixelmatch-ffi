using System;

namespace PixelmatchFfi;

/// <summary>画像型アダプターの戻り値。Dispose すると diff 画像も破棄する。</summary>
/// <typeparam name="TImage">diff 画像の型。</typeparam>
/// <param name="Mismatch">差分ピクセル数（WindowSize 指定時は窓内の最大数）。</param>
/// <param name="Diff">diff 画像。要求しなかった場合は <c>null</c>。</param>
public sealed record ImageCompareResult<TImage>(ulong Mismatch, TImage? Diff) : IDisposable
    where TImage : class
{
    /// <inheritdoc />
    public void Dispose() => (Diff as IDisposable)?.Dispose();
}
