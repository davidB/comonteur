"""comonteur — canonical alias for the agent: `import comonteur as cmt`."""

from . import (  # noqa: F401
    anim,
    card,
    doctor,
    introspect,
    journal,
    library,
    preview,
    provenance,
    reconcile,
    scene,
    text,
    ui,
)


def register():
    provenance.register()
    scene.register()
    ui.register()


def unregister():
    ui.unregister()
    scene.unregister()
    provenance.unregister()
