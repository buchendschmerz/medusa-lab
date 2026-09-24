"""Pixel-art engine: canvas, bitmap font, sprites, and SVG/GIF/ANSI exporters."""

from .canvas import Canvas, Layer, Scene, TextOverlay
from .gif import encode_gif, scene_to_gif
from .svg import render_svg

__all__ = ["Canvas", "Layer", "Scene", "TextOverlay", "encode_gif", "render_svg", "scene_to_gif"]
