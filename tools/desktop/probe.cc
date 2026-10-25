#include "include/codec/SkCodec.h"
#include "include/core/SkBitmap.h"
#include "include/core/SkData.h"
#include <cstdio>

int main(int argc, char** argv) {
    if (argc != 2) return 1;
    auto codec = SkCodec::MakeFromData(SkData::MakeFromFileName(argv[1]));
    if (!codec || codec->dimensions() != SkISize::Make(8, 8)) return 2;
    SkBitmap bitmap;
    if (!bitmap.tryAllocN32Pixels(8, 8) ||
        codec->getPixels(bitmap.info(), bitmap.getPixels(), bitmap.rowBytes()) != SkCodec::kSuccess) return 3;
    for (int y = 0; y < 8; ++y)
        for (int x = 0; x < 8; ++x)
            if (bitmap.getColor(x, y) != ((x + y) % 2 ? SK_ColorBLUE : SK_ColorRED)) return 4;
    std::puts("SYNCWATCH_NATIVE_PNG_OK");
}
