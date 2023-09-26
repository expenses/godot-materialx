import MaterialX as mx
import sys
import godot_parser
import os

doc = mx.createDocument()
mx.readFromXmlFile(doc, sys.argv[1])

scene = godot_parser.GDResource()

next_internal_id = 2
internal_id_to_sub_resource = {}
connections = []

def add_sub_resource(**kwargs):
    global next_internal_id
    sub_res = scene.add_sub_resource(**kwargs)
    internal_id = next_internal_id
    internal_id_to_sub_resource[internal_id] = godot_parser.SubResource(sub_res.id)
    next_internal_id += 1
    return internal_id

path_to_ext_res = {}

def add_ext_res(path, type="Texture2D"):
    path = "res://" + path
    if not path in path_to_ext_res:
        path_to_ext_res[path] = godot_parser.ExtResource(scene.add_ext_resource(path, type).id)
    return path_to_ext_res[path]

node_name_to_internal_id_and_output_socket_index = {}

op_name_to_id = {
    "add": 1,
    "multiply": 2
}

func_name_to_id = {
    "sin": 0,
    "power": 5
}

node_and_input_name_to_socket_index = {
    "mix": {
        "bg": 0,
        "fg": 1,
        "mix": 2
    },
    "standard_surface": {
        "base": None,
        "base_color": 0,
        "metalness": 2,
        "specular_roughness": 3,
        "specular": 4,
        "specular_color": None,
        "coat_color": None,
        "coat": 13,
        "coat_roughness": 14,
        "specular_anisotropy": 15,
        "coat_anisotropy": None,
        "specular_IOR": None,
        "sheen": None,
        "sheen_color": None,
        "sheen_roughness": None,
    },
    "clamp": {
        "in": 0
    },
    "image": {
        "texcoord": 0,
    },
    "tiledimage": {
        "texcoord": 0
    },
    "extract": {
        "in": 0
    },
    "sin": {
        "in": 0
    }
}

two_input_nodes = set(["power", "dotproduct", "add", "multiply"])

two_input_mapping = {
    "in1": 0,
    "in2": 1
}

# Add the node as a subresource and return it's internal id.
# Todo: make sure we can use this to insert extra nodes such as for converting normals to world space.
def add_node(node):
    cat = node.getCategory()

    if cat == "image" or cat == "tiledimage":
        socket_index = 0
        texture_type = 1
        if node.getType() == "float":
            socket_index = 1
            # color images use color3 etc.
            texture_type = 0
        fixed_path = os.path.join(os.path.dirname(sys.argv[1]), node.getInput("file").getValue())
        relpath = os.path.relpath(fixed_path)
        return (add_sub_resource(type="VisualShaderNodeTexture", texture_type = texture_type, texture = add_ext_res(relpath), expanded_output_ports = [0]), socket_index)
    elif cat == "mix":
        op_type = None
        if node.getType() == "color3" or node.getType() == "color4":
            op_type = 3
        else:
            assert False, node.getType()
        return (add_sub_resource(type = "VisualShaderNodeMix", op_type=op_type), 0)
    elif cat == "texcoord":
        coord = "uv"
        if node.getName() == "UV_Map_001":
            coord = "uv2"
        return (add_sub_resource(type="VisualShaderNodeInput", input_name = coord), 0)
    elif cat == "geompropvalue":
        name = node.getInput("geomprop").getValue()
        if name == "UVMap":
            return (add_sub_resource(type="VisualShaderNodeInput", input_name = "uv"), 0)
        else:
            assert False, name
    elif cat == "extract":
        input_type = node.getInput("in").getType()
        field = node.getInput("index").getValue()

        op_type = None

        if input_type == "color4":
            op_type = 2
        else:
            assert False, input_type

        return (add_sub_resource(type = "VisualShaderNodeVectorDecompose", op_type=op_type), field)
    elif cat == "clamp":
        return (add_sub_resource(type = "VisualShaderNodeClamp"), 0)
    elif cat == "position":
        return (add_sub_resource(type="VisualShaderNodeInput", input_name = "node_position_world"), 0)
    elif cat in op_name_to_id:
        operator = op_name_to_id[cat]

        if node.getType() == "float":
            return (add_sub_resource(type = "VisualShaderNodeFloatOp", operator = operator), 0)
        elif node.getType() == "vector3":
            return (add_sub_resource(type = "VisualShaderNodeVectorOp", operator = operator), 0)
        else:
            assert False, node.getType()
    elif cat == "dotproduct":
        assert node.getInput("in1").getType() == "vector3"

        default_input_values = [0, godot_parser.Vector3(0,0,0), 1, godot_parser.Vector3(0,0,0)]
        for (i, input) in enumerate(node.getInputs()):
            if input.getValue() is not None:
                default_input_values[i*2] = godot_parser.Vector3(*input.getValue())
        return (add_sub_resource(type="VisualShaderNodeDotProduct", default_input_values=default_input_values), 0)
    elif cat in func_name_to_id:
        operator = func_name_to_id[cat]

        if node.getType() == "float":
            return (add_sub_resource(type = "VisualShaderNodeFloatFunc", operator = operator), 0)
        else:
            assert False, node.getType()
    else:
        assert False, cat
        print(node)
        return (None, None)

seen_edges = set()

got_standard_surface = False

for material in doc.getMaterialNodes():
    for edge in material.traverseGraph():
        upstream = edge.getUpstreamElement()
        downstream = edge.getDownstreamElement()
        input_socket = edge.getConnectingElement()

        # Todo: sometimes edges get emitted twice by some funky files with multiple materials or smth.
        edge_id = (input_socket.getName(), downstream.getName())
        if edge_id in seen_edges:
            continue
        seen_edges.add(edge_id)

        # Ignore convert nodes
        if downstream.getCategory() == "convert":
            continue
        # If the upsteam node is a convert node then find what it's upstream node is and use that instead.
        elif upstream.getCategory() == "convert":
            upstream = upstream.getConnectedNode("in")

        # Special handling of standard surface nodes
        if upstream.getCategory() == "standard_surface":
            # make sure we're not dealing with multiple standard surfaces
            assert not got_standard_surface
            got_standard_surface = True
            node_name_to_internal_id_and_output_socket_index[upstream.getName()] = (0, 0)

            # As you can't plug values directly into the godot output node, we need
            # to connect all the direct-value sockets with parameters
            for input in upstream.getInputs():
                if input.getValue() == None:
                    continue

                socket_index = node_and_input_name_to_socket_index[upstream.getCategory()][input.getName()]

                # Ignore MaterialX params we can't handle.
                if socket_index == None:
                    continue

                type = None
                value = input.getValue()

                if input.getType() == "float":
                    type = "VisualShaderNodeFloatParameter"
                elif input.getType() == "color3":
                    type = "VisualShaderNodeVec3Parameter"
                    value = godot_parser.Vector3(*value)

                param_internal_id = add_sub_resource(type=type, parameter_name = input.getName(), default_value_enabled=True, default_value=value)

                connections += [param_internal_id, 0, 0, socket_index]
            continue

        # Get or set the internal id for the upstream node
        if not upstream.getName() in node_name_to_internal_id_and_output_socket_index:
            node_name_to_internal_id_and_output_socket_index[upstream.getName()] = add_node(upstream)

        (upstream_internal_id, upstream_socket_index) = node_name_to_internal_id_and_output_socket_index[upstream.getName()]

        # Try to get the socket index we're connecting into.
        downstream_socket_index = None

        if downstream.getCategory() in two_input_nodes:
            downstream_socket_index = two_input_mapping[input_socket.getName()]
        elif downstream.getCategory() in node_and_input_name_to_socket_index:
            downstream_socket_index = node_and_input_name_to_socket_index[downstream.getCategory()][input_socket.getName()]
        else:
            # Make sure we at least know about the socket.
            assert False, downstream.getCategory()

        # If it's marked as None then it's not something we can implement and we just continue.
        if downstream_socket_index == None:
            continue

        # Connect up the sockets.
        (downstream_internal_id, _) = node_name_to_internal_id_and_output_socket_index[downstream.getName()]
        connections += [upstream_internal_id, upstream_socket_index, downstream_internal_id, downstream_socket_index]


section = godot_parser.GDSection(header=godot_parser.GDSectionHeader('resource'))
for internal_id, sub_res in internal_id_to_sub_resource.items():
    section[f"nodes/fragment/{internal_id}/node"] = sub_res

section["nodes/fragment/connections"] = godot_parser.GDObject("PackedInt32Array", *connections)
scene.add_section(section)

scene = str(scene)
scene = scene.replace("[gd_resource", "[gd_resource type=\"VisualShader\"")

print(scene)
