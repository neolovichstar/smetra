"""Decode untrusted avatars in a bounded process without application credentials."""

import io
import sys
import warnings


def main():
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = 16_000_000
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    raw = sys.stdin.buffer.read(1_048_577)
    if not raw or len(raw) > 1_048_576:
        raise ValueError("size")
    with Image.open(io.BytesIO(raw)) as original:
        if (
            original.format not in ("PNG", "JPEG", "WEBP")
            or getattr(original, "n_frames", 1) != 1
        ):
            raise ValueError("format")
        if (
            max(original.size) > 8192
            or min(original.size) < 16
            or original.width * original.height > 16_000_000
        ):
            raise ValueError("dimensions")
        original.load()
        oriented = ImageOps.exif_transpose(original)
        # A fresh image drops EXIF, ICC, comments and other uploaded metadata.
        mode = "RGBA" if "A" in oriented.getbands() else "RGB"
        square = ImageOps.fit(
            oriented.convert(mode), (384, 384), method=Image.Resampling.LANCZOS
        )
        clean = Image.new(mode, square.size)
        clean.paste(square)
        output = io.BytesIO()
        clean.save(output, format="WEBP", quality=85, method=4)
        result = output.getvalue()
        if len(result) > 160_000:
            raise ValueError("output")
        sys.stdout.buffer.write(result)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(2)
