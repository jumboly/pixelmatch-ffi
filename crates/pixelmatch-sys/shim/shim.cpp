#include "shim.h"

#include <mapbox/pixelmatch.hpp>
#include <new>

extern "C" int pmx_pixelmatch(const uint8_t* img1,
                              size_t stride1,
                              const uint8_t* img2,
                              size_t stride2,
                              size_t width,
                              size_t height,
                              uint8_t* output,
                              const pmx_options* o,
                              uint64_t* result) {
    // C++ 例外が extern "C" 境界を越えると未定義動作になるため、ここで全て捕捉してコード化する。
    // pixelmatch 内部の std::vector / new は巨大画像で bad_alloc を投げうる。
    try {
        mapbox::Options opts;
        opts.threshold = o->threshold;
        opts.alpha = o->alpha;
        opts.aaColor = {o->aa_color[0], o->aa_color[1], o->aa_color[2]};
        opts.diffColor = {o->diff_color[0], o->diff_color[1], o->diff_color[2]};
        if (o->has_diff_color_alt) {
            opts.diffColorAlt = mapbox::Color{o->diff_color_alt[0], o->diff_color_alt[1], o->diff_color_alt[2]};
        }
        opts.includeAA = o->include_aa != 0;
        opts.diffMask = o->diff_mask != 0;
        opts.checkerboard = o->checkerboard != 0;
        opts.ignoreMask = o->ignore_mask;
        opts.windowSize = o->window_size;

        *result = mapbox::pixelmatch(img1, stride1, img2, stride2, width, height, output, opts);
        return PMX_OK;
    } catch (const std::bad_alloc&) {
        return PMX_OUT_OF_MEMORY;
    } catch (...) {
        return PMX_EXCEPTION;
    }
}
