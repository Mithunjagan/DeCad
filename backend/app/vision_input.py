"""Bounded overview/detail images for a general schematic vision model."""
import base64
import io
import math
import os

from PIL import Image

from .engine import OperationError
from .vision_local import prepare


def setting(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise OperationError(f'{name} must be an integer.') from exc
    if not minimum <= value <= maximum:
        raise OperationError(f'{name} must be between {minimum} and {maximum}.')
    return value


def model_images(path):
    """One overview plus overlapping, collectively exhaustive detail regions.

All views describe the same page in one model request. Crops are never converted
to separate graphs or merged by assumed label similarity.
"""
    size = setting('VISION_IMAGE_SIZE', 2048, 512, 4096)
    budget = setting('VISION_DETAIL_IMAGES', 4, 0, 8)
    source = prepare(path, max_dim=100000)
    width, height = source.size
    regions = [(0, 0, width, height)]
    if budget >= 2 and max(width, height) > size:
        # Choose the grid whose tiles need the least downsampling, using <= budget.
        grids = [(cols, rows) for cols in range(1, budget + 1)
                 for rows in range(1, budget + 1) if 2 <= cols * rows <= budget]
        cols, rows = min(grids, key=lambda grid: (max(width / grid[0], height / grid[1]), -grid[0] * grid[1]))
        for row in range(rows):
            for col in range(cols):
                overlap_x, overlap_y = width / cols * .08, height / rows * .08
                regions.append((max(0, math.floor(col * width / cols - overlap_x)),
                                max(0, math.floor(row * height / rows - overlap_y)),
                                min(width, math.ceil((col + 1) * width / cols + overlap_x)),
                                min(height, math.ceil((row + 1) * height / rows + overlap_y))))
    images, descriptions = [], []
    for index, box in enumerate(regions):
        view = source.crop(box)
        view.thumbnail((size, size), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        view.save(output, format='PNG')
        images.append(base64.b64encode(output.getvalue()).decode())
        coordinates = ', '.join(f'{value / (width if i % 2 == 0 else height):.5f}' for i, value in enumerate(box))
        descriptions.append(f'Image {index + 1}: ' + ('complete page overview' if index == 0 else f'detail rectangle [{coordinates}] on the full page'))
    return images, '\n'.join(descriptions)
