"""Camera/frame-level overlay effects — not a text or card-image concept, so its own
module per the addon/comonteur/ responsibility split.
"""

from typing import Any

import bpy

from . import card, provenance


def vignette(
    scn: Any,
    *,
    color: tuple[float, ...] = (0.0, 0.0, 0.0),
    strength: float = 0.6,
    name: str | None = None,
) -> Any:
    """Camera-facing plane whose alpha/emission falls off toward the edges via a
    radial ("Quadratic Sphere") gradient texture — the darken-the-corners overlay
    GSAP/CSS vignettes usually are.
    """
    name = name or "vignette"
    quad = card._plane(scn, name, 2.0, 2.0)

    mat = bpy.data.materials.new(f"{quad.name}.color")
    mat.use_nodes = True
    quad.data.materials.append(mat)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    gradient = nodes.new("ShaderNodeTexGradient")
    gradient.gradient_type = "QUADRATIC_SPHERE"
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*color[:3], 0.0)
    ramp.color_ramp.elements[1].color = (*color[:3], strength)
    links.new(gradient.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 1.0

    provenance.tag(quad, name)
    return quad
