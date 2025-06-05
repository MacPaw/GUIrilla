import json


# store element to the output file as json
def store_data_to_file(element, output_file):
    if output_file is None:
        return
    json_data = json.dumps(element.to_dict(), ensure_ascii=False, indent=4)
    with open(output_file, "w", encoding='utf8') as f:
        f.write(json_data)
