"""Manual ownership override — SPEC.md §4.3, required regardless of flip-handler reliability."""

import bpy

from . import const


def _targets(context):
    obj = context.active_object
    return [obj] if obj is not None and obj.get(const.PROP_ID) is not None else []


class COMONTEUR_OT_take_ownership(bpy.types.Operator):
    bl_idname = "comonteur.take_ownership"
    bl_label = "Take Ownership"
    bl_description = (
        "Mark the active object as human-owned; the agent will only touch it if asked by name"
    )

    def execute(self, context):
        for id_block in _targets(context):
            id_block[const.PROP_ORIGIN] = const.ORIGIN_HUMAN
        return {"FINISHED"}


class COMONTEUR_OT_return_to_agent(bpy.types.Operator):
    bl_idname = "comonteur.return_to_agent"
    bl_label = "Return to Agent"
    bl_description = "Mark the active object as agent-owned again"

    def execute(self, context):
        for id_block in _targets(context):
            id_block[const.PROP_ORIGIN] = const.ORIGIN_AGENT
        return {"FINISHED"}


class COMONTEUR_PT_panel(bpy.types.Panel):
    bl_idname = "COMONTEUR_PT_panel"
    bl_label = "comonteur"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "comonteur"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj is None or obj.get(const.PROP_ID) is None:
            layout.label(text="No comonteur-tagged object active")
            return
        layout.label(text=f"cmt_id: {obj[const.PROP_ID]}")
        layout.label(text=f"origin: {obj.get(const.PROP_ORIGIN, '-')}")
        layout.operator(COMONTEUR_OT_take_ownership.bl_idname)
        layout.operator(COMONTEUR_OT_return_to_agent.bl_idname)


_classes = (COMONTEUR_OT_take_ownership, COMONTEUR_OT_return_to_agent, COMONTEUR_PT_panel)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
