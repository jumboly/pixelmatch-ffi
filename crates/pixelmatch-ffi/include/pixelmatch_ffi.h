/*
 * pixelmatch-ffi: C ABI for mapbox/pixelmatch-cpp.
 * このファイルは cbindgen で自動生成される。直接編集せず `mise run header` で再生成すること。
 */

#ifndef PIXELMATCH_FFI_H
#define PIXELMATCH_FFI_H

#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

// ABI の互換性が壊れる変更をしたときだけ増やす。
#define PM_ABI_VERSION 1

// 関数の戻り値。
typedef enum PmStatus {
  PM_STATUS_OK = 0,
  PM_STATUS_NULL_POINTER = 1,
  PM_STATUS_INVALID_ARGUMENT = 2,
  PM_STATUS_INVALID_STRIDE = 3,
  PM_STATUS_IMAGE_TOO_SMALL = 4,
  PM_STATUS_OUTPUT_TOO_SMALL = 5,
  PM_STATUS_IGNORE_MASK_TOO_SMALL = 6,
  PM_STATUS_SIZE_OVERFLOW = 7,
  // output が入力画像と重なっている（C++ 実装は入力を読みながら出力に書くため結果が壊れる）
  PM_STATUS_BUFFERS_OVERLAP = 8,
  PM_STATUS_OUT_OF_MEMORY = 9,
  // 想定外の内部エラー（Rust の panic / C++ の例外）
  PM_STATUS_INTERNAL = 99,
} PmStatus;

// diff 画像の描画色 (RGB)。
typedef struct PmColor {
  uint8_t r;
  uint8_t g;
  uint8_t b;
} PmColor;

// 比較オプション。必ず `pm_options_init` で初期化してから値を変更すること。
typedef struct PmOptions {
  // `sizeof(PmOptions)`。`pm_options_init` が設定する。
  uint32_t struct_size;
  double threshold;
  double alpha;
  struct PmColor aa_color;
  struct PmColor diff_color;
  // `has_diff_color_alt` が 0 のときは無視される
  struct PmColor diff_color_alt;
  uint8_t has_diff_color_alt;
  uint8_t include_aa;
  uint8_t diff_mask;
  uint8_t checkerboard;
  // 0 なら差分総数、N なら N×N 窓内の差分数の最大値を返す
  uint64_t window_size;
} PmOptions;

// RGBA8 画像。`stride` が 0 なら `width * 4`（行間の詰め物なし）とみなす。
typedef struct PmImage {
  const uint8_t *data;
  // `data` の読み取り可能なバイト数
  size_t len;
  size_t stride;
} PmImage;

#ifdef __cplusplus
extern "C" {
#endif // __cplusplus

// `PM_ABI_VERSION` を返す。ラッパーはロード時にこれを照合し、不一致なら使用を拒否すること。
uint32_t pm_abi_version(void);

// ライブラリのバージョン文字列（静的領域、解放不要）。
const char *pm_version(void);

// ステータスコードの英語メッセージ（静的領域、解放不要）。未知のコードでも NULL は返さない。
const char *pm_status_message(int status);

// `opts` を既定値で初期化し、`struct_size` を設定する。
//
// # Safety
// `opts` は NULL か、`PmOptions` を書き込める領域を指すこと。
enum PmStatus pm_options_init(struct PmOptions *opts);

// 2 枚の RGBA8 画像を比較する。
//
// - `output`: NULL 可。非 NULL なら `width * height * 4` バイトの diff 画像を書き込む。
//   入力画像と重なってはならない。
// - `ignore_mask`: NULL 可。`width * height` バイト、非 0 のピクセルを比較から除外。
// - `opts`: NULL なら既定値。
// - `out_count`: 差分ピクセル数（`window_size` 指定時は窓内最大数）の格納先。
//
// # Safety
// 各ポインタは対応する長さ分だけ有効であること。関数はスレッドセーフで状態を持たない。
enum PmStatus pm_pixelmatch(const struct PmImage *img1,
                            const struct PmImage *img2,
                            uint32_t width,
                            uint32_t height,
                            uint8_t *output,
                            size_t output_len,
                            const uint8_t *ignore_mask,
                            size_t ignore_mask_len,
                            const struct PmOptions *opts,
                            uint64_t *out_count);

#ifdef __cplusplus
}  // extern "C"
#endif  // __cplusplus

#endif  /* PIXELMATCH_FFI_H */
