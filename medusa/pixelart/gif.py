"""Dependency-free animated GIF89a encoder for pixel-art scenes.

Only the bounding box of pixels that changed since the previous frame is
stored for frames after the first (disposal "do not dispose"), which keeps a
mostly static dashboard animation small.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence

from .canvas import Canvas, Scene

RGB = tuple[int, int, int]


def _lzw(indices: Sequence[int], min_code_size: int) -> bytes:
    clear = 1 << min_code_size
    eoi = clear + 1
    code_size = min_code_size + 1
    next_code = eoi + 1
    table: dict[int, int] = {}
    out = bytearray()
    buffer = 0
    nbits = 0

    def emit(code: int) -> None:
        nonlocal buffer, nbits
        buffer |= code << nbits
        nbits += code_size
        while nbits >= 8:
            out.append(buffer & 0xFF)
            buffer >>= 8
            nbits -= 8

    emit(clear)
    it = iter(indices)
    try:
        prefix = next(it)
    except StopIteration:
        emit(eoi)
        if nbits:
            out.append(buffer & 0xFF)
        return bytes(out)
    for k in it:
        key = (prefix << 8) | k
        code = table.get(key)
        if code is not None:
            prefix = code
            continue
        emit(prefix)
        if next_code < 4096:
            table[key] = next_code
            if next_code == (1 << code_size) and code_size < 12:
                code_size += 1
            next_code += 1
        else:
            emit(clear)
            table.clear()
            code_size = min_code_size + 1
            next_code = eoi + 1
        prefix = k
    emit(prefix)
    emit(eoi)
    if nbits:
        out.append(buffer & 0xFF)
    return bytes(out)


def _sub_blocks(data: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(data), 255):
        chunk = data[i:i + 255]
        out.append(len(chunk))
        out += chunk
    out.append(0)
    return bytes(out)


def encode_gif(frames: Sequence[tuple[Canvas, int]], scale: int = 1, background: str = "#000000",
               loop: int = 0) -> bytes:
    """Encode ``(canvas, duration_ms)`` frames into an animated GIF."""
    if not frames:
        raise ValueError("no frames")
    rows_per_frame = [canvas.rgb_rows(background) for canvas, _ in frames]
    colors: dict[RGB, int] = {}
    for rows in rows_per_frame:
        for row in rows:
            for rgb in row:
                if rgb not in colors:
                    colors[rgb] = len(colors)
    if len(colors) > 256:
        raise ValueError(f"too many colours for GIF: {len(colors)}")
    table_bits = max(1, (len(colors) - 1).bit_length())  # GCT size = 2 ** table_bits
    min_code_size = max(2, table_bits)
    palette = bytearray()
    for rgb in sorted(colors, key=colors.__getitem__):
        palette += bytes(rgb)
    palette += b"\x00" * (3 * (1 << table_bits) - len(palette))

    width, height = frames[0][0].width, frames[0][0].height
    out = bytearray(b"GIF89a")
    out += struct.pack("<HHBBB", width * scale, height * scale, 0x80 | 0x70 | (table_bits - 1), 0, 0)
    out += palette
    if len(frames) > 1:
        out += b"\x21\xff\x0bNETSCAPE2.0\x03\x01" + struct.pack("<H", loop) + b"\x00"

    previous: list[list[int]] | None = None
    for (_, duration), rows in zip(frames, rows_per_frame, strict=True):
        grid = [[colors[rgb] for rgb in row] for row in rows]
        if previous is None:
            x0, y0, x1, y1 = 0, 0, width, height
        else:
            changed = [(x, y) for y in range(height) for x in range(width) if grid[y][x] != previous[y][x]]
            if changed:
                xs = [p[0] for p in changed]
                ys = [p[1] for p in changed]
                x0, y0, x1, y1 = min(xs), min(ys), max(xs) + 1, max(ys) + 1
            else:  # identical frame: store a single pixel so the delay still applies
                x0, y0, x1, y1 = 0, 0, 1, 1
        previous = grid
        delay = max(2, round(duration / 10))
        out += b"\x21\xf9\x04" + bytes([0x04]) + struct.pack("<H", delay) + b"\x00\x00"
        out += b"\x2c" + struct.pack("<HHHHB", x0 * scale, y0 * scale, (x1 - x0) * scale, (y1 - y0) * scale, 0)
        indices: list[int] = []
        for y in range(y0, y1):
            line: list[int] = []
            for x in range(x0, x1):
                line.extend([grid[y][x]] * scale)
            for _ in range(scale):
                indices.extend(line)
        out.append(min_code_size)
        out += _sub_blocks(_lzw(indices, min_code_size))
    out.append(0x3B)
    return bytes(out)


def scene_to_gif(scene: Scene, scale: int = 3, background: str = "#000000", max_frames: int = 24) -> bytes:
    return encode_gif(scene.timeline(max_frames=max_frames), scale=scale, background=background)
