import os
import json
import pandas as pd
import json
import time
import pandas as pd
import base64
import requests
import helpers.applications as applications
import argparse
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

PROMPT_PATH = './src/agents/tinytask_prompt.txt'
with open("config_open_ai.env", "r") as f:
    API_KEY = f.read().strip()

# Read the saved prompt
with open(PROMPT_PATH, 'r') as prompt_file:
    prompt_text = prompt_file.read()


def check_need_to_repredict_mini_tasks(graph):
    if isinstance(graph, dict):
        if 'processed_task_string' in graph and graph['processed_task_string']:
            return False
        for key, value in graph.items():
            if key == "actions":
                for action in graph[key]:
                    if "processed_task_string" in action and action["processed_task_string"]:
                        return False
            elif key == "edges":
                for edge in graph["edges"]:
                    return check_need_to_repredict_mini_tasks(edge["action"])
    elif isinstance(graph, list):
        for item in graph:
            if 'processed_task_string' in item and item['processed_task_string']:
                return False
            if check_need_to_repredict_mini_tasks(item):
                return True
    return True


def parse_tasks(graph, image_name=None):
    """Recursively parse the JSON-like graph structure to extract tasks, associated image names, and represent fields."""
    tasks = []

    if isinstance(graph, dict):
        # Update the image name if found at the current level
        if 'image_name' in graph and graph['image_name']:
            if "2025" in graph['image_name'] or "images" in graph['image_name']:
                image_name = graph['image_name']
                image_name = image_name.split("/")[-1]
            else:
                image_name = graph['image_name']

        # Check if there is a task string in this node and 'represent' has 'position' and 'size'
        if 'task_string' in graph and graph['task_string']:
            represent = graph.get("represent")
            if represent and "position" in represent and "size" in represent:
                position = represent["position"]
                size = represent["size"]
                x, y = position.get("x"), position.get("y")
                if x > 0 and y > 0:
                    tasks.append({
                        "id": graph.get("element", {}).get("id"),
                        "task_string": graph["task_string"],
                        "image_name": image_name,
                        "position_x": int(position.get("x", 0)),
                        "position_y": int(position.get("y", 0)),
                        "size_width": int(size.get("width", 0)),
                        "size_height": int(size.get("height", 0))  # Using 'heght' as is, assuming typo in example data
                    })

        # Recursively parse children or nested structures
        for key, value in graph.items():
            tasks.extend(parse_tasks(value, image_name))

    elif isinstance(graph, list):
        for item in graph:
            tasks.extend(parse_tasks(item, image_name))

    return tasks


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def process_tasks(FOLDER_PATH, df, max_retries=5, delay_between_retries=1):
    """Process tasks with OpenAI API and return the results."""
    results = []
    try:
        # Group tasks by image_name
        grouped = df.groupby('image_name')
    except KeyError:
        logger.error("No 'image_name' column found in the DataFrame. Please ensure the column exists.")
        return results

    # Iterate over each group
    for image_name, group in grouped:
        # Reset index to prepare sequential IDs
        group = group.reset_index(drop=True)
        id_mapping = {original_id: idx + 1 for idx, original_id in enumerate(group['id'])}

        # Prepare task list string
        tasks_str = "\n".join(f"{id_mapping[row['id']]}: {row['task_string']}" for _, row in group.iterrows())

        # Prepare prompt with tasks
        prompt_with_tasks = f"{prompt_text}\n\nTasks:\n{tasks_str}"

        # Encode the image
        if "cropped" in image_name:
            image_name = image_name[:-12] + ".png"
        image_path = FOLDER_PATH + image_name
        base64_image = encode_image(image_path)

        logger.info(f"Processing tasks for image: {image_name}")

        # Prepare payload for OpenAI API
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt_with_tasks
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 300
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }

        response_json = None
        for attempt in range(max_retries):
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()

            try:
                initial_json = response.json()
                response_content = initial_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                try:
                    response_json = json.loads(response_content.strip("```json\n"))
                    break  # Exit loop if parsing is successful
                except json.JSONDecodeError:
                    print(f"Attempt {attempt + 1} failed: Response is not JSON format.")
                    time.sleep(delay_between_retries)  # Wait before retrying
            except json.JSONDecodeError:
                print(f"Attempt {attempt + 1} failed: Response is not JSON format.")
                time.sleep(delay_between_retries)  # Wait before retrying

        results.append({
            'image_name': image_name,
            'original_ids': id_mapping,
            'response': response_json if response_json else "No valid JSON response received"
        })
    return results


def update_data_json(graph, df):
    """Recursively add 'processed_task_string' to each task in the JSON-like structure based on DataFrame predictions."""
    if isinstance(graph, dict):
        if 'task_string' in graph and 'element' in graph and 'id' in graph['element']:
            task_id = graph['element']['id']
            # Find the row in df that matches the task_id
            matched_row = df[df['id'] == task_id]
            if not matched_row.empty:
                graph['processed_task_string'] = matched_row.iloc[0]['formatted_task']
            else:
                graph['processed_task_string'] = None

        # Recursively process children or nested structures
        for key, value in graph.items():
            update_data_json(value, df)

    elif isinstance(graph, list):
        for item in graph:
            update_data_json(item, df)

    return graph


if __name__ == '__main__':
    # Get the root directory for data.json files
    arg_parser = argparse.ArgumentParser(description="Parse -a argument")
    arg_parser.add_argument("-a", type=str, help="The application bundle identifier")
    args = arg_parser.parse_args()
    app = applications.app_for_description_details(args.a)

    json_path = f"./output/{app.bundle_id}/graph/data.json"
    image_dir = f"./output/{app.bundle_id}/graph/images/"

    # Parse tasks from the current data.json file
    if not os.path.exists(json_path):
        print(f"Skipping {app.bundle_id}")
        exit(0)

    with open(json_path, 'r') as file:
        graph = json.load(file)

    print("Loaded graph", graph.keys())

    re_predict_mini_tasks = check_need_to_repredict_mini_tasks(graph)
    
    if re_predict_mini_tasks:
        print(f"Re-predicting tasks for {app.bundle_id}")
        # Save tasks to a DataFrame
        tasks = parse_tasks(graph)
        df = pd.DataFrame(tasks)

        # Process tasks with OpenAI API
        results = process_tasks(image_dir, df)

        # Map predictions to formatted task strings
        for result in results:
            response_json = result['response']
            formatted_tasks = response_json.get("formatted_tasks", {})
            for original_id, new_id in result['original_ids'].items():
                formatted_task = formatted_tasks.get(str(new_id))
                df.loc[df['id'] == original_id, 'formatted_task'] = formatted_task

        # Iterate over data.json again to add "processed_task_string"
        updated_graph = update_data_json(graph, df)

        # Update the data.json file with the responses
        with open(json_path, 'w') as file:
            json.dump(updated_graph, file, indent=4)
