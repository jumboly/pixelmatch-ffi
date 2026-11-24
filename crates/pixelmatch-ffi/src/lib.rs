//! pixelmatch の公開 C ABI。
//!
//! 設計方針:
//! - メモリは常に呼び出し側が確保する（解放関数や所有権の受け渡しを不要にし、
//!   各言語のメモリ管理と衝突させないため）
//! - 失敗は戻り値のステータスコードで返す（例外機構は言語ごとに異なるため）
//! - `PmOptions` は先頭の `struct_size` で版管理し、将来フィールドを末尾に追加しても
//!   古いバイナリとの互換を保てるようにする

use std::ffi::{c_char, c_int};
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::{ptr, slice};

use pixelmatch::{BufferKind, Color, Error, Image, Options};

/// ABI の互換性が壊れる変更をしたときだけ増やす。
pub const PM_ABI_VERSION: u32 = 1;

/// 関数の戻り値。
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PmStatus {
    Ok = 0,
    NullPointer = 1,
    InvalidArgument = 2,
    InvalidStride = 3,
    ImageTooSmall = 4,
    OutputTooSmall = 5,
    IgnoreMaskTooSmall = 6,
    SizeOverflow = 7,
    /// output が入力画像と重なっている（C++ 実装は入力を読みながら出力に書くため結果が壊れる）
    BuffersOverlap = 8,
    OutOfMemory = 9,
    /// 想定外の内部エラー（Rust の panic / C++ の例外）
    Internal = 99,
}

/// diff 画像の描画色 (RGB)。
#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct PmColor {
    pub r: u8,
    pub g: u8,
    pub b: u8,
}

/// RGBA8 画像。`stride` が 0 なら `width * 4`（行間の詰め物なし）とみなす。
#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct PmImage {
    pub data: *const u8,
    /// `data` の読み取り可能なバイト数
    pub len: usize,
    pub stride: usize,
}

/// 比較オプション。必ず `pm_options_init` で初期化してから値を変更すること。
#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct PmOptions {
    /// `sizeof(PmOptions)`。`pm_options_init` が設定する。
    pub struct_size: u32,
    pub threshold: f64,
    pub alpha: f64,
    pub aa_color: PmColor,
    pub diff_color: PmColor,
    /// `has_diff_color_alt` が 0 のときは無視される
    pub diff_color_alt: PmColor,
    pub has_diff_color_alt: u8,
    pub include_aa: u8,
    pub diff_mask: u8,
    pub checkerboard: u8,
    /// 0 なら差分総数、N なら N×N 窓内の差分数の最大値を返す
    pub window_size: u64,
}

const OPTIONS_V1_SIZE: usize = size_of::<PmOptions>();

impl From<Color> for PmColor {
    fn from(c: Color) -> Self {
        Self {
            r: c.r,
            g: c.g,
            b: c.b,
        }
    }
}

impl From<PmColor> for Color {
    fn from(c: PmColor) -> Self {
        Color::new(c.r, c.g, c.b)
    }
}

impl From<&Error> for PmStatus {
    fn from(e: &Error) -> Self {
        match e {
            Error::DimensionMismatch { .. } | Error::InvalidOption(_) => PmStatus::InvalidArgument,
            Error::InvalidStride { .. } => PmStatus::InvalidStride,
            Error::BufferTooSmall { buffer, .. } => match buffer {
                BufferKind::Image => PmStatus::ImageTooSmall,
                BufferKind::Output => PmStatus::OutputTooSmall,
                BufferKind::IgnoreMask => PmStatus::IgnoreMaskTooSmall,
            },
            Error::SizeOverflow => PmStatus::SizeOverflow,
            Error::OutOfMemory => PmStatus::OutOfMemory,
            _ => PmStatus::Internal,
        }
    }
}

/// `PM_ABI_VERSION` を返す。ラッパーはロード時にこれを照合し、不一致なら使用を拒否すること。
#[unsafe(no_mangle)]
pub extern "C" fn pm_abi_version() -> u32 {
    PM_ABI_VERSION
}

/// ライブラリのバージョン文字列（静的領域、解放不要）。
#[unsafe(no_mangle)]
pub extern "C" fn pm_version() -> *const c_char {
    concat!(env!("CARGO_PKG_VERSION"), "\0").as_ptr().cast()
}

/// ステータスコードの英語メッセージ（静的領域、解放不要）。未知のコードでも NULL は返さない。
#[unsafe(no_mangle)]
pub extern "C" fn pm_status_message(status: c_int) -> *const c_char {
    let msg: &'static str = match status {
        0 => "ok\0",
        1 => "required pointer is null\0",
        2 => "invalid argument\0",
        3 => "stride is smaller than width * 4\0",
        4 => "image buffer is too small\0",
        5 => "output buffer is too small\0",
        6 => "ignore mask buffer is too small\0",
        7 => "image size overflows\0",
        8 => "output buffer overlaps an input image\0",
        9 => "out of memory\0",
        99 => "internal error\0",
        _ => "unknown status\0",
    };
    msg.as_ptr().cast()
}

/// `opts` を既定値で初期化し、`struct_size` を設定する。
///
/// # Safety
/// `opts` は NULL か、`PmOptions` を書き込める領域を指すこと。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn pm_options_init(opts: *mut PmOptions) -> PmStatus {
    if opts.is_null() {
        return PmStatus::NullPointer;
    }
    let d = Options::default();
    let value = PmOptions {
        struct_size: OPTIONS_V1_SIZE as u32,
        threshold: d.threshold,
        alpha: d.alpha,
        aa_color: d.aa_color.into(),
        diff_color: d.diff_color.into(),
        diff_color_alt: d.diff_color.into(),
        has_diff_color_alt: 0,
        include_aa: d.include_aa as u8,
        diff_mask: d.diff_mask as u8,
        checkerboard: d.checkerboard as u8,
        window_size: d.window_size as u64,
    };
    // SAFETY: 呼び出し側の契約により書き込み可能。未初期化領域でもよいよう write を使う
    unsafe { opts.write(value) };
    PmStatus::Ok
}

/// 2 枚の RGBA8 画像を比較する。
///
/// - `output`: NULL 可。非 NULL なら `width * height * 4` バイトの diff 画像を書き込む。
///   入力画像と重なってはならない。
/// - `ignore_mask`: NULL 可。`width * height` バイト、非 0 のピクセルを比較から除外。
/// - `opts`: NULL なら既定値。
/// - `out_count`: 差分ピクセル数（`window_size` 指定時は窓内最大数）の格納先。
///
/// # Safety
/// 各ポインタは対応する長さ分だけ有効であること。関数はスレッドセーフで状態を持たない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn pm_pixelmatch(
    img1: *const PmImage,
    img2: *const PmImage,
    width: u32,
    height: u32,
    output: *mut u8,
    output_len: usize,
    ignore_mask: *const u8,
    ignore_mask_len: usize,
    opts: *const PmOptions,
    out_count: *mut u64,
) -> PmStatus {
    // panic が extern "C" 境界を越えると abort するため、ステータスに変換して返す
    let r = catch_unwind(AssertUnwindSafe(|| unsafe {
        pixelmatch_impl(
            img1,
            img2,
            width,
            height,
            output,
            output_len,
            ignore_mask,
            ignore_mask_len,
            opts,
            out_count,
        )
    }));
    r.unwrap_or(PmStatus::Internal)
}

#[allow(clippy::too_many_arguments)]
unsafe fn pixelmatch_impl(
    img1: *const PmImage,
    img2: *const PmImage,
    width: u32,
    height: u32,
    output: *mut u8,
    output_len: usize,
    ignore_mask: *const u8,
    ignore_mask_len: usize,
    opts: *const PmOptions,
    out_count: *mut u64,
) -> PmStatus {
    if img1.is_null() || img2.is_null() || out_count.is_null() {
        return PmStatus::NullPointer;
    }
    let (img1, img2) = unsafe { (*img1, *img2) };
    let (w, h) = (width as usize, height as usize);

    let options = if opts.is_null() {
        Options::default()
    } else {
        // 将来の版で struct_size が大きくなっても、v1 で既知の先頭部分だけを読めば互換が保てる
        let size = unsafe { ptr::addr_of!((*opts).struct_size).read_unaligned() } as usize;
        if size < OPTIONS_V1_SIZE {
            return PmStatus::InvalidArgument;
        }
        let o = unsafe { opts.read_unaligned() };
        let window_size = match usize::try_from(o.window_size) {
            Ok(v) => v,
            Err(_) => return PmStatus::InvalidArgument,
        };
        Options {
            threshold: o.threshold,
            include_aa: o.include_aa != 0,
            alpha: o.alpha,
            aa_color: o.aa_color.into(),
            diff_color: o.diff_color.into(),
            diff_color_alt: (o.has_diff_color_alt != 0).then(|| o.diff_color_alt.into()),
            diff_mask: o.diff_mask != 0,
            checkerboard: o.checkerboard != 0,
            ignore_mask: None,
            window_size,
        }
    };

    let as_slice = |data: *const u8, len: usize| -> Option<&[u8]> {
        if len == 0 {
            Some(&[])
        } else if data.is_null() {
            None
        } else {
            // SAFETY: 呼び出し側の契約により len バイト読める
            Some(unsafe { slice::from_raw_parts(data, len) })
        }
    };

    let Some(d1) = as_slice(img1.data, img1.len) else {
        return PmStatus::NullPointer;
    };
    let Some(d2) = as_slice(img2.data, img2.len) else {
        return PmStatus::NullPointer;
    };
    let mask = if ignore_mask.is_null() {
        None
    } else {
        as_slice(ignore_mask, ignore_mask_len)
    };

    let make_image = |data, stride: usize| {
        if stride == 0 {
            Image::new(data, w, h)
        } else {
            Image::with_stride(data, w, h, stride)
        }
    };
    let i1 = match make_image(d1, img1.stride) {
        Ok(i) => i,
        Err(e) => return (&e).into(),
    };
    let i2 = match make_image(d2, img2.stride) {
        Ok(i) => i,
        Err(e) => return (&e).into(),
    };

    let out = if output.is_null() {
        None
    } else {
        let ranges_overlap = |a: *const u8, alen: usize, b: *const u8, blen: usize| {
            let (a, b) = (a as usize, b as usize);
            a < b.saturating_add(blen) && b < a.saturating_add(alen)
        };
        // Rust の &mut [u8] は他の参照と重ならない前提のため、slice 化する前に重なりを検出する
        if ranges_overlap(output, output_len, d1.as_ptr(), d1.len())
            || ranges_overlap(output, output_len, d2.as_ptr(), d2.len())
        {
            return PmStatus::BuffersOverlap;
        }
        // SAFETY: 呼び出し側の契約により output_len バイト書ける。入力とは重ならないことを確認済み
        Some(unsafe { slice::from_raw_parts_mut(output, output_len) })
    };

    let options = Options {
        ignore_mask: mask,
        ..options
    };
    match pixelmatch::pixelmatch(&i1, &i2, out, &options) {
        Ok(n) => {
            unsafe { out_count.write(n) };
            PmStatus::Ok
        }
        Err(e) => (&e).into(),
    }
}
