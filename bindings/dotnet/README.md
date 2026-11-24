# PixelmatchFfi (.NET)

[mapbox/pixelmatch-cpp](https://github.com/mapbox/pixelmatch-cpp) をネイティブライブラリ経由で呼ぶ .NET ラッパー。

```csharp
using PixelmatchFfi;

byte[] diff = new byte[width * height * 4];
ulong n = Pixelmatch.Compare(img1Rgba, img2Rgba, width, height, diff,
    new PixelmatchOptions { Threshold = 0.1 });
```

入力は RGBA8 の生バイト列。PNG 等のデコードは利用側のライブラリで行う。
