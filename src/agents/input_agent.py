from openai import OpenAI
import json
from agents.utilities import pretty_print_xml

with open("config_open_ai.env", "r") as f:
    api_key = f.read().strip()
client = OpenAI(api_key=api_key)


with open("src/agents/input_prompt.txt", "r") as f:
    ASSISTANT_PROMPT = f.read()

def get_input_fields(xml_data, id_mapping, input_fields, request_count=0):
    # Check if there are any AXTextFields in the XML data
    if xml_data.find_all("AXTextField") is None and xml_data.find_all("AXTextArea") is None:
        print("No AXTextFields or AXTextArea found in the XML data.")
        return {}
    
    input_field_ids = set([id_mapping[int(element["id"])].split("_")[0] for element in xml_data.find_all("AXTextField")])
    input_field_ids.update(set([id_mapping[int(element["id"])].split("_")[0] for element in xml_data.find_all("AXTextArea")]))
    # Check if these fields were already predicted
    if input_field_ids.issubset(input_fields.keys()):
        return {}
    
    xml_data_pretty = pretty_print_xml(xml_data)

    try:
        response = client.chat.completions.create(
            model="o3-mini",
            # model="gpt-4o-mini", doesn't handle this request well
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": ASSISTANT_PROMPT},
                {"role": "user", "content": xml_data_pretty},
            ],
        )
        request_count += 1

        text_field_input = response.choices[0].message.content

        data = json.loads(text_field_input)

        # Extract and combine numbers
        mapped_data = {}

        for text_field in data:
            if text_field.isdigit():
                mapped_data[int(text_field)] = data[text_field]

        if not mapped_data:
            raise ValueError("Extracted IDs contain non-integer values.")

        return {id_mapping[i].split("_")[0]: mapped_data[i] for i in mapped_data}

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"Error processing request: {e}")
        # Send a new request to the model
        if request_count < 3:
            return get_input_fields(xml_data, id_mapping, input_fields, request_count)
        return {}