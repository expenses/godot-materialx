# coding: utf-8
import godot_parser
import sys
import MaterialX as mx
import os
scene = godot_parser.GDResource()

doc = mx.createDocument()
mx.readFromXmlFile(doc, sys.argv[1])

path_to_ext_res_id = {}

def add_ext_res(path, type="Texture2D"):
    path = "res://" + path
    if not path in path_to_ext_res_id:
        path_to_ext_res_id[path] = scene.add_ext_resource(path, type).id
    return godot_parser.ExtResource(path_to_ext_res_id[path])

next_id = 2
mapping = {}
connections = []
node_to_id = {}

def add_subresource(node, output_socket = 0, **kwargs):
    global next_id
    sub_res = scene.add_sub_resource(**kwargs)
    mapping[next_id] = sub_res.id
    node_to_id[node.getName()] = (next_id, output_socket)
    next_id += 1

nodes = None
if len(doc.getNodeGraphs()) == 0:
    nodes = doc.getNodes()
else:
    assert len(doc.getNodeGraphs()) == 1
    graph = doc.getNodeGraphs()[0]
    nodes = graph.getNodes()

# Add nodes
for node in nodes:
    cat = node.getCategory()

    if cat == "image":
        relpath = os.path.relpath(node.getInput("file").getValue())
        texture_type = 1
        add_subresource(node, type="VisualShaderNodeTexture", texture_type = texture_type, texture = add_ext_res(relpath))
    elif cat == "tiledimage":
        relpath = os.path.relpath(node.getInput("file").getValue())
        texture_type = 1
        add_subresource(node, type="VisualShaderNodeTexture", texture_type = texture_type, texture = add_ext_res(relpath))
    elif cat == "standard_surface":
        node_to_id[node.getName()] = (0, None)
    elif cat == "geompropvalue":
        name = node.getInput("geomprop").getValue()
        if name == "UVMap":
            add_subresource(node, type="VisualShaderNodeInput", input_name = "uv")
        else:
            assert False, name
    elif cat == "texcoord":
        coord = "uv"
        if node.getName() == "UV_Map_001":
            coord = "uv2"
        add_subresource(node, type="VisualShaderNodeInput", input_name = coord)
    elif cat == "position":
        add_subresource(node, type="VisualShaderNodeInput", input_name = "node_position_world")
    elif cat == "dotproduct":
        default_input_values = [0, godot_parser.Vector3(0,0,0), 1, godot_parser.Vector3(0,0,0)]
        for (i, input) in enumerate(node.getInputs()):
            if input.getValue() is not None:
                default_input_values[i*2] = godot_parser.Vector3(*input.getValue())
        add_subresource(node, type="VisualShaderNodeDotProduct", default_input_values=default_input_values)
    elif cat == "extract":
        input_type = node.getInput("in").getType()
        field = node.getInput("index").getValue()

        op_type = None

        if input_type == "color4":
            op_type = 2
        else:
            assert False, input_type

        add_subresource(node, output_socket = field, type = "VisualShaderNodeVectorDecompose", op_type=op_type)
    elif cat == "multiply":
        if node.getType() == "float":
            add_subresource(node, type = "VisualShaderNodeFloatOp", operator = 2)
        elif node.getType() == "vector3":
            add_subresource(node, type = "VisualShaderNodeVectorOp", operator = 2)
        else:
            assert False, node.getType()
    elif cat == "add":
        if node.getType() == "float":
            add_subresource(node, type = "VisualShaderNodeFloatOp", operator = 1)
        else:
            assert False
    elif cat == "sin":
        if node.getType() == "float":
            add_subresource(node, type = "VisualShaderNodeFloatFunc", function = 0)
        else:
            assert False
    elif cat == "power":
        if node.getType() == "float":
            add_subresource(node, type = "VisualShaderNodeFloatOp", function = 5)
        else:
            assert False
    elif cat == "clamp":
        add_subresource(node, type = "VisualShaderNodeClamp")
    elif cat == "mix":
        op_type = None
        if node.getType() == "color3" or node.getType() == "color4":
            op_type = 3
        else:
            assert False, node.getType()
        add_subresource(node, type = "VisualShaderNodeMix", op_type=op_type)
    else:
        print(cat)

# Create connections between nodes
for node in nodes:
    # Skip nodes we're ignoring
    if node.getCategory() == "convert":
        continue
    elif node.getCategory() == "surfacematerial":
        continue
    elif node.getCategory() == "fractal3d":
        continue

    assert node.getName() in node_to_id, node

    node_id, _node_output_socket = node_to_id[node.getName()]
    node_socket = 0
    for input in node.getInputs():
        if not input.getNodeName():
            continue

        input_node = input.getConnectedNode()
        if input_node.getCategory() == "convert":
            input = input.getConnectedNode().getInputs()[0]
        elif input_node.getCategory() == "fractal3d":
            continue

        source_id, source_socket = node_to_id[input.getNodeName()]
        connections += [source_id, source_socket, node_id, node_socket]
        node_socket += 1

section = godot_parser.GDSection(header=godot_parser.GDSectionHeader('resource'))
for node_id, sub_res_id in mapping.items():
    section[f"nodes/fragment/{node_id}/node"] = godot_parser.SubResource(sub_res_id)

section["nodes/fragment/connections"] = godot_parser.GDObject("PackedInt32Array", *connections)
scene.add_section(section)


scene = str(scene)
scene = scene.replace("[gd_resource", "[gd_resource type=\"VisualShader\"")
open(sys.argv[2], "w").write(scene)
