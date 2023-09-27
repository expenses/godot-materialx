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

MIX_OP_TYPE = {
    (float, float): 0,
    (godot_parser.Vector2, godot_parser.Vector2): 1,
    (godot_parser.Vector2, float): 2,
    (godot_parser.Vector3, godot_parser.Vector3): 3,
    (godot_parser.Vector3, float): 4,
    # Todo: godot_parser doesn't have a Vector4 type.
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
        # Handled via a mix node.
        #"base": None,
        #"base_color": None,
        "metalness": 2,
        "diffuse_roughness": None,
        "specular_roughness": 3,
        "specular": 4,
        "specular_color": None,
        "specular_rotation": None,
        # Handled via a mix node
        #"emission": 5,
        #"emission_color": None,
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
    "remap": {
        "in": 0,
        "inlow": 1,
        "inhigh": 2,
        "outlow": 3,
        "outhigh": 4,
    }
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

def default_input_values(node):
    values = []

    socket_indices = NODE_AND_INPUT_NAME_TO_SOCKET_INDEX[node.getCategory()]

    # todo: this only works if the inputs are in order.
    for (name, index) in socket_indices.items():
        input = node.getInput(name)
        # todo: this can happen sometimes, for example a remap node missing outhigh.
        # need to fetch the default value.
        if input is None:
            assert False, print(str(node), name)
        # Todo: perhaps handle interface inputs a different way?
        if input.getInterfaceInput() is not None:
            input = input.getInterfaceInput()

        values += [index, get_value_as_godot_or_default(input)]

    """
    for (i, input) in enumerate(node.getInputs()):
        # Todo: perhaps handle interface inputs a different way?
        if input.getInterfaceInput() is not None:
            input = input.getInterfaceInput()
        values += [i, get_value_as_godot_or_default(input)]
    """
    return values

def convert_filename_to_rel_path(input, materialx_filepath):
    resolved = input.getResolvedValueString()
    valid_path = os.path.join(os.path.dirname(materialx_filepath), resolved)
    return os.path.relpath(valid_path)

class MaterialContext:
    def __init__(self):
        self.resource = godot_parser.GDResource()
        # The internal id godot uses for specifying nodes and their connections.
        # Seems to start at 2 but I haven't checked why.
        self.next_internal_id = 2
        self.internal_id_to_sub_resource = {}
        self.path_to_ext_res = {}
        self.connections = []

    def connect(self, upstream, downstream):
        (upstream_internal_id, upstream_socket_index) = upstream
        (downstream_internal_id, downstream_socket_index) = downstream
        self.connections += [upstream_internal_id, upstream_socket_index, downstream_internal_id, downstream_socket_index]

    def add_sub_resource(self, node_type, **kwargs):
        assert not node_type.startswith("VisualShaderNode"), ("we're shortening names for brevity.", node_type)

        sub_res = self.resource.add_sub_resource(type="VisualShaderNode"+node_type, **kwargs)
        internal_id = self.next_internal_id
        self.internal_id_to_sub_resource[internal_id] = godot_parser.SubResource(sub_res.id)
        self.next_internal_id += 1
        return internal_id

    def add_ext_res(self, path, res_type="Texture2D"):
        path = "res://" + path
        if not path in self.path_to_ext_res:
            self.path_to_ext_res[path] = godot_parser.ExtResource(self.resource.add_ext_resource(path, res_type).id)
        return self.path_to_ext_res[path]

    # Add the node as a subresource and return it's internal id.
    def add_node(self, node, connects_to_normalmap):
        cat = node.getCategory()
        socket_index = 0

        if cat == "image" or cat == "tiledimage":
            if connects_to_normalmap:
                texture_type = "normalmap"
            elif node.getType() == "float" or node.getType() == "vector3":
                socket_index = 1
                # color images use color3 etc.
                texture_type = "data"
            elif node.getType() == "color3":
                texture_type = "color"

            assert texture_type is not None, node
            relpath = convert_filename_to_rel_path(node.getInput("file"), sys.argv[1])
            internal_id = self.add_sub_resource(node_type="Texture", texture_type = TEXTURE_TYPE_TO_ID[texture_type], texture = self.add_ext_res(relpath), expanded_output_ports = [0])
        elif cat == "mix":
            values = default_input_values(node)
            # get the op type using the 0th and 2nd values
            op_type = MIX_OP_TYPE[(type(values[1]), type(values[5]))]
            internal_id = self.add_sub_resource(node_type = "Mix", op_type=op_type, default_input_values=values)
        elif cat == "texcoord":
            coord = "uv"
            if node.getName() == "UV_Map_001":
                coord = "uv2"
            internal_id = self.add_sub_resource(node_type="Input", input_name = coord)
        elif cat == "geompropvalue":
            name = node.getInput("geomprop").getValue()
            if name == "UVMap":
                internal_id = self.add_sub_resource(node_type="Input", input_name = "uv")
            else:
                assert False, name
        elif cat == "extract":
            input_type = node.getInput("in").getType()
            socket_index = node.getInput("index").getValue()

            internal_id = self.add_sub_resource(node_type = "VectorDecompose", op_type=VECTOR_OP_TYPE[input_type])
        elif cat == "clamp":
            # Todo: use a lookup table for this.
            if node.getType() == "float":
                op_type = 0
            elif node.getType() == "color3":
                op_type = 4
            else:
                assert False, node

            values = default_input_values(node)

            internal_id = self.add_sub_resource(node_type = "Clamp", default_input_values=values, op_type=op_type)
        elif cat == "position":
            internal_id = self.add_sub_resource(node_type="Input", input_name = "node_position_world")
        elif cat == "combine3" or cat == "combine2":
            values = default_input_values(node)
            internal_id = self.add_sub_resource(node_type="VectorCompose", default_input_values=values, op_type=VECTOR_OP_TYPE[node.getType()])
        elif cat == "dotproduct":
            assert node.getInput("in1").getType() == "vector3"

            values = default_input_values(node)
            internal_id = self.add_sub_resource(node_type="DotProduct", default_input_values=values)
        elif cat == "constant":
            input = node.getInput("value")

            if input.getType() == "float":
                node_type = "FloatParameter"
            elif input.getType() == "vector2":
                node_type = "Vec2Parameter"
            elif input.getType() == "color3":
                node_type = "Vec3Parameter"
            else:
                assert False, input.getType()

            internal_id = self.add_sub_resource(
                node_type=node_type,
                parameter_name = node.getName(),
                default_value_enabled=True,
                default_value=get_value_as_godot(input)
            )
        elif cat == "normal":
            inv_view_matrix_input_id = self.add_sub_resource(node_type="Input", input_name = "inv_view_matrix")
            normal_input_id = self.add_sub_resource(node_type="Input", input_name = "normal")
            transform_id = self.add_sub_resource(node_type="TransformVecMult", operator = 2)
            self.connect((inv_view_matrix_input_id, 0), (transform_id, 0))
            self.connect((normal_input_id, 0), (transform_id, 1))
            internal_id = transform_id
        elif cat == "tangent":
            inv_view_matrix_input_id = self.add_sub_resource(node_type="Input", input_name = "inv_view_matrix")
            tangent_input_id = self.add_sub_resource(node_type="Input", input_name = "tangent")
            transform_id = self.add_sub_resource(node_type="TransformVecMult", operator = 2)
            self.connect((inv_view_matrix_input_id, 0), (transform_id, 0))
            self.connect((tangent_input_id, 0), (transform_id, 1))
            internal_id = transform_id
        elif cat == "remap":
            values = default_input_values(node)
            internal_id = self.add_sub_resource(node_type="Remap", default_input_values=values)
        elif cat in OP_NAME_TO_ID:
            values = default_input_values(node)
            operator = OP_NAME_TO_ID[cat]

            if node.getType() == "float":
                internal_id = self.add_sub_resource(node_type = "FloatOp", operator = operator, default_input_values=values)
            else:
                op_type = VECTOR_OP_TYPE[node.getType()]
                internal_id = self.add_sub_resource(node_type = "VectorOp", operator = operator, default_input_values=values)
        elif cat in FUNC_NAME_TO_ID:
            assert_node_has_no_value_sockets(node)
            function = FUNC_NAME_TO_ID[cat]

            if node.getType() == "float":
                internal_id = self.add_sub_resource(node_type = "FloatFunc", function = function)
            else:
                assert False, node.getType()
        elif cat in COLOR_FUNC_NAME_TO_ID:
            function = COLOR_FUNC_NAME_TO_ID[cat]
            internal_id = self.add_sub_resource(node_type = "ColorFunc", function = function)
        else:
            assert False, cat

        return (internal_id, socket_index)

def convert_material(material):
    seen_edges = set()
    got_standard_surface = False
    node_name_to_internal_id_and_output_socket_index = {}
    context = MaterialContext()

    color_mult_internal_id = context.add_sub_resource(
        node_type = "VectorOp",
        operator = OP_NAME_TO_ID["multiply"],
        op_type = VECTOR_OP_TYPE["color3"],
        default_input_values = [godot_parser.Vector3(1,1,1), godot_parser.Vector3(1,1,1)]
    )
    context.connect((color_mult_internal_id, 0), (0, 0))
    emission_mult_internal_id = context.add_sub_resource(
        node_type = "VectorOp",
        operator = OP_NAME_TO_ID["multiply"],
        op_type = VECTOR_OP_TYPE["color3"],
        default_input_values = [godot_parser.Vector3(0,0,0), godot_parser.Vector3(1,1,1)]
    )
    context.connect((emission_mult_internal_id, 0), (0, 5))

    output_redirects = {
        "base": [color_mult_internal_id, 0],
        "base_color": [color_mult_internal_id, 1],
        "emission": [emission_mult_internal_id, 0],
        "emission_color": [emission_mult_internal_id, 1]
    }

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

                output_internal_id = 0

                if input.getName() in output_redirects:
                    (output_internal_id, output_socket_index) = output_redirects[input.getName()]
                else:
                    output_socket_index = NODE_AND_INPUT_NAME_TO_SOCKET_INDEX["standard_surface"][input.getName()]

                # Ignore MaterialX params we can't handle.
                if output_socket_index == None:
                    continue

                if input.getType() == "float":
                    node_type = "FloatParameter"
                elif input.getType() == "color3":
                    node_type = "Vec3Parameter"

                param_internal_id = context.add_sub_resource(
                    node_type=node_type,
                    parameter_name = input.getName(),
                    default_value_enabled=True,
                    default_value=get_value_as_godot(input)
                )

                context.connect((param_internal_id, 0), (output_internal_id, output_socket_index))
            continue

        # Get or set the internal id for the upstream node
        if not upstream.getName() in node_name_to_internal_id_and_output_socket_index:
            node_name_to_internal_id_and_output_socket_index[upstream.getName()] = context.add_node(upstream, connects_to_normalmap)

        (upstream_internal_id, upstream_socket_index) = node_name_to_internal_id_and_output_socket_index[upstream.getName()]

        # Try to get the socket index we're connecting into.
        (downstream_internal_id, _) = node_name_to_internal_id_and_output_socket_index[downstream.getName()]

        if downstream.getCategory() == "standard_surface" and input_socket.getName() in output_redirects:
            (downstream_internal_id, downstream_socket_index) = output_redirects[input_socket.getName()]
        elif downstream.getCategory() in NODE_AND_INPUT_NAME_TO_SOCKET_INDEX:
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
        context.connect((upstream_internal_id, upstream_socket_index), (downstream_internal_id, downstream_socket_index))

    # Write out the resource section where we give the nodes IDs and define their connections.
    section = godot_parser.GDSection(header=godot_parser.GDSectionHeader('resource'))
    for internal_id, sub_res in context.internal_id_to_sub_resource.items():
        section[f"nodes/fragment/{internal_id}/node"] = sub_res

    section["nodes/fragment/connections"] = godot_parser.GDObject("PackedInt32Array", *context.connections)
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
