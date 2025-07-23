bl_info = {
    "name": "Spread Sheet",
    "author": "Blender Bob",
    "version": (2, 9), # Incremented version
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Tool > Spread Sheet",
    "description": "Display and apply transforms for objects, bones, and mesh elements in a spreadsheet layout",
    "category": "3D View",
}

import bpy
import bmesh
from mathutils import Vector
from bpy.props import (
    CollectionProperty,
    BoolProperty,
    FloatProperty,
    FloatVectorProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import (
    Panel,
    Operator,
    PropertyGroup,
)

_spreadsheet_last_selected_names = set()
_spreadsheet_last_transforms = {}

# -----------------------------------
# Property Groups
# -----------------------------------

class SpreadSheetItem(PropertyGroup):
    def update_location(self, context):
        if self.obj:
            self.obj.location = self.location

    def update_rotation(self, context):
        if self.obj:
            if self.obj.rotation_mode == 'QUATERNION':
                self.obj.rotation_quaternion = self.rotation_quaternion
            else:
                self.obj.rotation_euler = self.rotation

    def update_scale(self, context):
        if self.obj:
            self.obj.scale = self.scale

    obj: PointerProperty(name="Object", type=bpy.types.Object)
    location: FloatVectorProperty(
        name="Location", size=3, subtype='TRANSLATION',
        update=update_location
    )
    rotation: FloatVectorProperty(
        name="Rotation", size=3, subtype='EULER',
        update=update_rotation
    )
    rotation_quaternion: FloatVectorProperty(
        name="Quaternion", size=4, subtype='QUATERNION',
        update=update_rotation
    )
    scale: FloatVectorProperty(
        name="Scale", size=3, subtype='XYZ',
        update=update_scale
    )
    chk_loc: BoolProperty(name="", default=True)
    chk_rot: BoolProperty(name="", default=True)
    chk_scale: BoolProperty(name="", default=True)

# --- New Property Group for Bones ---
# This property group stores data for display in the UI.
# Update functions now call dedicated operators to ensure undo support.
class BoneSpreadSheetItem(PropertyGroup):
    # Storing bone name and armature object reference
    armature_obj: PointerProperty(name="Armature Object", type=bpy.types.Object)
    bone_name: StringProperty(name="Bone Name")

    # Bone properties (for display/editing)
    # Location is relative to the bone's rest position (head).
    # Update functions call operators for undo support.
    def update_bone_location(self, context):
        # Check if we have valid references
        if self.armature_obj and self.armature_obj.type == 'ARMATURE' and self.armature_obj.mode == 'POSE' and self.bone_name:
            bone = self.armature_obj.pose.bones.get(self.bone_name)
            if bone:
                # Call the operator to set the location, which supports undo
                bpy.ops.spreadsheet.set_bone_location(
                    armature_name=self.armature_obj.name,
                    bone_name=self.bone_name,
                    loc_x=self.bone_location[0],
                    loc_y=self.bone_location[1],
                    loc_z=self.bone_location[2]
                )

    def update_bone_rotation(self, context):
        # Check if we have valid references
        if self.armature_obj and self.armature_obj.type == 'ARMATURE' and self.armature_obj.mode == 'POSE' and self.bone_name:
            bone = self.armature_obj.pose.bones.get(self.bone_name)
            if bone:
                if bone.rotation_mode == 'QUATERNION':
                    # Call the operator to set quaternion rotation, which supports undo
                    bpy.ops.spreadsheet.set_bone_rotation_quaternion(
                        armature_name=self.armature_obj.name,
                        bone_name=self.bone_name,
                        quat_w=self.bone_rotation_quaternion[0],
                        quat_x=self.bone_rotation_quaternion[1],
                        quat_y=self.bone_rotation_quaternion[2],
                        quat_z=self.bone_rotation_quaternion[3]
                    )
                else:
                    # Call the operator to set euler rotation, which supports undo
                    bpy.ops.spreadsheet.set_bone_rotation_euler(
                        armature_name=self.armature_obj.name,
                        bone_name=self.bone_name,
                        rot_x=self.bone_rotation[0],
                        rot_y=self.bone_rotation[1],
                        rot_z=self.bone_rotation[2]
                    )

    def update_bone_scale(self, context):
        # Check if we have valid references
        if self.armature_obj and self.armature_obj.type == 'ARMATURE' and self.armature_obj.mode == 'POSE' and self.bone_name:
             bone = self.armature_obj.pose.bones.get(self.bone_name)
             if bone:
                 # Call the operator to set the scale, which supports undo
                 bpy.ops.spreadsheet.set_bone_scale(
                     armature_name=self.armature_obj.name,
                     bone_name=self.bone_name,
                     scale_x=self.bone_scale[0],
                     scale_y=self.bone_scale[1],
                     scale_z=self.bone_scale[2]
                 )

    bone_location: FloatVectorProperty(name="Bone Location", size=3, subtype='TRANSLATION',
                                       update=update_bone_location) # Update function calls operator
    bone_rotation: FloatVectorProperty(
        name="Bone Rotation", size=3, subtype='EULER',
        update=update_bone_rotation # Update function calls operator
    )
    bone_rotation_quaternion: FloatVectorProperty(
        name="Bone Quaternion", size=4, subtype='QUATERNION',
        update=update_bone_rotation # Update function calls operator
    )
    bone_scale: FloatVectorProperty(
        name="Bone Scale", size=3, subtype='XYZ',
        update=update_bone_scale # Update function calls operator
    )
    # Checkboxes for bones
    bone_chk_loc: BoolProperty(name="", default=True)
    bone_chk_rot: BoolProperty(name="", default=True)
    bone_chk_scale: BoolProperty(name="", default=True)

class MeshElementItem(PropertyGroup):
    index: StringProperty(name="Index")
    source_object: StringProperty(name="Source Object")

    def update_coord(self, context):
        scn = context.scene
        # Don't update mesh if world mode is active!
        if getattr(scn, "spreadsheet_show_world_coords", False):
            return
        obj = bpy.data.objects.get(self.source_object)
        if obj and obj.type == 'MESH' and obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
            try:
                v = bm.verts[int(self.index)]
                v.co = Vector((self.x, self.y, self.z))
                bmesh.update_edit_mesh(obj.data)
            except Exception:
                pass

    def update_sharp(self, context):
        obj = bpy.data.objects.get(self.source_object)
        if obj and obj.type == 'MESH' and obj.mode == 'EDIT': # Fixed && to and
            bm = bmesh.from_edit_mesh(obj.data)
            try:
                edge = bm.edges[int(self.index)]
                edge.smooth = not self.is_sharp
                bmesh.update_edit_mesh(obj.data, loop_triangles=False)
            except Exception:
                pass

    x: FloatProperty(name="", update=update_coord, precision=6)
    y: FloatProperty(name="", update=update_coord, precision=6)
    z: FloatProperty(name="", update=update_coord, precision=6)
    is_sharp: BoolProperty(name="Sharp", default=False, update=update_sharp)

# -----------------------------------
# Operators for Bone Transform Updates (Undo Support)
# -----------------------------------

class SPREADSHEET_OT_SetBoneLocation(Operator):
    bl_idname = "spreadsheet.set_bone_location"
    bl_label = "Set Bone Location"
    bl_description = "Set the location of a bone (for undo support)"
    bl_options = {'UNDO', 'INTERNAL'} # INTERNAL to hide from search

    armature_name: StringProperty()
    bone_name: StringProperty()
    loc_x: FloatProperty()
    loc_y: FloatProperty()
    loc_z: FloatProperty()

    def execute(self, context):
        armature_obj = bpy.data.objects.get(self.armature_name)
        if not armature_obj or armature_obj.type != 'ARMATURE' or armature_obj.mode != 'POSE':
            return {'CANCELLED'}
        bone = armature_obj.pose.bones.get(self.bone_name)
        if not bone:
            return {'CANCELLED'}
        bone.location = (self.loc_x, self.loc_y, self.loc_z)
        return {'FINISHED'}

class SPREADSHEET_OT_SetBoneRotationEuler(Operator):
    bl_idname = "spreadsheet.set_bone_rotation_euler"
    bl_label = "Set Bone Euler Rotation"
    bl_description = "Set the Euler rotation of a bone (for undo support)"
    bl_options = {'UNDO', 'INTERNAL'}

    armature_name: StringProperty()
    bone_name: StringProperty()
    rot_x: FloatProperty()
    rot_y: FloatProperty()
    rot_z: FloatProperty()

    def execute(self, context):
        armature_obj = bpy.data.objects.get(self.armature_name)
        if not armature_obj or armature_obj.type != 'ARMATURE' or armature_obj.mode != 'POSE':
            return {'CANCELLED'}
        bone = armature_obj.pose.bones.get(self.bone_name)
        if not bone:
            return {'CANCELLED'}
        bone.rotation_euler = (self.rot_x, self.rot_y, self.rot_z)
        return {'FINISHED'}

class SPREADSHEET_OT_SetBoneRotationQuaternion(Operator):
    bl_idname = "spreadsheet.set_bone_rotation_quaternion"
    bl_label = "Set Bone Quaternion Rotation"
    bl_description = "Set the Quaternion rotation of a bone (for undo support)"
    bl_options = {'UNDO', 'INTERNAL'}

    armature_name: StringProperty()
    bone_name: StringProperty()
    quat_w: FloatProperty()
    quat_x: FloatProperty()
    quat_y: FloatProperty()
    quat_z: FloatProperty()

    def execute(self, context):
        armature_obj = bpy.data.objects.get(self.armature_name)
        if not armature_obj or armature_obj.type != 'ARMATURE' or armature_obj.mode != 'POSE':
            return {'CANCELLED'}
        bone = armature_obj.pose.bones.get(self.bone_name)
        if not bone:
            return {'CANCELLED'}
        bone.rotation_quaternion = (self.quat_w, self.quat_x, self.quat_y, self.quat_z)
        return {'FINISHED'}

class SPREADSHEET_OT_SetBoneScale(Operator):
    bl_idname = "spreadsheet.set_bone_scale"
    bl_label = "Set Bone Scale"
    bl_description = "Set the scale of a bone (for undo support)"
    bl_options = {'UNDO', 'INTERNAL'}

    armature_name: StringProperty()
    bone_name: StringProperty()
    scale_x: FloatProperty()
    scale_y: FloatProperty()
    scale_z: FloatProperty()

    def execute(self, context):
        armature_obj = bpy.data.objects.get(self.armature_name)
        if not armature_obj or armature_obj.type != 'ARMATURE' or armature_obj.mode != 'POSE':
            return {'CANCELLED'}
        bone = armature_obj.pose.bones.get(self.bone_name)
        if not bone:
            return {'CANCELLED'}
        bone.scale = (self.scale_x, self.scale_y, self.scale_z)
        return {'FINISHED'}

# -----------------------------------
# Handlers & Refreshers
# -----------------------------------

def selection_change_handler(scene, depsgraph):
    global _spreadsheet_last_selected_names, _spreadsheet_last_transforms
    context = bpy.context # Get current context within handler

    # Only care about OBJECT mode for object spreadsheet refresh
    if context.mode == 'OBJECT':
        current_selected = set(obj.name for obj in context.selected_objects)
        # Track transforms of selected objects
        current_transforms = {
            obj.name: (
                tuple(obj.location),
                tuple(obj.rotation_quaternion) if obj.rotation_mode == 'QUATERNION' else tuple(obj.rotation_euler),
                tuple(obj.scale)
            )
            for obj in context.selected_objects
        }
        # If selection or any transform has changed, refresh
        if (current_selected != _spreadsheet_last_selected_names or
            current_transforms != _spreadsheet_last_transforms):
            _spreadsheet_last_selected_names = current_selected
            _spreadsheet_last_transforms = current_transforms
            refresh_object_list(context)
        # Clear bone list when not in POSE mode
        if context.scene.bone_items:
             context.scene.bone_items.clear()

    elif context.mode == 'EDIT_MESH':
        scn = context.scene
        if getattr(scn, "show_spreadsheet_in_edit_mode", False):
            refresh_mesh_element_list(context)
        else:
            scn.vertex_items.clear()
        # Clear bone list when not in POSE mode
        if context.scene.bone_items:
             context.scene.bone_items.clear()

    elif context.mode == 'POSE':
        # Handle Pose Mode
        if context.active_object and context.active_object.type == 'ARMATURE':
            armature_obj = context.active_object
            current_selected_bone_names = set(bone.name for bone in context.selected_pose_bones)
            # Track transforms of selected bones (location, rotation, scale)
            current_bone_transforms = {}
            for bone in context.selected_pose_bones:
                 # Use location, rotation, scale for tracking
                 loc = tuple(bone.location)
                 if bone.rotation_mode == 'QUATERNION':
                     rot = tuple(bone.rotation_quaternion)
                 else:
                     rot = tuple(bone.rotation_euler)
                 scale = tuple(bone.scale)
                 current_bone_transforms[bone.name] = (loc, rot, scale)

            # If selection or any transform has changed, refresh
            if (current_selected_bone_names != _spreadsheet_last_selected_names or
                current_bone_transforms != _spreadsheet_last_transforms):
                _spreadsheet_last_selected_names = current_selected_bone_names
                _spreadsheet_last_transforms = current_bone_transforms
                refresh_bone_list(context) # This will set the _spreadsheet_refreshing_bones flag internally
        # Clear object and vertex lists when in POSE mode
        if context.scene.spreadsheet_items:
            context.scene.spreadsheet_items.clear()
        if context.scene.vertex_items:
            context.scene.vertex_items.clear()

    else:
        # Clear lists if not in relevant mode
        context.scene.spreadsheet_items.clear()
        context.scene.vertex_items.clear()
        context.scene.bone_items.clear()

def refresh_object_list(context):
    scn = context.scene
    items = scn.spreadsheet_items
    # Backup checkbox states per object name
    checkbox_states = {
        item.obj.name: (
            item.chk_loc,
            item.chk_rot,
            item.chk_scale
        ) for item in items if item.obj
    }
    items.clear()
    sorted_objects = sorted(context.selected_objects, key=lambda obj: obj.name)
    for obj in sorted_objects:
        item = items.add()
        item.obj = obj
        item.location = obj.location
        if obj.rotation_mode == 'QUATERNION':
            item.rotation_quaternion = obj.rotation_quaternion.copy()
        else:
            item.rotation = obj.rotation_euler.copy()
        item.scale = obj.scale
        # Restore previous checkbox states if available
        if obj.name in checkbox_states:
            item.chk_loc, item.chk_rot, item.chk_scale = checkbox_states[obj.name]

def refresh_bone_list(context):
    """Refresh the list of bones in Pose Mode."""
    scn = context.scene
    items = scn.bone_items
    # Backup checkbox states per bone name
    checkbox_states = {
        item.bone_name: (
            item.bone_chk_loc,
            item.bone_chk_rot,
            item.bone_chk_scale
        ) for item in items if item.armature_obj and item.bone_name
    }
    items.clear()

    if not context.active_object or context.active_object.type != 'ARMATURE' or context.mode != 'POSE':
        return

    armature_obj = context.active_object
    sorted_bones = sorted(context.selected_pose_bones, key=lambda bone: bone.name)

    for bone in sorted_bones:
        item = items.add()
        item.armature_obj = armature_obj # Store reference to the armature object
        item.bone_name = bone.name
        # Get bone transforms from pose bone for display
        item.bone_location = bone.location.copy() # Relative location
        if bone.rotation_mode == 'QUATERNION':
            item.bone_rotation_quaternion = bone.rotation_quaternion.copy()
        else:
            item.bone_rotation = bone.rotation_euler.copy()
        item.bone_scale = bone.scale.copy()
        # Restore previous checkbox states if available
        if bone.name in checkbox_states:
            item.bone_chk_loc, item.bone_chk_rot, item.bone_chk_scale = checkbox_states[bone.name]

def refresh_mesh_element_list(context):
    scn = context.scene
    scn.vertex_items.clear()
    scn.bone_items.clear() # Clear bones when entering edit mode
    for obj in context.selected_objects:
        if obj.type != 'MESH' or obj.mode != 'EDIT':
            continue
        bm = bmesh.from_edit_mesh(obj.data)
        select_mode = context.tool_settings.mesh_select_mode[:]
        if select_mode[0]:  # Vertex mode
            for v in bm.verts:
                if v.select:
                    item = scn.vertex_items.add()
                    item.index = str(v.index)
                    item.source_object = obj.name
                    item.x, item.y, item.z = v.co  # Always local, always!
        elif select_mode[1]:  # Edge
            for e in bm.edges:
                if e.select:
                    item = scn.vertex_items.add()
                    item.index = str(e.index)
                    item.source_object = obj.name
                    item.is_sharp = not e.smooth
        elif select_mode[2]:  # Face
            for f in bm.faces:
                if f.select:
                    item = scn.vertex_items.add()
                    item.index = str(f.index)
                    item.source_object = obj.name

# -----------------------------------
# Other Operators (Unchanged)
# -----------------------------------

class SPREADSHEET_OT_ApplyTrans(Operator):
    bl_idname = "spreadsheet.apply_trans"
    bl_label = "Apply"
    bl_description = "Apply transform values from the spreadsheet to the actual objects"
    bl_options = {'UNDO'}

    transform: StringProperty()

    def execute(self, context):
        scn = context.scene
        items = scn.spreadsheet_items
        active_only = getattr(scn, f"active_only_{self.transform}", False)
        updated = False
        checked_items = []
        applied_items = []

        # Save checkbox states before doing anything
        checkbox_backup = {
            item.obj.name: (item.chk_loc, item.chk_rot, item.chk_scale)
            for item in items if item.obj
        }

        # Save object list ONLY if Active Only is ON
        if active_only:
            object_backup = [item.obj for item in items if item.obj]

        # Build object list to apply to
        objects_to_apply = []
        for item in items:
            obj = item.obj
            if not obj:
                continue
            if active_only:
                if self.transform == 'loc' and not item.chk_loc:
                    continue
                if self.transform == 'rot' and not item.chk_rot:
                    continue
                if self.transform == 'scale' and not item.chk_scale:
                    continue
            objects_to_apply.append(obj)
            checked_items.append(obj.name)

        # Apply in batch
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects_to_apply:
            obj.select_set(True)
        if objects_to_apply:
            context.view_layer.objects.active = objects_to_apply[0]
            try:
                if self.transform == 'loc':
                    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
                elif self.transform == 'rot':
                    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
                elif self.transform == 'scale':
                    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
                applied_items = [obj.name for obj in objects_to_apply]
                updated = True
            except Exception as e:
                self.report({'WARNING'}, f"Transform apply failed: {e}")

        # Restore checkbox states
        for item in scn.spreadsheet_items:
            if item.obj and item.obj.name in checkbox_backup:
                item.chk_loc, item.chk_rot, item.chk_scale = checkbox_backup[item.obj.name]

        # Restore full list if Active Only caused a refresh
        if active_only:
            scn.spreadsheet_items.clear()
            for obj in object_backup:
                item = scn.spreadsheet_items.add()
                item.obj = obj
                item.location = obj.location.copy()
                if obj.rotation_mode == 'QUATERNION':
                    item.rotation_quaternion = obj.rotation_quaternion.copy()
                else:
                    item.rotation = obj.rotation_euler.copy()
                item.scale = obj.scale.copy()
                chk_loc, chk_rot, chk_scale = checkbox_backup.get(obj.name, (True, True, True))
                item.chk_loc = chk_loc
                item.chk_rot = chk_rot
                item.chk_scale = chk_scale

        if updated:
            self.report({'INFO'}, f"{self.transform.capitalize()} applied.")
        else:
            self.report({'WARNING'}, "No transform was applied.")
        return {'FINISHED'}

# --- Modified Operator for Clearing Bone Transforms ---
class SPREADSHEET_OT_ClearBoneTrans(Operator):
    bl_idname = "spreadsheet.clear_bone_trans"
    bl_label = "Clear Bone Transform"
    bl_description = "Clear (reset to default) selected bone transform properties"
    bl_options = {'UNDO'}

    transform: StringProperty() # 'loc', 'rot', or 'scale'

    def execute(self, context):
        scn = context.scene
        items = scn.bone_items
        active_only = getattr(scn, f"active_only_bone_{self.transform}", False)
        updated = False
        checked_items = []
        cleared_items = []

        if not context.active_object or context.active_object.type != 'ARMATURE' or context.mode != 'POSE':
            self.report({'WARNING'}, "Not in Pose Mode or no active Armature.")
            return {'CANCELLED'}

        armature_obj = context.active_object

        # Save checkbox states before doing anything (optional)
        checkbox_backup = {
            item.bone_name: (item.bone_chk_loc, item.bone_chk_rot, item.bone_chk_scale)
            for item in items if item.armature_obj and item.bone_name
        }

        # Build list of bones to clear
        bones_to_clear = [] # Store PoseBone objects
        for item in items:
            if not item.armature_obj or item.armature_obj != armature_obj or not item.bone_name:
                continue
            bone = armature_obj.pose.bones.get(item.bone_name)
            if not bone:
                continue

            if active_only:
                if self.transform == 'loc' and not item.bone_chk_loc:
                    continue
                if self.transform == 'rot' and not item.bone_chk_rot:
                    continue
                if self.transform == 'scale' and not item.bone_chk_scale:
                    continue

            bones_to_clear.append(bone)
            checked_items.append(bone.name)

        if not bones_to_clear:
             self.report({'WARNING'}, f"No bones selected for {self.transform} clear.")
             return {'CANCELLED'}

        # Clear the transforms directly on the pose bones
        try:
            for bone in bones_to_clear:
                if self.transform == 'loc':
                    bone.location = (0.0, 0.0, 0.0)
                elif self.transform == 'rot':
                    if bone.rotation_mode == 'QUATERNION':
                        bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0) # Identity quaternion
                    else:
                        bone.rotation_euler = (0.0, 0.0, 0.0)
                elif self.transform == 'scale':
                    bone.scale = (1.0, 1.0, 1.0)
            cleared_items = [bone.name for bone in bones_to_clear]
            updated = True
        except Exception as e:
            self.report({'WARNING'}, f"Bone transform clear failed: {e}")
            return {'CANCELLED'}

        if updated:
            self.report({'INFO'}, f"Bone {self.transform.capitalize()} cleared.")
            # Refresh the list to reflect new values
            refresh_bone_list(context)
        else:
            self.report({'WARNING'}, f"No bone {self.transform} was cleared.")

        return {'FINISHED'}

class SPREADSHEET_OT_select_vertex(Operator):
    bl_idname = "spreadsheet.select_vertex"
    bl_label = "Select Mesh Element"
    bl_description = "Select and highlight a single mesh element"

    index: StringProperty()
    object_name: StringProperty()

    def execute(self, context):
        obj = bpy.data.objects.get(self.object_name)
        if not obj:
            return {'CANCELLED'}

        # OBJECT MODE: deselect all, select and activate only the target object
        if context.mode == 'OBJECT':
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            return {'FINISHED'}

        # EDIT MESH MODE: select mesh element
        if context.mode == 'EDIT_MESH' and obj.type == 'MESH' and obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            # Deselect all
            for v in bm.verts:
                v.select = False
            for e in bm.edges:
                e.select = False
            for f in bm.faces:
                f.select = False

            i = int(self.index)
            mode = context.tool_settings.mesh_select_mode
            try:
                if mode[0] and i < len(bm.verts):
                    bm.verts[i].select = True
                elif mode[1] and i < len(bm.edges):
                    bm.edges[i].select = True
                elif mode[2] and i < len(bm.faces):
                    bm.faces[i].select = True
            except IndexError:
                self.report({'WARNING'}, f"Invalid element index: {i}")
                return {'CANCELLED'}

            bmesh.update_edit_mesh(obj.data)
            return {'FINISHED'}

        return {'CANCELLED'}

# --- New Operator for Selecting Bones ---
class SPREADSHEET_OT_select_bone(Operator):
    bl_idname = "spreadsheet.select_bone"
    bl_label = "Select Bone"
    bl_description = "Select and highlight a bone in Pose Mode"

    bone_name: StringProperty()
    armature_name: StringProperty() # Name of the armature object

    def execute(self, context):
        armature_obj = bpy.data.objects.get(self.armature_name)
        if not armature_obj or armature_obj.type != 'ARMATURE':
            self.report({'WARNING'}, "Invalid armature object.")
            return {'CANCELLED'}

        if context.mode != 'POSE' or context.active_object != armature_obj:
             # Switch to Pose Mode if not already
             bpy.context.view_layer.objects.active = armature_obj
             bpy.ops.object.mode_set(mode='POSE')

        bone = armature_obj.data.bones.get(self.bone_name) # Use armature.data.bones for selection
        if not bone:
            self.report({'WARNING'}, f"Bone '{self.bone_name}' not found.")
            return {'CANCELLED'}

        # Deselect all bones
        bpy.ops.pose.select_all(action='DESELECT')
        # Select the target bone
        bone.select = True # Correct way to select a bone
        # Make it the active bone
        armature_obj.data.bones.active = bone # Correct way to set active bone

        return {'FINISHED'}

# -----------------------------------
# UI Panel
# -----------------------------------

class SPREADSHEET_PT_MainPanel(Panel):
    bl_label = "Spread Sheet"
    bl_idname = "SPREADSHEET_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'

    def draw(self, context):
        layout = self.layout
        scn = context.scene

        # --- Pose Mode: Show bone spreadsheet ---
        if context.mode == 'POSE':
            if not scn.bone_items:
                layout.label(text="No bones selected.")
                return
            row = layout.row(align=True)
            row.prop(scn, "enable_pose_spreadsheet", text="Enable Spreadsheet")
            if not scn.enable_pose_spreadsheet:
                return


            # Header
            header = layout.row(align=True)
            header.scale_x = 1 # Adjusted scale for 4 columns
            header.label(text="Bone")
            header.scale_x = .8 
            header.label(text="Location")
            #header.label(text="")
            header.label(text="Rotation")
            #header.label(text="")
            header.label(text="Scale")
            #header.label(text="")

            # Bone Items
            for item in scn.bone_items:
                row = layout.row(align=True)
                row.scale_x = 2.5 # Adjusted scale for 4 columns
                # Display bone name
                row.label(text=item.bone_name if item.bone_name else "")
                # Select Bone Button
                if item.armature_obj and item.bone_name:
                    op = row.operator("spreadsheet.select_bone", text="", icon='RESTRICT_SELECT_OFF', emboss=False)
                    op.bone_name = item.bone_name
                    op.armature_name = item.armature_obj.name
                row.scale_x = 1.5
                # Location
                row.prop(item, "bone_location", text="")
                row.prop(item, "bone_chk_loc", text="")
                # Rotation
                if item.armature_obj and item.armature_obj.type == 'ARMATURE' and item.armature_obj.mode == 'POSE':
                    bone = item.armature_obj.pose.bones.get(item.bone_name)
                    if bone:
                        if bone.rotation_mode == 'QUATERNION':
                             row.prop(item, "bone_rotation_quaternion", text="")
                             #row.label(text="(Quat)")
                        else:
                             row.prop(item, "bone_rotation", text="")
                             #row.label(text="")
                    else:
                         row.label(text="Invalid")
                         row.label(text="")
                else:
                     row.label(text="N/A")
                     row.label(text="")
                # Rotation Checkbox
                row.prop(item, "bone_chk_rot", text="")
                # Scale
                row.prop(item, "bone_scale", text="")
                # Scale Checkbox
                row.prop(item, "bone_chk_scale", text="")

            # Active Only and Apply buttons for Bones
            active_row = layout.row(align=True)
            active_row.scale_x = 2.5
            active_row.label(text="")
            active_row.scale_x = 1.5
            active_row.prop(scn, "active_only_bone_loc", text="Active Only")
            active_row.label(text="")
            active_row.prop(scn, "active_only_bone_rot", text="Active Only")
            active_row.label(text="")
            active_row.prop(scn, "active_only_bone_scale", text="Active Only")
            active_row.label(text="")

            clear_row = layout.row(align=True)
            clear_row.scale_x = 2.5
            clear_row.label(text="")
            clear_row.scale_x = 1.6
            # Clear Buttons (keeping these as they are useful)
            clear_row.operator("spreadsheet.clear_bone_trans", text="Clear Loc").transform = 'loc'
            clear_row.label(text="")
            clear_row.operator("spreadsheet.clear_bone_trans", text="Clear Rot").transform = 'rot'
            clear_row.label(text="")
            clear_row.operator("spreadsheet.clear_bone_trans", text="Clear Scale").transform = 'scale'
            clear_row.label(text="")
            return # Stop drawing, Pose Mode UI is complete

        # --- Edit Mode: Show mesh element spreadsheet, else object spreadsheet ---
        if context.mode == 'EDIT_MESH':
            row = layout.row(align=True)
            row.prop(scn, "show_spreadsheet_in_edit_mode", text="Enable Spreadsheet")
            row.prop(scn, "spreadsheet_show_world_coords", text="World Space")
            if not scn.show_spreadsheet_in_edit_mode:
                return  # Do NOT calculate or display the mesh spreadsheet if unchecked

            grouped = {}
            for v in scn.vertex_items:
                grouped.setdefault(v.source_object, []).append(v)

            select_mode = context.tool_settings.mesh_select_mode
            for obj_name, items in grouped.items():
                layout.label(text=obj_name)
                if select_mode[1]:  # Edge mode
                    # Add a "Sharp" column header, left-aligned
                    header_row = layout.row(align=True)
                    header_row.split(factor=0.15, align=True).label(text="")
                    header_row.split(factor=0.1, align=True).label(text="")
                    sharp_col = header_row.row(align=True)
                    sharp_col.alignment = 'LEFT'
                    sharp_col.label(text="Sharp", icon='MOD_EDGESPLIT')

                for v in items:
                    split = layout.split(factor=0.12, align=True)
                    split.alignment = 'CENTER'
                    col1 = split.row(align=True)
                    col1.alignment = 'RIGHT'
                    col1.label(text=v.index)
                    split2 = split.split(factor=0.06, align=True)
                    col2 = split2.row(align=True)
                    col2.alignment = 'CENTER'
                    op = col2.operator("spreadsheet.select_vertex", text="", icon='RESTRICT_SELECT_OFF', emboss=False)
                    op.index = v.index
                    op.object_name = v.source_object
                    col3 = split2.row(align=True)
                    show_world = scn.spreadsheet_show_world_coords
                    obj = bpy.data.objects.get(v.source_object)
                    if select_mode[0]:  # Vertex mode
                        if show_world and obj:
                            local = Vector((v.x, v.y, v.z))
                            world = obj.matrix_world @ local
                            col3.label(text=f"{world.x:.4f}")
                            col3.label(text=f"{world.y:.4f}")
                            col3.label(text=f"{world.z:.4f}")
                        else:
                            col3.prop(v, "x", text="")
                            col3.prop(v, "y", text="")
                            col3.prop(v, "z", text="")
                    elif select_mode[1]:  # Edge mode
                        col3.prop(v, "is_sharp", text="")  # true checkbox

            return  # <---- THIS is crucial! Prevents Object Mode spreadsheet from showing in Edit Mode.

        # --- Object Mode: Show object spreadsheet ---
        if not scn.spreadsheet_items:
            return
        row = layout.row(align=True)
        row.prop(scn, "enable_object_spreadsheet", text="Enable Spreadsheet")
        if not scn.enable_object_spreadsheet:
            return


        header = layout.row(align=True)
        header.scale_x = 1.0
        header.label(text="Object")
        header.scale_x = 0.8
        header.label(text="Location")
        #header.label(text="")
        header.label(text="Rotation")
        #header.label(text="")
        header.label(text="Scale")
        #header.label(text="")

        for item in scn.spreadsheet_items:
            row = layout.row(align=True)
            row.scale_x = 1.5
            row.label(text=item.obj.name if item.obj else "")
            if item.obj:
                op = row.operator("spreadsheet.select_vertex", text="", icon='RESTRICT_SELECT_OFF', emboss=False)
                op.index = "0"
                op.object_name = item.obj.name
            row.scale_x = 1
            row.prop(item, "location", text="")
            row.prop(item, "chk_loc", text="")
            if item.obj:
                if item.obj.rotation_mode == 'QUATERNION':
                    row.prop(item, "rotation_quaternion", text="")
                    #row.label(text="(Quat)")
                else:
                    row.prop(item, "rotation", text="")
                    #row.label(text="")
            row.prop(item, "chk_rot", text="")
            row.prop(item, "scale", text="")
            row.prop(item, "chk_scale", text="")

        active_row = layout.row(align=True)
        active_row.scale_x = 3.0
        active_row.label(text="")
        active_row.scale_x = 1.25
        active_row.prop(scn, "active_only_loc", text="Active Only")
        active_row.label(text="")
        active_row.prop(scn, "active_only_rot", text="Active Only")
        active_row.label(text="")
        active_row.prop(scn, "active_only_scale", text="Active Only")
        active_row.label(text="")

        apply_row = layout.row(align=True)
        apply_row.scale_x = 3.0
        apply_row.label(text="")
        apply_row.scale_x = 1.3
        apply_row.operator("spreadsheet.apply_trans", text="Apply Locations").transform = 'loc'
        apply_row.label(text="")
        apply_row.operator("spreadsheet.apply_trans", text="Apply Rotations").transform = 'rot'
        apply_row.label(text="")
        apply_row.operator("spreadsheet.apply_trans", text="Apply Scales").transform = 'scale'
        apply_row.label(text="")

# -----------------------------------
# Register / Unregister
# -----------------------------------

# Add the new operators to the classes tuple
classes = (
    SpreadSheetItem,
    BoneSpreadSheetItem,
    MeshElementItem,
    SPREADSHEET_OT_SetBoneLocation,       # <-- New
    SPREADSHEET_OT_SetBoneRotationEuler,  # <-- New
    SPREADSHEET_OT_SetBoneRotationQuaternion, # <-- New
    SPREADSHEET_OT_SetBoneScale,          # <-- New
    SPREADSHEET_OT_ApplyTrans,
    SPREADSHEET_OT_ClearBoneTrans,
    SPREADSHEET_OT_select_vertex,
    SPREADSHEET_OT_select_bone,
    SPREADSHEET_PT_MainPanel,
)

def register():
    bpy.types.Scene.spreadsheet_show_world_coords = BoolProperty(
        name="World Space (not editable)",
        description="Display vertex coordinates in world space (read-only)",
        default=False
    )

    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.spreadsheet_items = CollectionProperty(type=SpreadSheetItem)
    bpy.types.Scene.bone_items = CollectionProperty(type=BoneSpreadSheetItem)
    bpy.types.Scene.vertex_items = CollectionProperty(type=MeshElementItem)

    bpy.types.Scene.show_spreadsheet_in_edit_mode = BoolProperty(
        name="Show Spreadsheet in Edit Mode",
        description="Enable to show the spreadsheet when in mesh Edit Mode (can be slow with many elements)",
        default=False
    )

    for prop in ('loc', 'rot', 'scale'):
        setattr(bpy.types.Scene, f"active_only_{prop}", BoolProperty(name="", default=False))

    for prop in ('bone_loc', 'bone_rot', 'bone_scale'):
         setattr(bpy.types.Scene, f"active_only_{prop}", BoolProperty(name="", default=False))

    if selection_change_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(selection_change_handler)
        
    bpy.types.Scene.enable_object_spreadsheet = BoolProperty(
        name="Enable Object Mode Spreadsheet", default=True)

    bpy.types.Scene.enable_pose_spreadsheet = BoolProperty(
        name="Enable Pose Mode Spreadsheet", default=True)
            

def unregister():
    del bpy.types.Scene.spreadsheet_show_world_coords

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.spreadsheet_items
    del bpy.types.Scene.bone_items
    del bpy.types.Scene.vertex_items

    del bpy.types.Scene.show_spreadsheet_in_edit_mode

    for prop in ('loc', 'rot', 'scale'):
        delattr(bpy.types.Scene, f"active_only_{prop}")

    for prop in ('bone_loc', 'bone_rot', 'bone_scale'):
         delattr(bpy.types.Scene, f"active_only_{prop}")

    if selection_change_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(selection_change_handler)
        
    del bpy.types.Scene.enable_object_spreadsheet
    del bpy.types.Scene.enable_pose_spreadsheet
    

if __name__ == "__main__":
    register()