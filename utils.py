
def get_gltf_reference_path_for_prim(prim):
    stack = prim.GetPrimStack()
    reference = None
    # Iter through the prim stack from bottom-up, getting the latest appied
    # reference.
    for spec in reversed(stack):
        references = spec.referenceList.GetAppliedItems()
        if len(references) > 0:
            reference = references[0]
    return reference.assetPath
