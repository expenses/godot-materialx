# coding: utf-8
import MaterialX as mx
import sys

doc = mx.createDocument()

mx.readFromXmlFile(doc, sys.argv[1])

# Remove any existing node defs with the same name as the ones we want.
doc.removeNode("stcoords")
doc.removeNode("normal_vector3")
doc.removeNode("position_vector3")

# Connect up the USD geometry values.

stcoords = doc.addNode("geompropvalue", "stcoords", "vector2")
stcoords.setInputValue("geomprop", "UVMap", "string")

node = doc.addNode("geompropvalue", "normal_vector3", "vector3")
node.setInputValue("geomprop", "normals", "string")

node = doc.addNode("geompropvalue", "position_vector3", "vector3")
node.setInputValue("geomprop", "points", "string")

# Set images up to use the new uv values.
for image in doc.getNodes("image"):
    image.setConnectedNode("texcoord", stcoords)

text = mx.writeToXmlString(doc)
print(text)
