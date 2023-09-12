# coding: utf-8
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf
import sys
import bpy
import math

def sanitise(name):
    replacements = {" ": "_", ".": "_", "[": "", "]": ""}

    for a, b in replacements.items():
        name = name.replace(a, b)

    return name

blend_file = sys.argv[1]

bpy.ops.wm.open_mainfile(filepath=blend_file)

root = Sdf.Path("/root")
prototypes_path = root.AppendPath("_prototypes")

stage = Usd.Stage.CreateNew("stage.usda")

root_prim = stage.DefinePrim(root)
stage.SetDefaultPrim(root_prim)
stage.SetMetadata("upAxis", "Z")

root_collections = list(bpy.context.scene.collection.children)
#assert len(root_collections) == 1
root_collection = root_collections[0]

traversed_instance_collections = set()

stack = []
for object in root_collection.objects:
    if object.parent is None:
        stack.append((object, root))
for child_collection in root_collection.children:
    stack.append((child_collection, root))

UsdGeom.Imageable(stage.DefinePrim(prototypes_path, "Xform")).CreateVisibilityAttr("invisible")


while len(stack) > 0:
    (object, parent_path) = stack.pop()

    if type(object) is bpy.types.Collection:
        path = parent_path.AppendPath(sanitise(object.name))
        prim = stage.DefinePrim(path, "Xform")

        for object in object.objects:
            stack.append((object, path))
            pass

        for child_collection in object.children:
            stack.append((child_collection, path))

        continue

    if (object.type == "CAMERA" or object.type == "LIGHT") and len(object.children) == 0:
        continue

    path = parent_path.AppendPath(sanitise(object.name))
    prim = stage.DefinePrim(path, "Xform")

    UsdGeom.Xformable(prim).AddXformOp(UsdGeom.XformOp.TypeTransform).Set(Gf.Matrix4d(list(object.matrix_local.transposed())))

    if object.type == "MESH":
        prim.SetInstanceable(True)
        prim.GetReferences().AddReference("meshes.usda", "/" + sanitise(object.data.name_full))

    if object.instance_collection is not None:
        path = prototypes_path.AppendPath(sanitise(object.instance_collection.name))

        # We only need to do this check for traversed instances because `AddXformOp`
        # can't be called with the same transform on the same prim twice.
        # Avoiding traversing instances multiple times is nice for perf too.
        if object.instance_collection not in traversed_instance_collections:
            traversed_instance_collections.add(object.instance_collection)
            # This is just here to avoid warnings.
            stage.DefinePrim(path, "Xform")
            stack.append((object.instance_collection, prototypes_path))

        prim.SetInstanceable(True)
        prim.GetReferences().AddInternalReference(path)

    for object in object.children:
        stack.append((object, path))

stage.GetRootLayer().Save()
