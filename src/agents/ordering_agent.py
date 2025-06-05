from agents.utilities import extract_ids_from_output, pretty_print_xml
from openai import OpenAI
import json
import random

with open("config_open_ai.env", "r") as f:
    api_key = f.read().strip()
client = OpenAI(api_key=api_key)

with open("src/agents/ordering_prompt.txt", "r") as f:
    ASSISTANT_PROMPT = f.read()


def get_clicking_order(xml_data, id_mapping, retries=3) -> list[str] | None:
    xml_data = pretty_print_xml(xml_data)
    try:
        response = client.chat.completions.create(
            # model="gpt-4o",
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": ASSISTANT_PROMPT},
                {"role": "user", "content": xml_data},
            ],
        )

        predicted_order = response.choices[0].message.content
        print(predicted_order)

        data = json.loads(predicted_order)
        login_page = False
        system_access_required = False
        if "action_order" not in data:
            print("Wrong output format, sending a new request.")
            get_clicking_order(xml_data, id_mapping)
        # For tags like login or system requirements we can assume is LLM didn't include id - it's false
        if "login_page" in data:
            if str(data["login_page"]).lower() == "true":
                login_page = True
        if "system_access_required" in data:
            if str(data["system_access_required"]).lower() == "true":
                system_access_required = True

        # Extract and combine numbers
        id_order = []
    
        for action in data["action_order"]:
            # Extract category and its elements
            if type(action) is not dict:
                print(f"Expected dictionary, got {type(action)}")
                continue
            for category_name, ids in action.items():
                # Check if category is dynamic or repeated
                if category_name.startswith("dynamic_") or category_name.startswith("repeated_"):
                    if ids:
                        # id_order.extend(ids)
                        id_order.append(random.choice(ids)) # TODO test if works
                else:
                    # Add all IDs from other categories
                    id_order.extend(ids)
        
        # Check for non-integer values
        for i in range(len(id_order)):
            if not isinstance(id_order[i], int):
                try:
                    id_order[i] = int(id_order[i])  # Convert to integer in place
                except Exception as e:
                    print(f"Non-integer ID encountered: {id_order[i]}. Sending a new request.")
                    if retries > 0:
                        return get_clicking_order(xml_data, id_mapping, retries - 1)
                    return None
                
        if not id_order:
            print("Empty ID order, retrying...")
            if retries > 0:
                return get_clicking_order(xml_data, id_mapping, retries - 1)
            return None

        # Sometimes LLMs may miss some elements, but they also filter out groups and unnecessary cells
        # So currently we leave it like this
        # missing_ids = set(id_mapping.keys()) - set(id_order)
        # id_order.extend(missing_ids)
        ordered_ids = [id_mapping[i] for i in id_order]
        if ordered_ids is None or len(ordered_ids) == 0:
            print(f"Children order is None")
            return None
        result = {"action_order": [id_mapping[i] for i in id_order], "login_page": login_page, "system_access_required": system_access_required}
        return result
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"Error processing request: {e}")
        # Send a new request to the model
        return get_clicking_order(xml_data, id_mapping)
