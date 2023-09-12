# coding: utf-8
from pxr import Usd, UsdGeom, Sdf, Gf
import sys
import bpy

def sanitise(name):
    replacements = {" ": "__", ".": "_", "[": "", "]": ""}

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

root_collection = bpy.context.scene.collection.children["Collection"]

traversed_objects = set()

stack = []
for object in root_collection.objects:
    if object.parent is None:
        stack.append((object, root))
for child_collection in root_collection.children:
    stack.append((child_collection, root))

UsdGeom.Imageable(stage.DefinePrim(prototypes_path, "Xform")).CreateVisibilityAttr("invisible")

while len(stack) > 0:
    (object, parent_path) = stack.pop()

    # Avoid traversing the same object multiple times (you can't set the same xform more than once)
    if object in traversed_objects:
        continue

    traversed_objects.add(object)

    # Collections just create an Xform and add everything then contain.
    if type(object) is bpy.types.Collection:
        path = parent_path.AppendPath(sanitise(object.name))
        prim = stage.DefinePrim(path, "Xform")

        for child in object.objects:
            stack.append((child, path))


        for child in object.children:
            stack.append((child, path))

        continue

    # We don't just cameras/lights currently
    if (object.type == "CAMERA" or object.type == "LIGHT"):
        continue

    path = parent_path.AppendPath(sanitise(object.name))
    prim = stage.DefinePrim(path, "Xform")

    if object.type != "MESH":
        # Transforms on meshes are generally bad as we're referencing in the whole model and transform stack anyway.
        pos, rot, scale = object.matrix_local.decompose()
        UsdGeom.Xformable(prim).AddXformOp(UsdGeom.XformOp.TypeTranslate).Set(Gf.Vec3d(list(pos)))
        UsdGeom.Xformable(prim).AddXformOp(UsdGeom.XformOp.TypeOrient).Set(Gf.Quatd(*list(rot)))
        UsdGeom.Xformable(prim).AddXformOp(UsdGeom.XformOp.TypeScale).Set(Gf.Vec3d(list(scale)))
    else:
        # Add a reference to the mesh object in the meshes file (name_full also gives the source filename)
        prim.SetInstanceable(True)
        prim.GetReferences().AddReference("meshes.usda", "/" + sanitise(object.data.name_full))

    # Instance collections have just one child, which is the collection being instanced.
    if object.instance_collection is not None:
        path = prototypes_path.AppendPath(sanitise(object.instance_collection.name))

        # This is just here to avoid warnings.
        stage.DefinePrim(path, "Xform")
        stack.append((object.instance_collection, prototypes_path))

        prim.SetInstanceable(True)
        prim.GetReferences().AddInternalReference(path)

    for child in object.children:
        stack.append((child, path))

stage.GetRootLayer().Save()
