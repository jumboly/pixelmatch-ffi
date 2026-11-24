# pixelmatch-ffi (Python)

[mapbox/pixelmatch-cpp](https://github.com/mapbox/pixelmatch-cpp) をネイティブライブラリ経由で呼ぶ Python ラッパー。

```python
from PIL import Image
from pixelmatch_ffi import pixelmatch

a = Image.open("a.png").convert("RGBA")
b = Image.open("b.png").convert("RGBA")
diff = bytearray(a.width * a.height * 4)
n = pixelmatch(a.tobytes(), b.tobytes(), a.width, a.height, diff, threshold=0.1)
Image.frombytes("RGBA", a.size, bytes(diff)).save("diff.png")
```
