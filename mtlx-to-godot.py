import MaterialX as mx
import sys
import godot_parser
import os

VECTOR_OP_TYPE = {
    "vector2": 0,
    "vector3": 1,
    "color3": 1,
    "vector4": 2,
}

OP_NAME_TO_ID = {
    "add": 0,
    "subtract": 1,
    "multiply": 2
}

FUNC_NAME_TO_ID = {
    "sin": 0,
    "cos": 1,
    "power": 5
}

COLOR_FUNC_NAME_TO_ID = {
    "hsvtorgb": 1
}

TEXTURE_TYPE_TO_ID = {
    "data": 0,
    "color": 1,
    "normalmap": 2
}

NODE_AND_INPUT_NAME_TO_SOCKET_INDEX = {
    "mix": {
        "bg": 0,
        "fg": 1,
        "mix": 2
    },
    "standard_surface": {
        # Todo: multiply base_color by this.
        "base": None,
        "base_color": 0,
        "metalness": 2,
        "diffuse_roughness": None,
        "specular_roughness": 3,
        "specular": 4,
        "specular_color": None,
        "specular_rotation": None,
        # Todo: multiply these two.
        "emission": 5,
        "emission_color": None,
        "normal": 9,
        "coat": 13,
        "coat_roughness": 14,
        "coat_color": None,
        "specular_anisotropy": 15,
        # Todo: is plugging this into 'subsurf scatter' correct?
        "subsurface": 17,
        "coat_anisotropy": None,
        "coat_rotation": None,
        "coat_IOR": None,
        "coat_affect_color": None,
        "coat_affect_roughness": None,
        "coat_normal": None,
        "specular_IOR": None,
        "sheen": None,
        "sheen_color": None,
        "sheen_roughness": None,
        # Todo: which of these can we handle?
        "subsurface_scale": None,
        "subsurface_color": None,
        "subsurface_radius": None,
        "subsurface_anisotropy": None,
        "transmission": None,
        "transmission_color": None,
        "transmission_depth": None,
        "transmission_scatter": None,
        "transmission_scatter_anisotropy": None,
        "transmission_dispersion": None,
        "transmission_extra_roughness": None,
        "thin_walled": None,
        "thin_walled_thickness": None,
        "thin_film_thickness": None,
        "thin_film_IOR": None,
        "tangent": None,
        # Todo: use this for alpha? It's a color3 for some reason.
        "opacity": None
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
    },
    "cos": {
        "in": 0
    },
    "hsvtorgb": {
        "in": 0
    },
    "combine2": {
        "in1": 0,
        "in2": 1
    },
    "combine3": {
        "in1": 0,
        "in2": 1,
        "in3": 2
    },
    "power": {
        "in1": 0,
        "in2": 1
    },
    "dotproduct": {
        "in1": 0,
        "in2": 1
    },
    "dot": {
        "in1": 0,
        "in2": 1
    },
    "add": {
        "in1": 0,
        "in2": 1
    },
    "subtract": {
        "in1": 0,
        "in2": 1
    },
    "multiply": {
        "in1": 0,
        "in2": 1
    },
}

def get_value_as_godot_or_default(input):
    if input.getType() == "float":
        return input.getValue() or 0.0
    elif input.getType() == "vector2":
        return input.getValue() and godot_parser.Vector2(*input.getValue()) or godot_parser.Vector2(0,0)
    elif input.getType() == "color3" or input.getType() == "vector3":
        return input.getValue() and godot_parser.Vector3(*input.getValue()) or godot_parser.Vector3(0,0,0)
    else:
        assert False, input

def get_value_as_godot(input):
    if input.getValue() is None:
        return None

    return get_value_as_godot_or_default(input)

def assert_node_has_no_value_sockets(node):
    for input in node.getInputs():
        assert input.getValue() == None, (str(node), [str(i) for i in node.getInputs()])

# Todo: this does not do any kind of mapping between MaterialX input layouts
# and godot input layouts yet.
def default_input_values(node):
    values = []

    for (i, input) in enumerate(node.getInputs()):
        values += [i, get_value_as_godot_or_default(input)]
    return values

# Paths in MaterialX are confusingly indirect.
def convert_filename_to_rel_path(node, materialx_filepath, filename):
    # Sometimes you see stuff like '<nodegraph name="NG_wood1" fileprefix="../textures/">'
    # We need to join the filename with that prefix.
    path_with_prefix = os.path.join(node.getActiveFilePrefix(), filename)
    valid_path = os.path.join(os.path.dirname(materialx_filepath), path_with_prefix)
    return os.path.relpath(valid_path)

# I'm not a fan of OOP so we're not implementing any functions on this context type,
# just passing them in as the first argument to stuff.
class MaterialContext:
    resource = godot_parser.GDResource()
    # The internal id godot uses for specifying nodes and their connections.
    # Seems to start at 2 but I haven't checked why.
    next_internal_id = 2
    internal_id_to_sub_resource = {}
    path_to_ext_res = {}

    # We need this to reset between materials (not sure why, I don't know python so well)
    def __init__(self):
        self.resource = godot_parser.GDResource()
        self.next_internal_id = 2
        self.internal_id_to_sub_resource = {}
        self.path_to_ext_res = {}

def add_sub_resource(context, type, **kwargs):
    assert not type.startswith("VisualShaderNode"), ("we're shortening names for brevity.", type)

    sub_res = context.resource.add_sub_resource(type="VisualShaderNode"+type, **kwargs)
    internal_id = context.next_internal_id
    context.internal_id_to_sub_resource[internal_id] = godot_parser.SubResource(sub_res.id)
    context.next_internal_id += 1
    return internal_id

def add_ext_res(context, path, type="Texture2D"):
    path = "res://" + path
    if not path in context.path_to_ext_res:
        context.path_to_ext_res[path] = godot_parser.ExtResource(context.resource.add_ext_resource(path, type).id)
    return context.path_to_ext_res[path]

# Add the node as a subresource and return it's internal id.
# Todo: make sure we can use this to insert extra nodes such as for converting normals to world space.
# Todo: eliminate op_types as much as possible.
def add_node(context, node, connects_to_normalmap):
    cat = node.getCategory()
    internal_id = None
    socket_index = 0

    if cat == "image" or cat == "tiledimage":
        texture_type = "color"
        if connects_to_normalmap:
            texture_type = "normalmap"
        elif node.getType() == "float":
            socket_index = 1
            # color images use color3 etc.
            texture_type = "data"
        relpath = convert_filename_to_rel_path(node, sys.argv[1], node.getInput("file").getValue())
        internal_id = add_sub_resource(context, type="Texture", texture_type = TEXTURE_TYPE_TO_ID[texture_type], texture = add_ext_res(context, relpath), expanded_output_ports = [0])
    elif cat == "mix":
        op_type = None
        if node.getType() == "float":
            op_type = 0
        elif node.getType() == "vector3" or node.getType() == "color3" or node.getType() == "color4":
            op_type = 3
        else:
            assert False, node.getType()

        values = default_input_values(node)
        internal_id = add_sub_resource(context, type = "Mix", op_type=op_type, default_input_values=values)
    elif cat == "texcoord":
        coord = "uv"
        if node.getName() == "UV_Map_001":
            coord = "uv2"
        internal_id = add_sub_resource(context, type="Input", input_name = coord)
    elif cat == "geompropvalue":
        name = node.getInput("geomprop").getValue()
        if name == "UVMap":
            internal_id = add_sub_resource(context, type="Input", input_name = "uv")
        else:
            assert False, name
    elif cat == "extract":
        input_type = node.getInput("in").getType()
        socket_index = node.getInput("index").getValue()

        internal_id = add_sub_resource(context, type = "VectorDecompose", op_type=VECTOR_OP_TYPE[input_type])
    elif cat == "clamp":
        op_type = None

        if node.getType() == "float":
            op_type = 0
        elif node.getType() == "color3":
            op_type = 4
        else:
            assert False, node

        values = default_input_values(node)

        internal_id = add_sub_resource(context, type = "Clamp", default_input_values=values, op_type=op_type)
    elif cat == "position":
        internal_id = add_sub_resource(context, type="Input", input_name = "node_position_world")
    elif cat == "combine3" or cat == "combine2":
        values = default_input_values(node)
        internal_id = add_sub_resource(context, type="VectorCompose", default_input_values=values, op_type=VECTOR_OP_TYPE[node.getType()])
    elif cat == "dotproduct":
        assert node.getInput("in1").getType() == "vector3"

        values = default_input_values(node)
        internal_id = add_sub_resource(context, type="DotProduct", default_input_values=values)
    elif cat == "constant":
        input = node.getInput("value")
        type = None

        if input.getType() == "float":
            type = "FloatParameter"
        elif input.getType() == "vector2":
            type = "Vec2Parameter"
        elif input.getType() == "color3":
            type = "Vec3Parameter"
        else:
            assert False, input.getType()

        internal_id = add_sub_resource(
            context,
            type=type,
            parameter_name = input.getName(),
            default_value_enabled=True,
            default_value=get_value_as_godot(input)
        )
    elif cat == "normal":
        # todo: world space normals.
        #print(node.getInput("space"))
        internal_id = add_sub_resource(context, type="Input", input_name = "normal")
    elif cat == "tangent":
        # todo: world space tangents.
        #print(node.getInput("space"))
        internal_id = add_sub_resource(context, type="Input", input_name = "tangent")
    elif cat in OP_NAME_TO_ID:
        values = default_input_values(node)
        operator = OP_NAME_TO_ID[cat]

        if node.getType() == "float":
            internal_id = add_sub_resource(context, type = "FloatOp", operator = operator, default_input_values=values)
        else:
            op_type = VECTOR_OP_TYPE[node.getType()]
            internal_id = add_sub_resource(context, type = "VectorOp", operator = operator, default_input_values=values)
    elif cat in FUNC_NAME_TO_ID:
        assert_node_has_no_value_sockets(node)
        operator = FUNC_NAME_TO_ID[cat]

        if node.getType() == "float":
            internal_id = add_sub_resource(context, type = "FloatFunc", operator = operator)
        else:
            assert False, node.getType()
    elif cat in COLOR_FUNC_NAME_TO_ID:
        operator = COLOR_FUNC_NAME_TO_ID[cat]
        internal_id = add_sub_resource(context, type = "ColorFunc", operator = operator)
    else:
        assert False, cat

    return (internal_id, socket_index)

def convert_material(material):
    seen_edges = set()
    got_standard_surface = False
    node_name_to_internal_id_and_output_socket_index = {}
    connections = []
    # Todo: maybe put this other stuff in context too even though it's not needed in add_node
    # or the other functions?
    context = MaterialContext()

    for edge in material.traverseGraph():
        upstream = edge.getUpstreamElement()
        downstream = edge.getDownstreamElement()
        input_socket = edge.getConnectingElement()

        # Sometimes edges get emitted twice by some funky files where the same
        # nodegraph output is used twice.
        # Example: https://github.com/RogerDass/Usd-Mtlx-Example/blob/2829831c2deab4f74ff805965462b99835c064c7/materials/standard_surface_brass_tiled.mtlx
        edge_id = (input_socket.getName(), downstream.getName())
        if edge_id in seen_edges:
            continue
        seen_edges.add(edge_id)

        # Ignore a few node types (making note of normalmaps)
        # - conversions are implicit in godot
        # - there are no normalmap nodes, that happens in the Texture2D node
        # - dots are just no-ops for pretty graphs or something, like a blender reroute
        connects_to_normalmap = upstream.getCategory() == "normalmap"
        skip_nodes = {"convert", "normalmap", "dot"}

        if downstream.getCategory() in skip_nodes:
            continue
        # If the upsteam node is a skipped node then find what it's upstream node is and use that instead.
        elif upstream.getCategory() in skip_nodes:
            assert upstream.getConnectedNode("in") is not None, upstream
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

                socket_index = NODE_AND_INPUT_NAME_TO_SOCKET_INDEX["standard_surface"][input.getName()]

                # Ignore MaterialX params we can't handle.
                if socket_index == None:
                    continue

                type = None

                if input.getType() == "float":
                    type = "FloatParameter"
                elif input.getType() == "color3":
                    type = "Vec3Parameter"

                param_internal_id = add_sub_resource(
                    context,
                    type=type,
                    parameter_name = input.getName(),
                    default_value_enabled=True,
                    default_value=get_value_as_godot(input)
                )

                connections += [param_internal_id, 0, 0, socket_index]
            continue

        # Get or set the internal id for the upstream node
        if not upstream.getName() in node_name_to_internal_id_and_output_socket_index:
            node_name_to_internal_id_and_output_socket_index[upstream.getName()] = add_node(context, upstream, connects_to_normalmap)

        (upstream_internal_id, upstream_socket_index) = node_name_to_internal_id_and_output_socket_index[upstream.getName()]

        # Try to get the socket index we're connecting into.
        downstream_socket_index = None

        if downstream.getCategory() in NODE_AND_INPUT_NAME_TO_SOCKET_INDEX:
            downstream_sockets = NODE_AND_INPUT_NAME_TO_SOCKET_INDEX[downstream.getCategory()]
            assert input_socket.getName() in downstream_sockets, (str(input_socket), str(downstream))
            downstream_socket_index = downstream_sockets[input_socket.getName()]
        else:
            # Make sure we at least know about the socket.
            assert False, downstream.getCategory()

        # If it's marked as None then it's not something we can implement and we just continue.
        if downstream_socket_index == None:
            continue

        # Connect up the sockets.
        (downstream_internal_id, _) = node_name_to_internal_id_and_output_socket_index[downstream.getName()]
        connections += [upstream_internal_id, upstream_socket_index, downstream_internal_id, downstream_socket_index]

    # Write out the resource section where we give the nodes IDs and define their connections.
    section = godot_parser.GDSection(header=godot_parser.GDSectionHeader('resource'))
    for internal_id, sub_res in context.internal_id_to_sub_resource.items():
        section[f"nodes/fragment/{internal_id}/node"] = sub_res

    section["nodes/fragment/connections"] = godot_parser.GDObject("PackedInt32Array", *connections)
    context.resource.add_section(section)

    # Hack because I'm not sure how to set the type in the godot_parser lib
    resource = str(context.resource)
    resource = resource.replace("[gd_resource", "[gd_resource type=\"VisualShader\"")

    return resource

if __name__ == "__main__":
    doc = mx.createDocument()
    mx.readFromXmlFile(doc, sys.argv[1])

    for material in doc.getMaterialNodes():
        converted = convert_material(material)
        open(f"{material.getName()}.tres", "w").write(converted)
