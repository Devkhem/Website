#!/usr/bin/env python3
"""Prepare local images for APIs that are strict about image encoding.

The default output is a square RGB PNG suitable for legacy image variation
endpoints that reject vertical PNGs even when the image file is otherwise valid.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps


DEFAULT_MAX_BYTES = 4 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Normalize an image for API upload.')
    parser.add_argument('image', help='Input image path.')
    parser.add_argument('--out', default='', help='Output image path. Defaults to <name>-api-square.png.')
    parser.add_argument('--size', type=int, default=1024, help='Square output size in pixels.')
    parser.add_argument('--max-mb', type=float, default=4, help='Maximum output size in MB.')
    return parser.parse_args()


def load_rgb(path: Path) -> Image.Image:
    image = Image.open(path)
    image = ImageOps.exif_transpose(image)
    if image.mode == 'RGB':
        return image
    if image.mode in {'RGBA', 'LA'} or (image.mode == 'P' and 'transparency' in image.info):
        rgba = image.convert('RGBA')
        background = Image.new('RGBA', rgba.size, (0, 0, 0, 255))
        return Image.alpha_composite(background, rgba).convert('RGB')
    return image.convert('RGB')


def resize_cover(image: Image.Image, size: int) -> Image.Image:
    scale = max(size / image.width, size / image.height)
    width = math.ceil(image.width * scale)
    height = math.ceil(image.height * scale)
    resized = image.resize((width, height), Image.Resampling.LANCZOS)
    left = (width - size) // 2
    top = (height - size) // 2
    return resized.crop((left, top, left + size, top + size))


def resize_contain(image: Image.Image, size: int, margin: float = 0.04) -> Image.Image:
    target = int(size * (1 - margin * 2))
    scale = min(target / image.width, target / image.height)
    width = max(1, round(image.width * scale))
    height = max(1, round(image.height * scale))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def square_pad(image: Image.Image, size: int) -> Image.Image:
    background = resize_cover(image, size)
    background = background.filter(ImageFilter.GaussianBlur(radius=max(12, size // 36)))
    shade = Image.new('RGB', (size, size), (8, 9, 12))
    background = Image.blend(background, shade, 0.34)

    foreground = resize_contain(image, size)
    canvas = background.copy()
    x = (size - foreground.width) // 2
    y = (size - foreground.height) // 2
    canvas.paste(foreground, (x, y))
    return canvas


def save_under_limit(image: Image.Image, output_path: Path, max_bytes: int) -> tuple[int, int]:
    size = image.width
    current = image
    while True:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        current.save(output_path, format='PNG', optimize=True)
        bytes_written = output_path.stat().st_size
        if bytes_written <= max_bytes or size <= 512:
            return size, bytes_written
        size = max(512, int(size * 0.9))
        current = image.resize((size, size), Image.Resampling.LANCZOS)


def default_output_path(input_path: Path) -> Path:
    return input_path.with_name(f'{input_path.stem}-api-square.png')


def main() -> None:
    args = parse_args()
    input_path = Path(args.image)
    output_path = Path(args.out) if args.out else default_output_path(input_path)
    max_bytes = int(args.max_mb * 1024 * 1024)

    image = load_rgb(input_path)
    prepared = square_pad(image, args.size)
    final_size, bytes_written = save_under_limit(prepared, output_path, max_bytes)

    print(f'Created {output_path}')
    print(f'Input: {image.width}x{image.height} {image.mode}')
    print(f'Output: {final_size}x{final_size} PNG RGB, {bytes_written / (1024 * 1024):.2f} MB')


if __name__ == '__main__':
    main()
