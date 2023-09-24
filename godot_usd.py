from pxr import Usd, UsdGeom, Gf
import godot_parser
import sys
import json
from utils import get_gltf_reference_path_for_prim

def flatten_transposed_matrix(matrix):
    matrix = matrix.GetTranspose()
    return (scalar for i in range(3) for scalar in matrix[i])

def flatten_matrix(matrix):
    return (scalar for vector in matrix for scalar in vector[:3])

scene = godot_parser.GDScene()

gltf_to_id = {}

stage = Usd.Stage.Open(sys.argv[1])

cache = UsdGeom.XformCache()

prim_to_node = {}
used_paths = set()

def add_ext(path, type = "PackedScene"):
    if not path in gltf_to_id:
        gltf_to_id[path] = scene.add_ext_resource("res://" + path, type).id
    return gltf_to_id[path]

with scene.use_tree() as tree:
    for prim in stage.Traverse():
        if UsdGeom.Imageable(prim).ComputeVisibility() == "invisible":
            continue

        used_paths.add(str(prim.GetPath()))

        node_type = "Node3D"
        instance = None
        data = {}
        children = []

        point_instancer = UsdGeom.PointInstancer(prim)

        if point_instancer:
            node_type = "Node3D"
            positions = point_instancer.GetPositionsAttr().Get()
            orientations = point_instancer.GetOrientationsAttr().Get()
            scales = point_instancer.GetScalesAttr().Get()

            matrices = [Gf.Matrix4d().SetScale(Gf.Vec3d(scales[i])) * Gf.Matrix4d(Gf.Rotation(orientations[i]), Gf.Vec3d(positions[i])) for i in range(len(positions))]
            #values = [value for matrix in matrices for value in flatten_transposed_matrix(matrix)]

            # Need to handle prototypes as relationships to referenced prims
            prototypes = point_instancer.GetPrototypesRel()
            target = prototypes.GetTargets()[0]
            proto_prim = stage.GetPrimAtPath(target)
            asset = get_gltf_reference_path_for_prim(proto_prim)
            # This isn't used in godot as it instances models in it's own mesh format extracted from gltfs.
            #data["metadata/instanced_mesh"] = godot_parser.ExtResource(add_ext(str(asset)))

            #sub_res = scene.add_sub_resource("MultiMesh")
            #sub_res["transform_format"] = 1
            #sub_res["instance_count"] = len(positions)
            #sub_res["buffer"] = godot_parser.GDObject("PackedFloat32Array", *values)

            #mesh = prim.GetAttribute("godot_mesh").Get()
            asset_res = add_ext(asset)#add_ext(mesh, type = "ArrayMesh")
            #mesh = godot_parser.ExtResource(mesh)
            #sub_res["mesh"] = godot_parser.ExtResource(add_ext(mesh, type = "ArrayMesh"))
            #data["multimesh"] = godot_parser.SubResource(sub_res.id)

            for i, matrix in enumerate(matrices):
                node = godot_parser.Node(f"{prim.GetName()}_{i}", instance=asset_res, type="Node3D")
                node["transform"] = godot_parser.objects.GDObject("Transform3D", *flatten_matrix(matrix))
                children.append(node)


        if prim.HasAuthoredReferences():
            direct_arcs = Usd.PrimCompositionQuery.GetDirectReferences(
                prim
            ).GetCompositionArcs()

            gltf = get_gltf_reference_path_for_prim(prim)
            instance = add_ext(gltf)
            node_type = None

        matrix = cache.GetLocalTransformation(prim)[0]
        data["transform"] = godot_parser.objects.GDObject("Transform3D", *flatten_matrix(matrix))

        node = godot_parser.Node(prim.GetName(), instance=instance, type=node_type)

        for key, value in data.items():
            node[key] = value

        for child in children:
            node.add_child(child)

        if prim.GetParent() == stage.GetPseudoRoot():
            tree.root = node
        else:
            prim_to_node[prim.GetParent()].add_child(
                node
            )

        prim_to_node[prim] = node

scene.write(sys.argv[2])

open("import.json", "w").write(json.dumps(list(used_paths)))
