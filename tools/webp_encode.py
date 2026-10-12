#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["pillow"]
# ///
# Fallback de cwebp (libwebp CLI) via Pillow, para entornos sin el binario cwebp en PATH
# (este taller: sin sudo, no se puede instalar el paquete libwebp-tools del sistema).
# Mismos parametros que cwebp -q Q -m 6: metodo de compresion 6 (mejor/mas lento), sin alpha.
import sys
from PIL import Image

src, dst, q = sys.argv[1], sys.argv[2], int(sys.argv[3])
im = Image.open(src).convert("RGB")
im.save(dst, "WEBP", quality=q, method=6)
