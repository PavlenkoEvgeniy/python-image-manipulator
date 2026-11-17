"""Generate the application icon in PNG, ICO and ICNS formats.

The icon is a rounded gradient tile holding a photo card: a landscape
(sun + mountains) with a bold "T" for the text overlay, plus a resize
badge for the resizing step.

Run from the repository root:

    python tools/generate_icon.py
"""

from __future__ import annotations

import io
import struct
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
PACKAGE = ROOT / "src" / "image_manipulator"

# Supersampled canvas; the final icon is downscaled to 1024.
S = 2048
FINAL_SIZE = 1024
PACKAGE_SIZE = 256

GRADIENT_START = (109, 40, 217)   # violet-700
GRADIENT_END = (6, 182, 212)      # cyan-500
INK = (30, 27, 75, 255)           # indigo-950


def lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """Linearly interpolate between two RGB colors."""
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def diagonal_gradient(size: int) -> Image.Image:
    """Top-left to bottom-right color gradient."""
    small = 512
    gradient = Image.new("RGB", (small, small))
    pixels = gradient.load()
    for y in range(small):
        for x in range(small):
            pixels[x, y] = lerp(GRADIENT_START, GRADIENT_END, (x + y) / (2 * (small - 1)))
    return gradient.resize((size, size), Image.Resampling.BICUBIC)


def vertical_gradient(
    width: int, height: int, start: tuple[int, int, int], end: tuple[int, int, int]
) -> Image.Image:
    """Top to bottom color gradient."""
    gradient = Image.new("RGB", (1, height))
    pixels = gradient.load()
    for y in range(height):
        pixels[0, y] = lerp(start, end, y / max(1, height - 1))
    return gradient.resize((width, height), Image.Resampling.BICUBIC)


def rounded_mask(width: int, height: int, radius: int) -> Image.Image:
    """Anti-aliased rounded-rectangle mask."""
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, width - 1, height - 1], radius=radius, fill=255
    )
    return mask


def _arrow_head(
    draw: ImageDraw.ImageDraw,
    base: tuple[float, float],
    direction: tuple[float, float],
    length: float,
    width: float,
    fill,
) -> None:
    """Draw a triangular arrowhead whose base is at ``base``."""
    ux, uy = direction
    tip = (base[0] + ux * length, base[1] + uy * length)
    perp = (-uy, ux)
    left = (base[0] + perp[0] * width / 2, base[1] + perp[1] * width / 2)
    right = (base[0] - perp[0] * width / 2, base[1] - perp[1] * width / 2)
    draw.polygon([tip, left, right], fill=fill)


def draw_icon(size: int = S) -> Image.Image:
    """Render the icon at the given (supersampled) size."""
    # Rounded gradient tile
    background = diagonal_gradient(size).convert("RGBA")
    tile_radius = int(size * 0.22)
    tile_mask = rounded_mask(size, size, tile_radius)
    background.putalpha(tile_mask)

    # Soft top-left highlight
    highlight = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(highlight).ellipse(
        [int(-0.35 * size), int(-0.55 * size), int(0.95 * size), int(0.45 * size)],
        fill=(255, 255, 255, 40),
    )
    highlight = highlight.filter(ImageFilter.GaussianBlur(int(0.04 * size)))
    highlight.putalpha(ImageChops.multiply(highlight.getchannel("A"), tile_mask))
    background = Image.alpha_composite(background, highlight)

    # Photo card geometry
    card_w = int(0.62 * size)
    card_h = int(0.50 * size)
    card_x = (size - card_w) // 2
    card_y = int((size - card_h) / 2 - 0.015 * size)
    card_radius = int(0.055 * size)

    # Card shadow
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [
            card_x,
            card_y + int(0.025 * size),
            card_x + card_w,
            card_y + card_h + int(0.025 * size),
        ],
        radius=card_radius,
        fill=(15, 23, 42, 100),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(int(0.018 * size)))
    background = Image.alpha_composite(background, shadow)

    # Photo content: sky, sun, mountains
    content = vertical_gradient(
        card_w, card_h, (240, 249, 255), (186, 230, 253)
    ).convert("RGBA")

    sun_radius = int(0.10 * card_h)
    sun_x = int(0.80 * card_w)
    sun_y = int(0.27 * card_h)

    # Blend the glow into the sky first; drawing translucent pixels directly
    # leaves them to blend with whatever lies behind the card later.
    glow = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [
            sun_x - int(1.45 * sun_radius),
            sun_y - int(1.45 * sun_radius),
            sun_x + int(1.45 * sun_radius),
            sun_y + int(1.45 * sun_radius),
        ],
        fill=(251, 191, 36, 70),
    )
    content = Image.alpha_composite(content, glow)
    draw = ImageDraw.Draw(content)

    draw.ellipse(
        [
            sun_x - sun_radius,
            sun_y - sun_radius,
            sun_x + sun_radius,
            sun_y + sun_radius,
        ],
        fill=(245, 158, 11, 255),
    )

    # Back mountain
    draw.polygon(
        [
            (int(0.02 * card_w), int(0.88 * card_h)),
            (int(0.40 * card_w), int(0.42 * card_h)),
            (int(0.70 * card_w), int(0.88 * card_h)),
        ],
        fill=(14, 116, 144, 255),
    )
    # Front mountain
    draw.polygon(
        [
            (int(0.30 * card_w), int(0.92 * card_h)),
            (int(0.63 * card_w), int(0.52 * card_h)),
            (int(0.99 * card_w), int(0.92 * card_h)),
        ],
        fill=(21, 94, 117, 255),
    )
    # Snow caps
    draw.polygon(
        [
            (int(0.34 * card_w), int(0.51 * card_h)),
            (int(0.40 * card_w), int(0.42 * card_h)),
            (int(0.46 * card_w), int(0.51 * card_h)),
        ],
        fill=(224, 242, 254, 255),
    )
    draw.polygon(
        [
            (int(0.57 * card_w), int(0.61 * card_h)),
            (int(0.63 * card_w), int(0.52 * card_h)),
            (int(0.69 * card_w), int(0.61 * card_h)),
        ],
        fill=(224, 242, 254, 255),
    )

    # Bold "T" made of rounded bars, standing for the text overlay.
    t_height = int(0.34 * card_h)
    t_thickness = int(0.082 * card_h)
    t_width = int(0.34 * card_w)
    t_x = int(0.12 * card_w)
    t_y = int(0.16 * card_h)
    stem_x = t_x + (t_width - t_thickness) // 2

    draw.rounded_rectangle(
        [t_x, t_y, t_x + t_width, t_y + t_thickness],
        radius=t_thickness // 2,
        fill=INK,
    )
    draw.rounded_rectangle(
        [stem_x, t_y, stem_x + t_thickness, t_y + t_height],
        radius=t_thickness // 2,
        fill=INK,
    )

    # Thin white print border, clipped by the card mask.
    border = max(2, int(0.006 * size))
    draw.rounded_rectangle(
        [border, border, card_w - border, card_h - border],
        radius=max(1, card_radius - border),
        outline=(255, 255, 255, 255),
        width=border,
    )

    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    card.paste(content, (0, 0), rounded_mask(card_w, card_h, card_radius))
    background.alpha_composite(card, dest=(card_x, card_y))

    # Resize badge with a double-headed diagonal arrow.
    badge_radius = int(0.095 * size)
    badge_x = card_x + card_w - int(0.035 * size)
    badge_y = card_y + card_h - int(0.035 * size)
    ring_radius = badge_radius + max(3, int(0.014 * size))

    draw = ImageDraw.Draw(background)
    draw.ellipse(
        [
            badge_x - ring_radius,
            badge_y - ring_radius,
            badge_x + ring_radius,
            badge_y + ring_radius,
        ],
        fill=(255, 255, 255, 255),
    )
    draw.ellipse(
        [
            badge_x - badge_radius,
            badge_y - badge_radius,
            badge_x + badge_radius,
            badge_y + badge_radius,
        ],
        fill=(251, 191, 36, 255),
    )

    arm = int(0.045 * size)
    line_width = max(3, int(0.015 * size))
    start = (badge_x - arm, badge_y + arm)
    end = (badge_x + arm, badge_y - arm)
    draw.line([start, end], fill=INK, width=line_width)

    u = 0.7071
    head_length = int(0.032 * size)
    head_width = int(0.030 * size)
    _arrow_head(draw, end, (u, -u), head_length, head_width, INK)
    _arrow_head(draw, start, (-u, u), head_length, head_width, INK)

    return background.resize((FINAL_SIZE, FINAL_SIZE), Image.Resampling.LANCZOS)


def write_icns(image: Image.Image, path: Path) -> None:
    """Write an ICNS container with standard PNG-based chunk types."""
    chunks = []
    for size, chunk_type in (
        (16, b"icp4"),
        (32, b"icp5"),
        (64, b"icp6"),
        (128, b"ic07"),
        (256, b"ic08"),
        (512, b"ic09"),
        (1024, b"ic10"),
    ):
        buffer = io.BytesIO()
        image.resize((size, size), Image.Resampling.LANCZOS).save(
            buffer, format="PNG"
        )
        payload = buffer.getvalue()
        chunks.append(chunk_type + struct.pack(">I", len(payload) + 8) + payload)

    body = b"".join(chunks)
    path.write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)


def main() -> None:
    """Generate every icon artifact."""
    ASSETS.mkdir(exist_ok=True)
    PACKAGE.mkdir(parents=True, exist_ok=True)

    icon = draw_icon()
    icon.save(ASSETS / "icon.png", optimize=True)
    icon.save(
        ASSETS / "icon.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    write_icns(icon, ASSETS / "icon.icns")
    icon.resize((PACKAGE_SIZE, PACKAGE_SIZE), Image.Resampling.LANCZOS).save(
        PACKAGE / "icon.png", optimize=True
    )

    print(f"Wrote {ASSETS / 'icon.png'}")
    print(f"Wrote {ASSETS / 'icon.ico'}")
    print(f"Wrote {ASSETS / 'icon.icns'}")
    print(f"Wrote {PACKAGE / 'icon.png'}")


if __name__ == "__main__":
    main()
