// pixelmatch-cpp を Rust から呼ぶための内部用 C インターフェース。
// 公開 C ABI ではない（公開 ABI は pixelmatch-ffi クレートが提供する）。
// 入力検証は Rust 側で済ませる前提のため、ここでは一切検証しない。
#ifndef PIXELMATCH_SHIM_H
#define PIXELMATCH_SHIM_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct pmx_options {
    double threshold;
    double alpha;
    uint8_t aa_color[3];
    uint8_t diff_color[3];
    uint8_t diff_color_alt[3];
    uint8_t has_diff_color_alt;
    uint8_t include_aa;
    uint8_t diff_mask;
    uint8_t checkerboard;
    const uint8_t* ignore_mask;
    size_t window_size;
} pmx_options;

enum {
    PMX_OK = 0,
    PMX_OUT_OF_MEMORY = 1,
    PMX_EXCEPTION = 2,
};

int pmx_pixelmatch(const uint8_t* img1,
                   size_t stride1,
                   const uint8_t* img2,
                   size_t stride2,
                   size_t width,
                   size_t height,
                   uint8_t* output,
                   const pmx_options* options,
                   uint64_t* result);

#ifdef __cplusplus
}
#endif

#endif
