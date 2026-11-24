//! C ABI 層固有の検証（NULL / 重なり / struct_size による版管理）。比較ロジック自体は pixelmatch クレート側で検証済み。

use std::ffi::CStr;
use std::mem::MaybeUninit;
use std::ptr;

use pixelmatch_ffi::*;

fn opts() -> PmOptions {
    let mut o = MaybeUninit::uninit();
    assert_eq!(unsafe { pm_options_init(o.as_mut_ptr()) }, PmStatus::Ok);
    unsafe { o.assume_init() }
}

fn image(d: &[u8]) -> PmImage {
    PmImage {
        data: d.as_ptr(),
        len: d.len(),
        stride: 0,
    }
}

fn call(
    a: &PmImage,
    b: &PmImage,
    out: *mut u8,
    out_len: usize,
    o: *const PmOptions,
) -> (PmStatus, u64) {
    let mut n = 0;
    let s = unsafe { pm_pixelmatch(a, b, 1, 2, out, out_len, ptr::null(), 0, o, &mut n) };
    (s, n)
}

#[test]
fn layout_is_stable() {
    // ラッパー側 (ctypes / .NET) の構造体定義と一致させる基準値。変わったら ABI 破壊
    assert_eq!(size_of::<PmOptions>(), 48);
    assert_eq!(size_of::<PmImage>(), 3 * size_of::<usize>());
    assert_eq!(opts().struct_size, 48);
    assert_eq!(pm_abi_version(), PM_ABI_VERSION);
    assert!(!unsafe { CStr::from_ptr(pm_version()) }.is_empty());
}

#[test]
fn basic_and_errors() {
    let a = [0, 0, 0, 255, 0, 0, 0, 255];
    let b = [255, 255, 255, 255, 0, 0, 0, 255];
    let (ia, ib) = (image(&a), image(&b));
    let o = opts();

    assert_eq!(call(&ia, &ib, ptr::null_mut(), 0, &o), (PmStatus::Ok, 1));
    assert_eq!(
        call(&ia, &ib, ptr::null_mut(), 0, ptr::null()),
        (PmStatus::Ok, 1)
    );

    let mut out = [0u8; 8];
    assert_eq!(call(&ia, &ib, out.as_mut_ptr(), 8, &o), (PmStatus::Ok, 1));
    assert_eq!(
        call(&ia, &ib, out.as_mut_ptr(), 7, &o).0,
        PmStatus::OutputTooSmall
    );

    let short = image(&a[..7]);
    assert_eq!(
        call(&short, &ib, ptr::null_mut(), 0, &o).0,
        PmStatus::ImageTooSmall
    );

    let mut n = 0;
    assert_eq!(
        unsafe {
            pm_pixelmatch(
                ptr::null(),
                &ib,
                1,
                2,
                ptr::null_mut(),
                0,
                ptr::null(),
                0,
                &o,
                &mut n,
            )
        },
        PmStatus::NullPointer
    );

    let old = PmOptions {
        struct_size: 8,
        ..o
    };
    assert_eq!(
        call(&ia, &ib, ptr::null_mut(), 0, &old).0,
        PmStatus::InvalidArgument
    );
}

#[test]
fn rejects_overlapping_output() {
    let mut buf = [0u8; 16];
    let b = [255u8; 8];
    let ia = PmImage {
        data: buf.as_ptr(),
        len: 8,
        stride: 0,
    };
    let ib = image(&b);
    let (s, _) = call(&ia, &ib, unsafe { buf.as_mut_ptr().add(4) }, 8, &opts());
    assert_eq!(s, PmStatus::BuffersOverlap);
    // 隣接（重ならない）なら許可
    let (s, _) = call(&ia, &ib, unsafe { buf.as_mut_ptr().add(8) }, 8, &opts());
    assert_eq!(s, PmStatus::Ok);
}
