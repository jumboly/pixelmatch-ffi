//! mapbox/pixelmatch-cpp への生バインディング。
//!
//! 安全性の保証は一切しないため、通常は `pixelmatch` クレートを使うこと。
#![no_std]

use core::ffi::c_int;

#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct pmx_options {
    pub threshold: f64,
    pub alpha: f64,
    pub aa_color: [u8; 3],
    pub diff_color: [u8; 3],
    pub diff_color_alt: [u8; 3],
    pub has_diff_color_alt: u8,
    pub include_aa: u8,
    pub diff_mask: u8,
    pub checkerboard: u8,
    pub ignore_mask: *const u8,
    pub window_size: usize,
}

pub const PMX_OK: c_int = 0;
pub const PMX_OUT_OF_MEMORY: c_int = 1;
pub const PMX_EXCEPTION: c_int = 2;

unsafe extern "C" {
    /// # Safety
    /// - `img1`/`img2` は `stride * (height - 1) + width * 4` バイト以上読めること
    /// - `output` は NULL か `width * height * 4` バイト書けること（入力と重ならないこと）
    /// - `options.ignore_mask` は NULL か `width * height` バイト読めること
    pub fn pmx_pixelmatch(
        img1: *const u8,
        stride1: usize,
        img2: *const u8,
        stride2: usize,
        width: usize,
        height: usize,
        output: *mut u8,
        options: *const pmx_options,
        result: *mut u64,
    ) -> c_int;
}
