# coding: utf-8
from pxr import Usd, UsdGeom
import MaterialX as mx
import sys

usd_filename = sys.argv[1]
materialx_filename = sys.argv[2]

# Open the source stage and extract metadata

source_stage = Usd.Stage.Open(usd_filename)
up_axis = source_stage.GetMetadata("upAxis")
meters_per_unit = source_stage.GetMetadata("metersPerUnit")

# extract the name of the materialx material.

mat = mx.createDocument()

mx.readFromXmlFile(mat, materialx_filename)

file_materials = mat.getNodes("surfacematerial")
assert len(file_materials) == 1
file_material = file_materials[0]
material_name = file_material.getName()

# Create the stage

stage = Usd.Stage.CreateNew('override.usda')

stage.SetMetadata("upAxis", up_axis)
stage.SetMetadata("metersPerUnit", meters_per_unit)

root = stage.DefinePrim('/root', "Xform")

stage.SetDefaultPrim(root)

root.GetReferences().AddReference(usd_filename)

scope = stage.DefinePrim('/root/MaterialX', "Scope")

scope.GetReferences().AddReference(materialx_filename, "/MaterialX")

mesh_paths = (x.GetPath() for x in stage.Traverse() if UsdGeom.Mesh(x))

for path in mesh_paths:
    over = stage.OverridePrim(path)

    over.GetRelationship("material:binding").SetTargets(["/root/MaterialX/Materials/" + material_name])

stage.GetRootLayer().Save()
