import bpy
from pxr import Usd, UsdGeom, Gf, Sdf

depsgraph = bpy.context.evaluated_depsgraph_get()

object_to_id = {}
object_names = []
next_id = 0
points = []
orientations = []
scales = []
proto_indices = []


for object in depsgraph.object_instances:
    if not object.is_instance:
        continue
    
    if not object.instance_object in object_to_id:
        object_to_id[object.instance_object] = next_id
        next_id += 1
        object_names.append(object.instance_object.name)
    
    pos, rot, scale = object.matrix_world.decompose()
    points.append(pos)
    orientations.append(Gf.Quath(*list(rot)))
    proto_indices.append(object_to_id[object.instance_object])
    scales.append(scale)

stage = Usd.Stage.CreateNew("points.usda")
stage.SetMetadata("upAxis", "Z")

prototype_paths = []

UsdGeom.Imageable(stage.DefinePrim("/prototypes", "Xform")).CreateVisibilityAttr("invisible")

for object_name in object_names:
    path = Sdf.Path("/prototypes/" + object_name.replace(".", "_"))
    prototype_paths.append(path)
    stage.DefinePrim(path)

point_instancer = UsdGeom.PointInstancer.Define(stage, "/points")
point_instancer.CreatePositionsAttr(points)
point_instancer.CreateProtoIndicesAttr(proto_indices)
point_instancer.CreateScalesAttr(scales)
point_instancer.CreateOrientationsAttr(orientations)

prototypes_rel = point_instancer.CreatePrototypesRel()

for prototype_path in prototype_paths:
    prototypes_rel.AddTarget(prototype_path)

stage.GetRootLayer().Save()
