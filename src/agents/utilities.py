from bs4 import Tag


def extract_ids_from_output(item):
    """
    Convert the extracted IDs to a list of integers.
    The format is a bit complex to motivate the model to return a more accurate output.
    """
    numbers = []
    if isinstance(item, dict):
        for value in item.values():
            numbers.extend(extract_ids_from_output(value))
    elif isinstance(item, list):
        for element in item:
            numbers.extend(extract_ids_from_output(element))
    elif isinstance(item, int):
        numbers.append(item)
    return numbers


def create_xml_element(element):
    # Only include elements with meaningful content
    if not any([element.get('name'), element.get('description'), element.get('value'), element.get('children')]) and element['role'] == 'AXGroup':
        return None

    attrib = {
        'role_description': element.get('role_description', ''),
        'id': element['id'],
        'name': element.get('name', ''),
        'description': element.get('description', ''),
        'value': str(element['value']) if element.get('value') is not None else ''
    }

    xml_element = Tag(name=element['role'], attrs=attrib)
    meaningful_children = [create_xml_element(child) for child in element.get('children', []) if create_xml_element(child)]

    # Merge condition: Check if it's a row with only one cell
    if element['role'] == 'AXRow' and len(meaningful_children) == 1 and meaningful_children[0].name == 'AXCell':
        cell = meaningful_children[0]
        cell_children = list(cell.children)
        if len(cell_children) == 1:
            merged_element = cell_children[0]
            merged_element['role_description'] = f"merged {attrib['role_description']}"
            return merged_element

    for child in meaningful_children:
        xml_element.append(child)

    # Remove elements that are groups without meaningful children
    if not list(xml_element.children) and element['role'] == 'AXGroup':
        return None

    return xml_element


def pretty_print_xml(xml_tree):
    if xml_tree is None:
        return ""
    if type(xml_tree) == str:
        return xml_tree
    return xml_tree.prettify()


def map_ids(element, id_mapping, current_id=1):
    original_id = element['id']
    id_mapping[current_id] = original_id
    element['id'] = str(current_id)
    current_id += 1

    for child in element.find_all(recursive=False):
        current_id = map_ids(child, id_mapping, current_id)

    return current_id


def json_to_xml(json_obj):
    id_mapping = {}
    root_element = create_xml_element(json_obj)
    if root_element is None:
        return None, id_mapping
    
    # Map ids of elements
    map_ids(root_element, id_mapping)
    return root_element, id_mapping