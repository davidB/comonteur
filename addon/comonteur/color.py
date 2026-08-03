"""sRGB<->linear color conversion. hex/CSS colors (brand palettes, HyperFrames
provenance data) are sRGB-encoded; Blender's Emission/Base Color inputs are linear.
Feeding hex/255 straight in double-gamma-washes dark colors toward gray.
"""


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_rgba(hex_str: str, a: float = 1.0) -> tuple[float, float, float, float]:
    h = hex_str.lstrip("#")
    r, g, b = (srgb_to_linear(int(h[i : i + 2], 16) / 255.0) for i in (0, 2, 4))
    return (r, g, b, a)
