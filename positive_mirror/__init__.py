import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Matrix, Vector


AXIS_INDEX = {'X': 0, 'Y': 1, 'Z': 2}
AXIS_ITEMS = (
    ('X', "X", ""),
    ('Y', "Y", ""),
    ('Z', "Z", ""),
)
PLANE_ITEMS = (
    ('WORLD', "World", "Mirror across a world axis through the world origin"),
    ('CURSOR', "3D Cursor", "Mirror across a world axis through the 3D Cursor"),
    ('OBJECT', "Object", "Mirror across a local axis of the chosen object"),
)

def flip_matrix(axis):
    matrix = Matrix.Identity(4)
    index = AXIS_INDEX[axis]
    matrix[index][index] = -1.0
    return matrix

def mirrored_matrix(source_matrix, plane_matrix, plane_axis, flip_axis):
    world_flip = plane_matrix @ flip_matrix(plane_axis) @ plane_matrix.inverted()
    return world_flip @ source_matrix @ flip_matrix(flip_axis)

def get_plane_matrix(plane_type, point, plane_object):
    if plane_type == 'OBJECT':
        location, rotation, scale = plane_object.matrix_world.decompose()
        return Matrix.LocRotScale(location, rotation, None)
    return Matrix.Translation(point)

def matrices_differ(matrix_a, matrix_b, tolerance=1e-5):
    for row_a, row_b in zip(matrix_a, matrix_b):
        for value_a, value_b in zip(row_a, row_b):
            if abs(value_a - value_b) > tolerance:
                return True
    return False

def set_transform_lock(obj, locked):
    obj.lock_location = (locked, locked, locked)
    obj.lock_rotation = (locked, locked, locked)
    obj.lock_rotation_w = locked
    obj.lock_scale = (locked, locked, locked)

def get_target_matrix(copy):
    link = copy.positive_mirror_link
    plane_matrix = get_plane_matrix(link.plane_type, Vector(link.plane_point), link.plane_object)
    return mirrored_matrix(link.source.matrix_world, plane_matrix, link.plane_axis, link.flip_axis)

def sync_copy(copy):
    link = copy.positive_mirror_link
    if link.source is None:
        return False
    if link.plane_type == 'OBJECT' and link.plane_object is None:
        return False

    target = get_target_matrix(copy)
    if matrices_differ(copy.matrix_world, target):
        copy.matrix_world = target
        return True
    return False

def unlink_copy(obj):
    link = obj.positive_mirror_link
    link.source = None
    link.plane_object = None
    set_transform_lock(obj, False)

def find_broken_links(scene):
    scene_objects = set(scene.objects)
    broken = []
    for obj in scene_objects:
        link = obj.positive_mirror_link
        if link.source is None:
            continue
        source_gone = link.source not in scene_objects
        plane_gone = link.plane_type == 'OBJECT' and link.plane_object not in scene_objects
        if source_gone or plane_gone:
            broken.append((obj, source_gone))
    return broken

def clean_broken_links(scene):
    delete_copies = scene.positive_mirror.delete_with_source
    broken = find_broken_links(scene)
    while broken:
        for obj, source_gone in broken:
            if delete_copies and source_gone:
                for collection in list(obj.users_collection):
                    collection.objects.unlink(obj)
            else:
                unlink_copy(obj)
        broken = find_broken_links(scene)

def sync_scene(scene):
    clean_broken_links(scene)
    updated = 0
    for obj in scene.objects:
        if sync_copy(obj):
            updated += 1
    return updated

is_syncing = False

def live_sync(scene):
    global is_syncing
    if is_syncing or not scene.positive_mirror.live_link:
        return
    if bpy.app.is_job_running('RENDER'):
        return

    is_syncing = True
    try:
        sync_scene(scene)
    finally:
        is_syncing = False

@persistent
def positive_mirror_on_depsgraph_update(scene, depsgraph):
    if depsgraph.id_type_updated('OBJECT'):
        live_sync(scene)

@persistent
def positive_mirror_on_frame_change(scene, depsgraph):
    live_sync(scene)

def remove_handler(handler_list, name):
    for handler in list(handler_list):
        if handler.__name__ == name:
            handler_list.remove(handler)

def find_opposite_mesh(source):
    if source.type != 'MESH':
        return None

    mesh_name = bpy.utils.flip_name(source.data.name)
    if mesh_name != source.data.name and mesh_name in bpy.data.meshes:
        return bpy.data.meshes[mesh_name]

    if bpy.utils.flip_name(source.name) == source.name:
        return None
    other = bpy.data.objects.get(bpy.utils.flip_name(source.name, strip_digits=True))
    if other is not None and other.type == 'MESH':
        return other.data
    return None

def mirrored_name(name):
    flipped = bpy.utils.flip_name(name)
    if flipped != name:
        return flipped
    return name + "_mirror"

def on_live_link_changed(self, context):
    if self.live_link:
        sync_scene(context.scene)

HELP_SECTIONS = (
    ("1 · Mirror", (
        "Select objects and press Mirror Selected",
        "Each copy keeps a positive scale, with no negative values",
        "Copies share the source mesh, so instancing is kept",
        "A parent with non-uniform scale can stop a copy matching exactly",
    )),
    ("2 · Mirror Plane", (
        "World mirrors across a world axis through the origin",
        "3D Cursor uses the cursor position at the moment you mirror",
        "Object mirrors across a local axis of the chosen object",
    )),
    ("3 · Flip Axis", (
        "The local axis the mesh is symmetric along, X by default",
        "A wrong flip axis shows the copy upside down or backwards",
    )),
    ("4 · Left and right meshes", (
        "Names like Asset_L and Asset_R are paired automatically",
        "The copy then uses the mesh of the other side",
        "An asymmetric mesh with no pair will not look mirrored",
    )),
    ("5 · Links", (
        "Copies follow their source and are locked",
        "Live Link updates them as you work, Refresh does it on demand",
        "Unlink Selected turns copies into normal objects",
        "Deleting a source unlinks its copies, or deletes them if ticked",
        "The add-on must be enabled for copies to follow",
    )),
)

class POSMIRROR_Settings(PropertyGroup):
    plane_type: EnumProperty(name="Mirror Plane", items=PLANE_ITEMS, default='WORLD')
    plane_axis: EnumProperty(name="Axis", items=AXIS_ITEMS, default='X')
    plane_object: PointerProperty(name="Mirror Object", type=bpy.types.Object)
    flip_axis: EnumProperty(name="Flip Axis", items=AXIS_ITEMS, default='X')
    use_opposite_mesh: BoolProperty(
        name="Use opposite side mesh",
        description="Give the copy the mesh of the other side when one exists, for example Asset_R for Asset_L",
        default=True,
    )
    delete_with_source: BoolProperty(
        name="Delete copies with source",
        description="When a source is deleted, delete its copies too. When off, the copies are unlinked and kept",
        default=False,
    )
    live_link: BoolProperty(
        name="Live Link",
        description="Keep linked copies in sync while their sources move",
        default=True,
        update=on_live_link_changed,
    )


class POSMIRROR_Link(PropertyGroup):
    source: PointerProperty(name="Source", type=bpy.types.Object)
    plane_type: EnumProperty(name="Mirror Plane", items=PLANE_ITEMS, default='WORLD')
    plane_axis: EnumProperty(name="Axis", items=AXIS_ITEMS, default='X')
    plane_point: FloatVectorProperty(name="Plane Point", subtype='XYZ')
    plane_object: PointerProperty(name="Mirror Object", type=bpy.types.Object)
    flip_axis: EnumProperty(name="Flip Axis", items=AXIS_ITEMS, default='X')


class POSMIRROR_OT_mirror(Operator):
    bl_idname = "posmirror.mirror"
    bl_label = "Mirror Selected"
    bl_description = "Create mirrored copies of the selected objects with positive scale"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(context.selected_objects) > 0

    def execute(self, context):
        settings = context.scene.positive_mirror

        if settings.plane_type == 'OBJECT' and settings.plane_object is None:
            self.report({'ERROR'}, "Pick a mirror object first")
            return {'CANCELLED'}

        point = Vector((0.0, 0.0, 0.0))
        if settings.plane_type == 'CURSOR':
            point = context.scene.cursor.location.copy()

        sources = list(context.selected_objects)
        if settings.plane_type == 'OBJECT' and settings.plane_object in sources:
            sources.remove(settings.plane_object)
        if not sources:
            self.report({'ERROR'}, "Only the mirror object is selected")
            return {'CANCELLED'}
        copies = []
        paired = 0
        for source in sources:
            copy = source.copy()
            copy.name = mirrored_name(source.name)
            for collection in source.users_collection:
                collection.objects.link(copy)
            if settings.use_opposite_mesh:
                opposite = find_opposite_mesh(source)
                if opposite is not None and opposite != source.data:
                    copy.data = opposite
                    paired += 1
            link = copy.positive_mirror_link
            link.source = source
            link.plane_type = settings.plane_type
            link.plane_axis = settings.plane_axis
            link.plane_point = point
            link.plane_object = settings.plane_object if settings.plane_type == 'OBJECT' else None
            link.flip_axis = settings.flip_axis

            set_transform_lock(copy, True)
            sync_copy(copy)
            copies.append(copy)

        for obj in context.selected_objects:
            obj.select_set(False)
        for copy in copies:
            copy.select_set(True)
        context.view_layer.objects.active = copies[-1]

        context.view_layer.update()
        mismatched = 0
        for copy in copies:
            if matrices_differ(copy.matrix_world, get_target_matrix(copy), tolerance=1e-3):
                mismatched += 1

        message = f"Mirrored {len(copies)} object(s) · {paired} used an opposite side mesh"
        if mismatched:
            self.report({'WARNING'}, f"{message} · {mismatched} may not match exactly because a parent has non-uniform scale")
        else:
            self.report({'INFO'}, message)
        return {'FINISHED'}


class POSMIRROR_OT_refresh(Operator):
    bl_idname = "posmirror.refresh"
    bl_label = "Refresh Links"
    bl_description = "Move every linked copy in the scene to match its source"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        updated = sync_scene(context.scene)
        self.report({'INFO'}, f"Updated {updated} linked copy(s)")
        return{'FINISHED'}


class POSMIRROR_OT_unlink(Operator):
    bl_idname = "posmirror.unlink"
    bl_label = "Unlink Selected"
    bl_description = "Turn the selected linked copies into normal, unlocked objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(obj.positive_mirror_link.source is not None for obj in context.selected_objects)

    def execute(self, context):
        count = 0
        for obj in context.selected_objects:
            link = obj.positive_mirror_link
            if link.source is None:
                continue
            unlink_copy(obj)
            count += 1
        self.report({'INFO'}, f"Unlinked {count} object(s)")
        return {'FINISHED'}


class POSMIRROR_OT_help(Operator):
    bl_idname = "posmirror.help"
    bl_label = "Positive Mirror Help"
    bl_description = "Show how to use this tool"

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=500)

    def draw(self, context):
        layout = self.layout
        for heading, lines in HELP_SECTIONS:
            box = layout.box()
            box.label(text=heading)
            col = box.column(align=True)
            for line in lines:
                col.label(text=line)

    def execute(self, context):
        return {'FINISHED'}

    
class POSMIRROR_PT_panel(Panel):
    bl_label = "Positive Mirror"
    bl_idname = "POSMIRROR_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Positive Mirror"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.positive_mirror

        box = layout.box()
        box.label(text="Mirror", icon='MOD_MIRROR')
        col = box.column()
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(settings, "plane_type")
        if settings.plane_type == 'OBJECT':
            col.prop(settings, "plane_object")
        col.prop(settings, "plane_axis", expand=True)
        col.prop(settings, "flip_axis", expand=True)
        box.prop(settings, "use_opposite_mesh")
        box.operator("posmirror.mirror", icon='MOD_MIRROR')

        box = layout.box()
        box.label(text="Links", icon='LINKED')
        box.prop(settings, "live_link")
        box.prop(settings, "delete_with_source")
        box.operator("posmirror.refresh", icon='FILE_REFRESH')
        box.operator("posmirror.unlink", icon='UNLINKED')

        active = context.active_object
        if active is not None and active.positive_mirror_link.source is not None:
            box.label(text=f"Linked to {active.positive_mirror_link.source.name}", icon='LINKED')

        layout.operator("posmirror.help", text="Help", icon='HELP')


def draw_mirror_menu(self, context):
    self.layout.separator()
    self.layout.operator("posmirror.mirror", text="Positive Mirror", icon='MOD_MIRROR')


classes = (
    POSMIRROR_Settings,
    POSMIRROR_Link,
    POSMIRROR_OT_mirror,
    POSMIRROR_OT_refresh,
    POSMIRROR_OT_unlink,
    POSMIRROR_OT_help,
    POSMIRROR_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.positive_mirror = PointerProperty(type=POSMIRROR_Settings)
    bpy.types.Object.positive_mirror_link = PointerProperty(type=POSMIRROR_Link)
    remove_handler(bpy.app.handlers.depsgraph_update_post, "positive_mirror_on_depsgraph_update")
    remove_handler(bpy.app.handlers.frame_change_post, "positive_mirror_on_frame_change")
    bpy.app.handlers.depsgraph_update_post.append(positive_mirror_on_depsgraph_update)
    bpy.app.handlers.frame_change_post.append(positive_mirror_on_frame_change)
    bpy.types.VIEW3D_MT_mirror.append(draw_mirror_menu)


def unregister():
    bpy.types.VIEW3D_MT_mirror.remove(draw_mirror_menu)
    remove_handler(bpy.app.handlers.depsgraph_update_post, "positive_mirror_on_depsgraph_update")
    remove_handler(bpy.app.handlers.frame_change_post, "positive_mirror_on_frame_change")
    del bpy.types.Object.positive_mirror_link
    del bpy.types.Scene.positive_mirror
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()