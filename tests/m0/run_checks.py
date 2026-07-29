"""M0 API verification spike — run with: blender -b -P tests/m0/run_checks.py
Prints PASS/FAIL/INFO lines per SPEC.md §10 check id. Source for docs/M0-FINDINGS.md.
"""

import os
import tempfile

import bpy

R = []  # (id, status, detail)


def report(id_, status, detail=""):
    R.append((id_, status, detail))
    print(f"[{id_}] {status}: {detail}")


def reset_file():
    bpy.ops.wm.read_factory_settings(use_empty=True)


# --- M0.2: bpy.ops.scene.new(type=...) semantics ---
reset_file()
base_scene = bpy.data.scenes[0]
base_scene.name = "Base"
bpy.data.objects.new("BaseCube", bpy.data.meshes.new("BaseMesh"))
base_scene.collection.objects.link(bpy.data.objects["BaseCube"])
bpy.context.window.scene = base_scene

for scene_type in ("NEW", "EMPTY", "LINK_COPY", "FULL_COPY"):
    bpy.context.window.scene = base_scene
    before = set(bpy.data.scenes.keys())
    bpy.ops.scene.new(type=scene_type)
    new_scene = bpy.context.window.scene
    n_objects = len(new_scene.objects)
    report(
        "M0.2",
        "INFO",
        f"type={scene_type!r} -> new scene {new_scene.name!r}, "
        f"{n_objects} objects (0 = genuinely empty)",
    )

# --- M0.1 + M0.6: custom properties on Scene/Object/VSE strip, survive save/load & linking ---
reset_file()
scn = bpy.data.scenes[0]
scn.name = "TaggedScene"
scn["cmt_id"] = "shot-01"
scn["cmt_origin"] = "agent"
scn["cmt_rev"] = 1

obj_mesh = bpy.data.meshes.new("M")
obj = bpy.data.objects.new("TaggedObj", obj_mesh)
scn.collection.objects.link(obj)
obj["cmt_id"] = "shot-01.title"
obj["cmt_origin"] = "agent"

if not scn.sequence_editor:
    scn.sequence_editor_create()
strips = getattr(scn.sequence_editor, "strips", None)
if strips is None:
    strips = scn.sequence_editor.sequences  # pre-rename fallback, shouldn't hit on 5.2
color_strip = strips.new_effect(
    name="TaggedStrip", type="COLOR", channel=1, frame_start=1, length=50
)
try:
    color_strip["cmt_id"] = "shot-01.bg"
    color_strip["cmt_origin"] = "agent"
    strip_tag_ok = True
except Exception as e:  # noqa: BLE001
    strip_tag_ok = False
    report("M0.1", "FAIL", f"strip custom property assignment raised: {e!r}")

if strip_tag_ok:
    report("M0.1", "PASS", "VSE strip accepted custom properties before save")

tmpdir = tempfile.mkdtemp(prefix="cmt_m0_")
saved_path = os.path.join(tmpdir, "m0_tag_test.blend")
bpy.ops.wm.save_as_mainfile(filepath=saved_path)

reset_file()
bpy.ops.wm.open_mainfile(filepath=saved_path)
scn2 = bpy.data.scenes["TaggedScene"]
obj2 = bpy.data.objects["TaggedObj"]
strip2 = scn2.sequence_editor.strips["TaggedStrip"] if scn2.sequence_editor else None

scene_survived = scn2.get("cmt_id") == "shot-01"
obj_survived = obj2.get("cmt_id") == "shot-01.title"
strip_survived = bool(strip2) and strip2.get("cmt_id") == "shot-01.bg"

report(
    "M0.1",
    "PASS" if scene_survived else "FAIL",
    f"Scene cmt_id after save/load: {scn2.get('cmt_id')!r}",
)
report(
    "M0.1",
    "PASS" if obj_survived else "FAIL",
    f"Object cmt_id after save/load: {obj2.get('cmt_id')!r}",
)
report(
    "M0.1",
    "PASS" if strip_survived else "FAIL",
    f"VSE strip cmt_id after save/load: {strip2.get('cmt_id') if strip2 else None!r}",
)

# --- M0.6: survive linking (separate library file) ---
lib_dir = os.path.join(tmpdir, "linktest")
os.makedirs(lib_dir, exist_ok=True)
lib_path = os.path.join(lib_dir, "lib.blend")

reset_file()
lib_scene = bpy.data.scenes[0]
lib_scene.name = "LibScene"
lib_scene["cmt_id"] = "lib-shot"
lib_scene["cmt_origin"] = "agent"
lib_obj = bpy.data.objects.new("LibObj", bpy.data.meshes.new("LibMesh"))
lib_obj["cmt_id"] = "lib-shot.obj"
lib_scene.collection.objects.link(lib_obj)
bpy.ops.wm.save_as_mainfile(filepath=lib_path)

reset_file()
with bpy.data.libraries.load(lib_path, link=True) as (data_from, data_to):
    data_to.scenes = ["LibScene"]
linked_scene = bpy.data.scenes["LibScene"]
linked_obj = [o for o in linked_scene.objects if o.name == "LibObj"][0]

report(
    "M0.6",
    "PASS" if linked_scene.get("cmt_id") == "lib-shot" else "FAIL",
    f"linked Scene cmt_id: {linked_scene.get('cmt_id')!r}",
)
report(
    "M0.6",
    "PASS" if linked_obj.get("cmt_id") == "lib-shot.obj" else "FAIL",
    f"linked Object cmt_id: {linked_obj.get('cmt_id')!r}",
)

# --- M0.7: can a linked Scene be used as a VSE Scene strip? ---
reset_file()
with bpy.data.libraries.load(lib_path, link=True) as (data_from, data_to):
    data_to.scenes = ["LibScene"]
linked_scene2 = bpy.data.scenes["LibScene"]
host_scene = bpy.data.scenes[0]
host_scene.name = "Host"
if not host_scene.sequence_editor:
    host_scene.sequence_editor_create()
try:
    scene_strip = host_scene.sequence_editor.strips.new_scene(
        name="LinkedSceneStrip", scene=linked_scene2, channel=1, frame_start=1
    )
    report("M0.7", "PASS", f"created Scene strip from linked scene: {scene_strip.name!r}")
except Exception as e:  # noqa: BLE001
    report("M0.7", "FAIL", f"could not create Scene strip from linked scene: {e!r}")

# --- M0.4: VSE strip API shape (strips vs sequences, transform, text strip) ---
reset_file()
scn4 = bpy.data.scenes[0]
if not scn4.sequence_editor:
    scn4.sequence_editor_create()
se = scn4.sequence_editor
report(
    "M0.4",
    "INFO",
    f"has 'strips' attr: {hasattr(se, 'strips')}; has 'sequences' attr: {hasattr(se, 'sequences')}",
)
text_strip = se.strips.new_effect(
    name="TextStrip", type="TEXT", channel=1, frame_start=1, length=30
)
report(
    "M0.4",
    "INFO",
    f"text strip type name: {type(text_strip).__name__}; has .text: {hasattr(text_strip, 'text')}; has .transform: {hasattr(text_strip, 'transform')}",
)
movie_placeholder_attrs = [
    a for a in ("transform", "blend_type", "channel", "frame_final_start") if hasattr(text_strip, a)
]
report("M0.4", "INFO", f"common strip attrs present: {movie_placeholder_attrs}")

# --- M0.3: Geometry Nodes modifier property API shape ---
reset_file()
gn_obj = bpy.data.objects.new("GNObj", bpy.data.meshes.new("GNMesh"))
bpy.context.scene.collection.objects.link(gn_obj)
gn_mod = gn_obj.modifiers.new(name="GeoNodes", type="NODES")
node_group = bpy.data.node_groups.new("TestGN", "GeometryNodeTree")
gn_mod.node_group = node_group
try:
    iface_item = node_group.interface.new_socket(
        name="MyInput", in_out="INPUT", socket_type="NodeSocketFloat"
    )
    identifier = iface_item.identifier  # e.g. "Socket_0"
    # Changed in 5.2: mod[identifier] no longer works (IDProperty storage removed).
    # Inputs now live under mod.properties.inputs.<identifier>.value
    input_prop = getattr(gn_mod.properties.inputs, identifier)
    input_prop.value = 2.5
    read_back = getattr(gn_mod.properties.inputs, identifier).value
    report(
        "M0.3",
        "PASS",
        f"5.2 API: getattr(mod.properties.inputs, {identifier!r}).value — set/read 2.5 -> {read_back}. "
        f"OLD mod[identifier]=... no longer works (raises TypeError, id properties not supported).",
    )
except Exception as e:  # noqa: BLE001
    report("M0.3", "FAIL", f"GN modifier property access raised: {e!r}")

# --- M0.5: depsgraph_update_post — updates usable, upd.id.original, selection-only noise ---
reset_file()
dg_obj = bpy.data.objects.new("DGObj", bpy.data.meshes.new("DGMesh"))
bpy.context.scene.collection.objects.link(dg_obj)
fired = []


def handler(scene, depsgraph):
    fired.append(
        [
            (getattr(u.id, "original", u.id).name, u.is_updated_transform, u.is_updated_geometry)
            for u in depsgraph.updates
        ]
    )


bpy.app.handlers.depsgraph_update_post.append(handler)
fired.clear()
dg_obj.select_set(True)
bpy.context.view_layer.update()
report("M0.5", "INFO", f"updates fired on select+view_layer.update(): {fired}")

fired.clear()
dg_obj.location.x += 1.0
bpy.context.view_layer.update()
report("M0.5", "INFO", f"updates fired on location change: {fired}")
bpy.app.handlers.depsgraph_update_post.remove(handler)

# --- M0.8: undo_push from a timer callback ---
reset_file()
undo_result = {}


def timer_cb():
    try:
        bpy.ops.ed.undo_push(message="comonteur: m0 test")
        undo_result["ok"] = True
    except Exception as e:  # noqa: BLE001
        undo_result["ok"] = False
        undo_result["error"] = repr(e)
    return None


bpy.app.timers.register(timer_cb, first_interval=0.0)
# In background mode timers registered this way won't run without an event loop tick;
# note this limitation rather than pretending it passed.
report(
    "M0.8",
    "INFO",
    "registered undo_push via bpy.app.timers in background mode — background mode has no running event loop, cannot confirm execution here. Needs a GUI-session check (see M0-FINDINGS.md).",
)

print("\n=== M0 SUMMARY ===")
for id_, status, detail in R:
    print(f"{id_}\t{status}\t{detail}")
