from pxr import Usd, UsdGeom, Gf
import bpy
from bpy_extras.io_utils import ImportHelper, ExportHelper
import os
import mathutils
import math
import sys

def get_gltf_reference_path_for_prim(prim):
    stack = prim.GetPrimStack()
    reference = None
    # Iter through the prim stack from bottom-up, getting the latest appied
    # reference.
    for spec in reversed(stack):
        references = spec.referenceList.GetAppliedItems()
        if len(references) > 0:
            reference = references[0]
    return reference.assetPath


def load(filename):
    stage = Usd.Stage.Open(filename)
    stage.Reload()

    gltf_path_to_collection = {}
    prim_to_object = {}

    prototype_collection = bpy.data.collections.new("prototypes")
    prototype_collection.hide_viewport = True
    bpy.context.scene.collection.children.link(prototype_collection)

    cache = UsdGeom.XformCache()
    
    bpy.context.scene["usd_paths"] = {}
    bpy.context.scene["prototype_object_names"] = {}

    for prim in stage.Traverse():
        bpy.context.scene["usd_paths"][str(prim.GetPath())] = None
        
        data = None
        
        point_instancer = UsdGeom.PointInstancer(prim)
        if point_instancer:
            """
            data = bpy.data.pointclouds.new(prim.GetName())
            positions = data.attributes.new("position", "FLOAT_VECTOR", "POINT")
            for i in range(100):
            #data.attributes.add(positions)
                data.points.link(bpy.types.Point())
            """
        
        object = bpy.data.objects.new(str(prim.GetName()), data)
        bpy.context.scene.collection.objects.link(object)
        
        object.matrix_basis = list(cache.GetLocalTransformation(prim)[0])
          
        prim_to_object[prim] = object
        
        if prim.GetParent() and prim.GetParent() in prim_to_object:
            object.parent = prim_to_object[prim.GetParent()]
            
        if UsdGeom.Imageable(prim).ComputeVisibility() == "invisible":
            object.hide_set(True)
        
        direct_arcs = Usd.PrimCompositionQuery.GetDirectReferences(prim).GetCompositionArcs()
        
        # The prim has an authored reference but it's not listed in the composition arcs,
        # meaning that it's a filfe with no associated usd handler.
        # Todo: this is hacky AF
        if len(direct_arcs) == 0 and prim.HasAuthoredReferences():
            filepath = get_gltf_reference_path_for_prim(prim)
            
            if filepath not in gltf_path_to_collection:
                gltf_collection = bpy.data.collections.new(filepath)
                prototype_collection.children.link(gltf_collection)
                gltf_path_to_collection[filepath] = gltf_collection
                
                scene_path = prim.GetPath().AppendPath("Scenes").AppendPath("Scene")
                
                bpy.ops.import_scene.gltf(filepath=os.path.join(os.path.dirname(filename), filepath))
                
                for gltf_object in bpy.context.selected_objects:
                    # Blender switches gltf objects from Y-up to Z-up, so we need to switch them back.
                    gltf_object.matrix_basis = mathutils.Matrix.Rotation(-math.pi / 2.0, 4, 'X') @ gltf_object.matrix_basis
                    # Todo: not sure whether to support referencing parts of a gltf scene or not.
                    # if so, we need to create one collection for the whole gltf, and then a collection
                    # per-component where each component is centered around the origin.
                    gltf_collection.objects.link(gltf_object)
                    bpy.context.scene.collection.objects.unlink(gltf_object)
                    
                    bpy.context.scene["prototype_object_names"][gltf_object.name] = None
            
            object.instance_type = "COLLECTION"
            object.instance_collection = gltf_path_to_collection[filepath]
    
    for prim in stage.GetPseudoRoot().GetChildren():
        # Set the root objects (hopefully only one root prim)
        # to rotate everything from Y-up to Z-up
        # This means we can use Y-up coordinates more or less natively.
        prim_to_object[prim].matrix_basis @= mathutils.Matrix.Rotation(math.pi / 2.0, 4, 'X')
        prim_to_object[prim]["usd_xform_matrix"] = prim_to_object[prim].matrix_basis
            
def write_override(filename):
    try:
        stage = Usd.Stage.Open(filename)
    except Exception as e:
        stage = Usd.Stage.CreateNew(filename)
    
    unused_usd_paths = dict(bpy.context.scene["usd_paths"])

    for object in bpy.data.objects:
        if object.name in bpy.context.scene["prototype_object_names"]:
            continue 

        name = object.name.replace(".", "_")
        current_object = object
        while current_object.parent is not None:
            current_object = current_object.parent
            name = current_object.name + "/" + name
        name = "/" + name
        
        if name in unused_usd_paths:
            del unused_usd_paths[name]
            #continue

        # Any modifications to root prims need transform fixes. Just skip them for now.
        if object.parent is None:
            continue
        
        prim = stage.DefinePrim(name, "Xform")
        
        if object.instance_collection is not None:
            prim.SetInstanceable(True)
            prim.GetReferences().AddReference(object.instance_collection.name)
        
        pos, rot, scale = object.matrix_basis.decompose()
        
        prim = UsdGeom.Xformable(prim)
        prim.ClearXformOpOrder()
        prim.AddXformOp(UsdGeom.XformOp.TypeTranslate).Set(Gf.Vec3d(list(pos)))
        prim.AddXformOp(UsdGeom.XformOp.TypeOrient).Set(Gf.Quatd(*list(rot)))
        prim.AddXformOp(UsdGeom.XformOp.TypeScale).Set(Gf.Vec3d(list(scale)))
    
    for path in unused_usd_paths:
        stage.OverridePrim(path).SetActive(False)
    
    stage.GetRootLayer().Save()

class OT_TestOpenFilebrowser(bpy.types.Operator, ImportHelper):

    bl_idname = "object.import_usd"
    bl_label = "Import USD"

    filter_glob: bpy.props.StringProperty(
        default='*.usd*',
        options={'HIDDEN'}
    )

    def execute(self, context):
        load(self.filepath)

        return {'FINISHED'}

class WriteOverride(bpy.types.Operator, ExportHelper):
    bl_idname = "object.write_override"  # Unique identifier for buttons and menu items to reference.
    bl_label = "Write Override"  # Display name in the interface.
    bl_options = {"REGISTER", "UNDO"}  # Enable undo for the operator.

    filename_ext = ".usda"

    def execute(self, context):  # execute() is called when running the operator.
        write_override(self.filepath)

        return {"FINISHED"}  # Lets Blender know the operator finished successfully.


class SaveLoadPanel(bpy.types.Panel):
    bl_label = "USD+glTF"
    bl_category = "USD"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.row().operator("object.import_usd")
        box.row().operator("object.write_override")
        

bpy.utils.register_class(OT_TestOpenFilebrowser)
bpy.utils.register_class(SaveLoadPanel)
bpy.utils.register_class(WriteOverride)
