from pxr import Usd, UsdGeom, Gf
import bpy
from bpy_extras.io_utils import ImportHelper, ExportHelper
import os
import mathutils
import math


def get_gltf_reference_path_for_prim(prim):
    stack = prim.GetPrimStack()
    prim_spec = stack[-1]
    references = prim_spec.referenceList.GetAppliedItems()
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

    for prim in stage.Traverse():
        object = bpy.data.objects.new(str(prim.GetPath()), None)
        bpy.context.scene.collection.objects.link(object)

        object.matrix_basis = list(cache.GetLocalTransformation(prim)[0])

        object["usd_prim_path"] = str(prim.GetPath())
        object["usd_xform_matrix"] = object.matrix_basis
        # Keep around a set of the blender names of children this object has
        # Blender doesn't support sets for custom properties so we use a dict of 'None's
        # instead.
        object["blender_children"] = {}

        prim_to_object[prim] = object

        if prim.GetParent() and prim.GetParent() in prim_to_object:
            object.parent = prim_to_object[prim.GetParent()]
            object.parent["blender_children"][object.name] = None

        if UsdGeom.Imageable(prim).GetVisibilityAttr().Get() == "invisible":
            object.hide_set(True)

        direct_arcs = Usd.PrimCompositionQuery.GetDirectReferences(
            prim
        ).GetCompositionArcs()

        # The prim has an authored reference but it's not listed in the composition arcs,
        # meaning that it's a filfe with no associated usd handler.
        # Todo: this is hacky AF
        if len(direct_arcs) == 0 and prim.HasAuthoredReferences():
            filepath = get_gltf_reference_path_for_prim(prim)

            object["usd_references_gltf"] = filepath

            if filepath not in gltf_path_to_collection:
                gltf_collection = bpy.data.collections.new(filepath)
                prototype_collection.children.link(gltf_collection)
                gltf_path_to_collection[filepath] = gltf_collection

                scene_path = prim.GetPath().AppendPath("Scenes").AppendPath("Scene")

                bpy.ops.import_scene.gltf(
                    filepath=os.path.join(os.path.dirname(filename), filepath)
                )

                for gltf_object in bpy.context.selected_objects:
                    # Blender switches gltf objects from Y-up to Z-up, so we need to switch them back.
                    gltf_object.matrix_basis = (
                        gltf_object.matrix_basis
                        @ mathutils.Matrix.Rotation(-math.pi / 2.0, 4, "X")
                    )
                    # Todo: not sure whether to support referencing parts of a gltf scene or not.
                    # if so, we need to create one collection for the whole gltf, and then a collection
                    # per-component where each component is centered around the origin.
                    gltf_collection.objects.link(gltf_object)
                    bpy.context.scene.collection.objects.unlink(gltf_object)

            object.instance_type = "COLLECTION"
            object.instance_collection = gltf_path_to_collection[filepath]

    for prim in stage.GetPseudoRoot().GetChildren():
        # Set the root objects (hopefully only one root prim)
        # to rotate everything from Y-up to Z-up
        # This means we can use Y-up coordinates more or less natively.
        prim_to_object[prim].matrix_basis @= mathutils.Matrix.Rotation(
            math.pi / 2.0, 4, "X"
        )
        prim_to_object[prim]["usd_xform_matrix"] = prim_to_object[prim].matrix_basis


def write_override(filename):
    try:
        stage = Usd.Stage.Open(filename)
    except Exception as e:
        stage = Usd.Stage.CreateNew(filename)

    for object in bpy.data.objects:
        if not "usd_xform_matrix" in object:
            continue

        for child in object.children:
            if child.name not in object["blender_children"]:
                # Replace the name here to avoid naming problems in usd.
                # The child name seems to have some delay with being replaced so we
                # use this temporary replaced variable.
                replaced = child.name.replace(".", "_")
                child.name = replaced
                prim = stage.DefinePrim(replaced, "Xform")

                if "usd_references_gltf" in child:
                    prim.SetInstanceable(True)
                    prim.GetReferences().AddReference(child["usd_references_gltf"])

                prim = UsdGeom.Xformable(prim)

                pos, rot, scale = child.matrix_basis.decompose()

                prim.ClearXformOpOrder()
                prim.AddXformOp(UsdGeom.XformOp.TypeTranslate).Set(Gf.Vec3d(list(pos)))
                prim.AddXformOp(UsdGeom.XformOp.TypeOrient).Set(Gf.Quatd(*list(rot)))
                prim.AddXformOp(UsdGeom.XformOp.TypeScale).Set(Gf.Vec3d(list(scale)))

                # Do this last so that fields don't get changed if an error occurs
                child["usd_prim_path"] = child.name
                object["blender_children"][child.name] = None
                child["usd_xform_matrix"] = child.matrix_basis

        list_xform_matrix = [list(x) for x in object["usd_xform_matrix"]]
        list_basis_matrix = [list(x) for x in object.matrix_basis]
        if list_xform_matrix != list_basis_matrix:
            object["usd_xform_matrix"] = object.matrix_basis
            prim = stage.OverridePrim(object["usd_prim_path"])
            prim = UsdGeom.Xformable(prim)

            pos, rot, scale = object.matrix_basis.decompose()

            prim.ClearXformOpOrder()
            prim.AddXformOp(UsdGeom.XformOp.TypeTranslate).Set(Gf.Vec3d(list(pos)))
            prim.AddXformOp(UsdGeom.XformOp.TypeOrient).Set(Gf.Quatd(*list(rot)))
            prim.AddXformOp(UsdGeom.XformOp.TypeScale).Set(Gf.Vec3d(list(scale)))

    stage.GetRootLayer().Save()


class OT_TestOpenFilebrowser(bpy.types.Operator, ImportHelper):
    bl_idname = "object.import_usd"
    bl_label = "Import USD"

    filter_glob: bpy.props.StringProperty(default="*.usd*", options={"HIDDEN"})

    def execute(self, context):
        load(self.filepath)

        return {"FINISHED"}


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
