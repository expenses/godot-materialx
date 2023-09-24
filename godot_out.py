import sys
import godot_parser
from pxr import Usd, UsdGeom, Gf, Sdf
import json
from utils import get_gltf_reference_path_for_prim

def truncate_vec4(vec4):
    return Gf.Vec3d(vec4[0], vec4[1], vec4[2])

def extract_scale(matrix):
    a = truncate_vec4(matrix.GetColumn(0)).GetLength()
    b = truncate_vec4(matrix.GetColumn(1)).GetLength()
    c = truncate_vec4(matrix.GetColumn(2)).GetLength()
    return Gf.Vec3d(a, b, c)

def godot_matrix_to_usd(list):
    return [
        list[0], list[1], list[2], 0.0,
        list[3], list[4], list[5], 0.0,
        list[6], list[7], list[8], 0.0,
        list[9], list[10], list[11], 1.0,
    ]

file = godot_parser.GDScene.load(sys.argv[1])

stage = Usd.Stage.Open(sys.argv[3])
xform_cache = UsdGeom.XformCache()

# Represents the set of usd paths that were previously imported.
unused_paths = set(json.loads(open("import.json").read()))

edit_target = stage.GetEditTargetForLocalLayer(0)
stage.SetEditTarget(edit_target)

for node in file.find_all():
    if type(node) is not godot_parser.GDNodeSection:
        continue
    
    transform = node.get("transform")
    if transform:
        transform = Gf.Matrix4d(*godot_matrix_to_usd(transform.args))
    else:
        transform = Gf.Matrix4d()

    path = node.name
    current_node = node
    while True:
        if current_node.parent == ".":
            path = "/root/" + path
            break
        elif current_node.parent is None:
            path = "/root"
            break
        else:
            current_node = file.find_node(name=node.parent)
            # Todo: the godot node tree doesn't perfectly map to usd
            # as usd doesn't let you add children to an instanceable prim.
            if current_node.instance:
                assert False
            path = current_node.name + "/" + path
            continue

    if path in unused_paths:
        unused_paths.remove(path)

    # We're currently outputting point instancer points as individual instances
    # as this lets godot perform frustum culling and is generally faster.
    # We don't want thse instances to get put back into the stage so we just ignore any
    # children of point instancers. Point instancers shouldn't have children anyway so this
    # works out fine.
    if UsdGeom.PointInstancer(stage.GetPrimAtPath(Sdf.Path(path).GetParentPath())):
        continue

    prim = stage.GetPrimAtPath(path) or stage.DefinePrim(path, "Xform")
    
    base_transform = xform_cache.GetLocalTransformation(prim)[0]
 
    if node.instance:
        resource_path = file.find_ext_resource(id=node.instance).path
        instance_asset = resource_path.split("res://")[-1]
        if not prim.HasAuthoredReferences() or get_gltf_reference_path_for_prim(prim) != instance_asset:
            # Not sure how to handle instancing subscenes yet.
            if not instance_asset.endswith(".tscn"):
                prim.SetInstanceable(True)
                prim.GetReferences().AddReference(instance_asset)

    if transform != base_transform:
        prim = UsdGeom.Xformable(prim)
        prim.ClearXformOpOrder()
        prim.AddXformOp(UsdGeom.XformOp.TypeTransform).Set(transform)

        # Don't want to support multimeshes created in godot yet.
        """
        sub_res = file.find_sub_resource(id=node.get("multimesh").id)

        instance_count = sub_res.get("instance_count")
        buffer = sub_res.get("buffer").args
        matrices = [Gf.Matrix4d(*godot_matrix_to_usd(buffer[i * 12:(i + 1) * 12])) for i in range(instance_count)]

        mesh = file.find_ext_resource(id = node.get("metadata/instanced_mesh").id)
        asset = mesh.path.split("res://")[-1]

        # point instancers use relationships, not references which means we have to define an internal prim
        # to be instanced. Annoying but not the end of the world.
        UsdGeom.Imageable(stage.DefinePrim("/root/prototypes", "Xform")).CreateVisibilityAttr("invisible")
        instanced_prim = stage.DefinePrim("/root/prototypes/" + asset.replace(".", "_"), "Xform")
        instanced_prim.SetInstanceable(True)
        instanced_prim.GetReferences().AddReference(asset)


        prim = UsdGeom.PointInstancer.Define(stage, path)

        print(extract_scale(matrices[0]))

        prim.CreatePositionsAttr([matrix.ExtractTranslation() for matrix in matrices])
        prim.CreateOrientationsAttr([Gf.Quath(matrix.ExtractRotationQuat()) for matrix in matrices])
        prim.CreateScalesAttr([extract_scale(matrix) for matrix in matrices])
        prim.CreateProtoIndicesAttr([0] * instance_count)
        prim.CreatePrototypesRel().AddTarget(instanced_prim.GetPath())
        """

for path in unused_paths:
    print(path)
    stage.OverridePrim(path).SetActive(False)

edit_target.GetLayer().Export(sys.argv[2])
stage.GetRootLayer().subLayerPaths.insert(0, sys.argv[2])
stage.GetRootLayer().Save()
