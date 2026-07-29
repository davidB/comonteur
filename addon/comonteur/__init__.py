"""comonteur — canonical alias for the agent: `import comonteur as cmt`."""

from . import doctor, introspect, journal, preview, provenance, scene, ui  # noqa: F401


def register():
    provenance.register()
    ui.register()


def unregister():
    ui.unregister()
    provenance.unregister()
