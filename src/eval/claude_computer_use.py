import datasets
import anthropic
import json
from tqdm import tqdm
from src.eval.logger import setup_json_logger
import os
from PIL import Image
from src.eval.utils import get_bbox_from_element, check_in, log_image, get_log_dir, encode_screenshot, resize_image_and_bbox_width
from src.eval.results_logger import ResultsLogger



def call_computer_use(image, task, task_id):
    screenshot_base64 = encode_screenshot(image)

    system = """* You are utilizing a MacOS computer
* You will be given a task and a screenshot of the computer screen
* You have to complete the task using the computer tool in a single action, without any other actions
* You CANNOT take a screenshot, use the provided screenshot only
* You will respond with a computer tool call"""
    
    response = client.beta.messages.create(
        model="claude-3-7-sonnet-20250219",
        max_tokens=4096,
        tools=[
            {
            "type": "computer_20250124",
            "name": "computer",
            "display_width_px": image.width,
            "display_height_px": image.height,
            "display_number": 1,
            }
        ],
        messages=[{"role": "user", "content": [
                {
                "type": "text",
                "text": task
                },
                # Optional: include a screenshot of the initial state of the environment
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": screenshot_base64,
                    },
                }
            ]}],
        betas=["computer-use-2025-01-24"],
        thinking={"type": "enabled", "budget_tokens": 1024},
        system=system,
        # temperature=0,
    )

    logger.info("Claude response", extra={"id": task_id, "response": response.content})
    tool_use_blocks = [block for block in response.content if block.type == "tool_use"]
    logger.info("Tool use blocks", extra={"id": task_id, "tool_use_blocks": tool_use_blocks})
    return tool_use_blocks


def handle_click(bbox, computer_call_action, image, task, task_id):
    if computer_call_action["action"] == "left_click":
        x, y = computer_call_action["coordinate"]
        if check_in(bbox, x, y):
            logger.info("Computer call action is within the bounding box", extra={"id": task_id})
            success = True
        else:
            logger.warning("Computer call action is not within the bounding box", extra={"id": task_id, "computer_call_action": computer_call_action})
            log_image(image, task, bbox, (x, y), os.path.join(logs_dir, f"{task_id}.png"))
            success = False
        return success
    else:
        logger.warning("Computer call action is not a left click", extra={"id": task_id, "computer_call_action": computer_call_action})
        return False


def handle_type(action, computer_call_action, task_id):
    if computer_call_action["action"] == "type":
        computer_call_text = computer_call_action["text"]
        action_input = action.replace("type ", "")
        if action_input == computer_call_text:
            logger.info("Computer call action is correct", extra={"id": task_id})
            success = True
        else:
            logger.warning("Computer call action is incorrect", extra={"id": task_id, "computer_call_action": computer_call_text})
            success = False
        return success
    else:
        logger.warning("Computer call action is not a type", extra={"id": task_id, "computer_call_action": computer_call_action})
        return False


def main():
    dataset = datasets.load_dataset("GUIrilla/GUIrilla-Task", split="test")

    results = []

    for item in tqdm(dataset):
        task_id = item["screen_id"]
        task = item["task"]
        action = item["action"]
        scaling_factor = item["scaling_factor"]
        if not task:
            item.pop("accessibility")
            print(item)
            raise

        element = json.loads(item["element_data"])
        bbox = get_bbox_from_element(element, scaling_factor)
        logger.info("Processing task", extra={"id": task_id, "task": task, "action": action, "bbox": bbox})

        image = item["image"]
        image, bbox = resize_image_and_bbox_width(image, bbox)
        
        computer_calls = call_computer_use(image, task, task_id)
        if not computer_calls:
            logger.warning("No computer calls found", extra={"id": task_id})
            success = False
        else:
            computer_call = computer_calls[0]
            computer_call_action = computer_call.input
            if action.startswith("left click"):
                success = handle_click(bbox, computer_call_action, image, task, task_id)
            elif action.startswith("type"):
                success = handle_type(action, computer_call_action, task_id)
            else:
                logger.warning("Action is not supported", extra={"id": task_id, "action": action})
                raise ValueError(f"Unknown action type: {action}")
        results.append(success)
        results_logger.log(
            id=task_id,
            task=task,
            original_task=item["original_task"],
            task_category=item["task_category"],
            element_category=item["element_category"],
            success=success)

    # calculate accuracy
    accuracy = sum(results) / len(results)
    print(f"Accuracy: {accuracy:.2%}")
    logger.info("Accuracy", extra={"accuracy": accuracy})


if __name__ == "__main__":
    with open("config_claude.env", "r") as f:
        api_key = f.read().strip()
    client = anthropic.Anthropic(api_key=api_key)

    logs_dir = get_log_dir("claude")
    logger = setup_json_logger(os.path.join(logs_dir, "logs.json"))

    results_logger = ResultsLogger(os.path.join(logs_dir, "results.csv"))

    main()