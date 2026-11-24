//! [mapbox/pixelmatch-cpp](https://github.com/mapbox/pixelmatch-cpp) の安全な Rust ラッパー。
//!
//! C++ 実装はポインタを無検証で読み書きするため、このクレートで寸法・stride・
//! バッファ長をすべて検証してから呼び出す。比較ロジック自体は C++ 版
//! （= JS 版 pixelmatch 8.x とビット一致）をそのまま使う。

use std::fmt;

/// diff 画像の描画色 (RGB)。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Color {
    pub r: u8,
    pub g: u8,
    pub b: u8,
}

impl Color {
    pub const fn new(r: u8, g: u8, b: u8) -> Self {
        Self { r, g, b }
    }

    const fn to_array(self) -> [u8; 3] {
        [self.r, self.g, self.b]
    }
}

/// RGBA8 画像への参照。
#[derive(Debug, Clone, Copy)]
pub struct Image<'a> {
    data: &'a [u8],
    width: usize,
    height: usize,
    stride: usize,
}

impl<'a> Image<'a> {
    /// 行間に詰め物のない (`stride == width * 4`) 画像。
    pub fn new(data: &'a [u8], width: usize, height: usize) -> Result<Self, Error> {
        let stride = width.checked_mul(4).ok_or(Error::SizeOverflow)?;
        Self::with_stride(data, width, height, stride)
    }

    /// 行ごとに `stride` バイト（`width * 4` 以上）で並ぶ画像。
    pub fn with_stride(
        data: &'a [u8],
        width: usize,
        height: usize,
        stride: usize,
    ) -> Result<Self, Error> {
        let row = width.checked_mul(4).ok_or(Error::SizeOverflow)?;
        if stride < row {
            return Err(Error::InvalidStride { stride, min: row });
        }
        let required = required_len(row, height, stride)?;
        if data.len() < required {
            return Err(Error::BufferTooSmall {
                buffer: BufferKind::Image,
                len: data.len(),
                required,
            });
        }
        Ok(Self {
            data,
            width,
            height,
            stride,
        })
    }

    pub fn width(&self) -> usize {
        self.width
    }

    pub fn height(&self) -> usize {
        self.height
    }

    pub fn stride(&self) -> usize {
        self.stride
    }
}

/// 最終行は stride 分の詰め物を持たなくてよい（JS/C++ 版と同じ解釈）。
fn required_len(row: usize, height: usize, stride: usize) -> Result<usize, Error> {
    if height == 0 {
        return Ok(0);
    }
    stride
        .checked_mul(height - 1)
        .and_then(|n| n.checked_add(row))
        .ok_or(Error::SizeOverflow)
}

/// 比較オプション。既定値は pixelmatch 本家と同じ。
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Options<'a> {
    /// 一致とみなす色差の上限 (0〜1)。小さいほど敏感。
    pub threshold: f64,
    /// `true` ならアンチエイリアス検出を無効化し、AA ピクセルも差分として数える。
    pub include_aa: bool,
    /// diff 出力で変化のないピクセルに重ねる元画像の不透明度。
    pub alpha: f64,
    pub aa_color: Color,
    pub diff_color: Color,
    /// img2 側が暗くなった差分の色。`None` なら `diff_color`。
    pub diff_color_alt: Option<Color>,
    /// 透明背景に差分だけを描く。
    pub diff_mask: bool,
    /// 半透明ピクセルを市松模様に合成して比較する（`false` なら白）。
    pub checkerboard: bool,
    /// 1 ピクセル 1 バイト (`width * height`)。非 0 のピクセルは比較から除外。
    pub ignore_mask: Option<&'a [u8]>,
    /// 非 0 なら N×N 窓内の差分数の最大値を返す。0 なら総数。
    pub window_size: usize,
}

impl Default for Options<'_> {
    fn default() -> Self {
        Self {
            threshold: 0.1,
            include_aa: false,
            alpha: 0.1,
            aa_color: Color::new(255, 255, 0),
            diff_color: Color::new(255, 0, 0),
            diff_color_alt: None,
            diff_mask: false,
            checkerboard: true,
            ignore_mask: None,
            window_size: 0,
        }
    }
}

/// エラーの対象となったバッファ。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BufferKind {
    Image,
    Output,
    IgnoreMask,
}

#[derive(Debug, Clone, PartialEq)]
#[non_exhaustive]
pub enum Error {
    DimensionMismatch {
        img1: (usize, usize),
        img2: (usize, usize),
    },
    InvalidStride {
        stride: usize,
        min: usize,
    },
    BufferTooSmall {
        buffer: BufferKind,
        len: usize,
        required: usize,
    },
    InvalidOption(&'static str),
    SizeOverflow,
    OutOfMemory,
    /// C++ 側で想定外の例外が発生した。
    Internal,
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::DimensionMismatch { img1, img2 } => write!(
                f,
                "image sizes do not match: {}x{} vs {}x{}",
                img1.0, img1.1, img2.0, img2.1
            ),
            Error::InvalidStride { stride, min } => {
                write!(f, "stride {stride} is smaller than width * 4 ({min})")
            }
            Error::BufferTooSmall {
                buffer,
                len,
                required,
            } => write!(
                f,
                "{buffer:?} buffer too small: {len} bytes, need {required}"
            ),
            Error::InvalidOption(msg) => write!(f, "invalid option: {msg}"),
            Error::SizeOverflow => f.write_str("image size overflows usize"),
            Error::OutOfMemory => f.write_str("out of memory"),
            Error::Internal => f.write_str("internal error in pixelmatch"),
        }
    }
}

impl std::error::Error for Error {}

/// 2 枚の RGBA 画像を比較し、差分ピクセル数（`window_size` 指定時は窓内の最大数）を返す。
///
/// `output` を渡すと `width * height * 4` バイトの詰めた RGBA で diff 画像を書き込む。
pub fn pixelmatch(
    img1: &Image<'_>,
    img2: &Image<'_>,
    output: Option<&mut [u8]>,
    options: &Options<'_>,
) -> Result<u64, Error> {
    if (img1.width, img1.height) != (img2.width, img2.height) {
        return Err(Error::DimensionMismatch {
            img1: (img1.width, img1.height),
            img2: (img2.width, img2.height),
        });
    }
    // NaN は比較が常に偽になり C++ 側で黙って全一致扱いになるため、明示的に弾く
    if !options.threshold.is_finite() {
        return Err(Error::InvalidOption("threshold must be finite"));
    }
    if !options.alpha.is_finite() {
        return Err(Error::InvalidOption("alpha must be finite"));
    }

    let (width, height) = (img1.width, img1.height);
    let pixels = width.checked_mul(height).ok_or(Error::SizeOverflow)?;
    let out_len = pixels.checked_mul(4).ok_or(Error::SizeOverflow)?;

    let output_ptr = match output {
        Some(out) if out.len() < out_len => {
            return Err(Error::BufferTooSmall {
                buffer: BufferKind::Output,
                len: out.len(),
                required: out_len,
            });
        }
        Some(out) => out.as_mut_ptr(),
        None => std::ptr::null_mut(),
    };
    let ignore_mask_ptr = match options.ignore_mask {
        Some(mask) if mask.len() < pixels => {
            return Err(Error::BufferTooSmall {
                buffer: BufferKind::IgnoreMask,
                len: mask.len(),
                required: pixels,
            });
        }
        Some(mask) => mask.as_ptr(),
        None => std::ptr::null(),
    };

    // 空画像では C++ 側の窓計算が (n - 1) でアンダーフローしうるため、呼ばずに確定させる
    if pixels == 0 {
        return Ok(0);
    }

    let raw = pixelmatch_sys::pmx_options {
        threshold: options.threshold,
        alpha: options.alpha,
        aa_color: options.aa_color.to_array(),
        diff_color: options.diff_color.to_array(),
        diff_color_alt: options
            .diff_color_alt
            .unwrap_or(options.diff_color)
            .to_array(),
        has_diff_color_alt: options.diff_color_alt.is_some() as u8,
        include_aa: options.include_aa as u8,
        diff_mask: options.diff_mask as u8,
        checkerboard: options.checkerboard as u8,
        ignore_mask: ignore_mask_ptr,
        window_size: options.window_size,
    };

    let mut result = 0u64;
    // SAFETY: 各バッファ長は上で検証済み。output は &mut 由来なので入力とは重ならない。
    let status = unsafe {
        pixelmatch_sys::pmx_pixelmatch(
            img1.data.as_ptr(),
            img1.stride,
            img2.data.as_ptr(),
            img2.stride,
            width,
            height,
            output_ptr,
            &raw,
            &mut result,
        )
    };
    match status {
        pixelmatch_sys::PMX_OK => Ok(result),
        pixelmatch_sys::PMX_OUT_OF_MEMORY => Err(Error::OutOfMemory),
        _ => Err(Error::Internal),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_small_buffers() {
        let buf = [0u8; 15];
        assert!(matches!(
            Image::new(&buf, 2, 2),
            Err(Error::BufferTooSmall { required: 16, .. })
        ));
    }

    #[test]
    fn last_row_needs_no_padding() {
        // stride 12 / width 2 / height 2 → 12 + 8 = 20 バイトで足りる
        let buf = [0u8; 20];
        assert!(Image::with_stride(&buf, 2, 2, 12).is_ok());
        assert!(matches!(
            Image::with_stride(&buf, 2, 2, 7),
            Err(Error::InvalidStride { .. })
        ));
    }

    #[test]
    fn rejects_dimension_mismatch_and_nan() {
        let a = [0u8; 16];
        let i1 = Image::new(&a, 2, 2).unwrap();
        let i2 = Image::new(&a, 4, 1).unwrap();
        assert!(matches!(
            pixelmatch(&i1, &i2, None, &Options::default()),
            Err(Error::DimensionMismatch { .. })
        ));
        let opts = Options {
            threshold: f64::NAN,
            ..Default::default()
        };
        assert!(matches!(
            pixelmatch(&i1, &i1, None, &opts),
            Err(Error::InvalidOption(_))
        ));
    }

    #[test]
    fn empty_image_is_zero() {
        let i = Image::new(&[], 0, 5).unwrap();
        assert_eq!(pixelmatch(&i, &i, None, &Options::default()), Ok(0));
    }

    #[test]
    fn single_pixel_diff() {
        let a = [0, 0, 0, 255];
        let b = [255, 255, 255, 255];
        let (i1, i2) = (Image::new(&a, 1, 1).unwrap(), Image::new(&b, 1, 1).unwrap());
        let mut out = [0u8; 4];
        assert_eq!(
            pixelmatch(&i1, &i2, Some(&mut out), &Options::default()),
            Ok(1)
        );
        assert_eq!(out, [255, 0, 0, 255]);
    }
}
