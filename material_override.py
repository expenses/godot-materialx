# coding: utf-8
from pxr import Usd, UsdGeom, UsdShade, Sdf
import sys

usd_filename = sys.argv[1]
materialx_filename = sys.argv[2]

# Open the source stage and extract metadata

source_stage = Usd.Stage.Open(usd_filename)
up_axis = source_stage.GetMetadata("upAxis")
meters_per_unit = source_stage.GetMetadata("metersPerUnit")

# Open the materialx file as a usd and extract the name of the material.

matx_stage = Usd.Stage.Open(materialx_filename)
material_paths = [x.GetPath() for x in matx_stage.Traverse() if UsdShade.Material(x)]
assert len(material_paths) == 1
material_path = material_paths[0]
relative_path = material_path.MakeRelativePath("/MaterialX")

# Create the stage

stage = Usd.Stage.CreateNew("override.usda")

stage.SetMetadata("upAxis", up_axis)
stage.SetMetadata("metersPerUnit", meters_per_unit)

root = stage.DefinePrim("/root", "Xform")

stage.SetDefaultPrim(root)

root.GetReferences().AddReference(usd_filename)

scope = stage.DefinePrim("/root/MaterialX", "Scope")

scope.GetReferences().AddReference(materialx_filename, "/MaterialX")

mesh_paths = (x.GetPath() for x in stage.Traverse() if UsdGeom.Mesh(x))

for path in mesh_paths:
    over = stage.OverridePrim(path)

    over.GetRelationship("material:binding").SetTargets([Sdf.Path("/root/MaterialX").AppendPath(relative_path)])

stage.GetRootLayer().Save()
