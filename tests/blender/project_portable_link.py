"""library.link() must resolve a project-relative path (the form skill docs tell an
agent to call, e.g. cmt.library.link("lib/design.blend", ...)) via the project root,
not the process's cwd — the exact bug class that made fonts go missing (SPEC.md
troubleshooting.md). Regression: link succeeds despite a mismatched cwd, and the
library block Blender saves is //-relative (portable if the project folder moves),
not an absolute path baked to wherever it happened to be linked from.
"""

import os
import tempfile

import _bl
import bpy

cmt = _bl.setup()

project_dir = tempfile.mkdtemp(prefix="comonteur_project_")
os.makedirs(os.path.join(project_dir, ".comonteur"))
os.makedirs(os.path.join(project_dir, "lib"))

lib_path = os.path.join(project_dir, "lib", "design.blend")
bounce = bpy.data.actions.new("BounceIn")
bounce.asset_mark()
bpy.ops.wm.save_as_mainfile(filepath=lib_path)

cmt.unregister()
bpy.ops.wm.read_factory_settings(use_empty=True)
cmt.register()

timeline_path = os.path.join(project_dir, "timeline.blend")
bpy.ops.wm.save_as_mainfile(filepath=timeline_path)

# Simulate the reported bug: Blender's cwd is not the project root.
os.chdir(tempfile.mkdtemp(prefix="comonteur_elsewhere_"))

linked = cmt.library.link("lib/design.blend", "actions", "BounceIn")
assert linked.name == "BounceIn", linked.name

lib_block = next(lb for lb in bpy.data.libraries if lb.filepath.endswith("design.blend"))
assert lib_block.filepath == "//lib/design.blend", lib_block.filepath
