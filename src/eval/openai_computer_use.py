import datasets
from openai import OpenAI, BadRequestError
import json
from tqdm import tqdm
from src.eval.logger import setup_json_logger
import os
from src.eval.utils import get_bbox_from_element, check_in, log_image, get_log_dir, encode_screenshot
from src.eval.results_logger import ResultsLogger


def confirm_computer_use(response_id, image, task_id):
    # screenshot_base64 = encode_screenshot(image)
    # Send the screenshot back as a computer_call_output
    try: 
        response = client.responses.create(
            model="computer-use-preview",
            previous_response_id=response_id,
            tools=[
                {
                    "type": "computer_use_preview",
                    "display_width": image.width,
                    "display_height": image.height,
                    "environment": "mac"
                }
            ],
            input=[
                {
                "role": "user",
                "content": [
                    {
                    "type": "input_text",
                    "text": "Confirming",
                    },
                    # {
                    #     "type": "input_image",
                    #     "image_url": f"data:image/png;base64,{screenshot_base64}"
                    # }
                ]
                }
            ],
            truncation="auto",
            temperature=0,
        )
    except BadRequestError as e:
        logger.error("BadRequestError", extra={"id": task_id, "error": str(e)})
        response = client.responses.create(
            model="computer-use-preview",
            previous_response_id=response_id,
            tools=[
                {
                    "type": "computer_use_preview",
                    "display_width": image.width,
                    "display_height": image.height,
                    "environment": "mac"
                }
            ],
            input=[
                {
                "role": "user",
                "content": [
                    {
                    "type": "input_text",
                    "text": "Confirming",
                    }
                ]
                }
            ],
            truncation="auto",
            temperature=0,
        )
    logger.info("OpenAI response on confirmation", extra={"id": task_id, "response.output": response.output})
    computer_calls = [item for item in response.output if item.type == "computer_call"]
    logger.info("Computer calls", extra={"id": task_id, "computer_calls": computer_calls})
    return computer_calls


def call_computer_use(image, task, task_id):
    screenshot_base64 = encode_screenshot(image)
    response = client.responses.create(
        model="computer-use-preview",
        tools=[{
            "type": "computer_use_preview",
            "display_width": image.width,
            "display_height": image.height,
            "environment": "mac"
        }],    
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": "* You are utilizing a MacOS computer\n"
                                "* You will be given a task and a screenshot of the computer screen\n"
                                "* You have to complete the task using the computer tool in a single action, without any other actions\n"
                                "* You CANNOT take a screenshot, use the provided screenshot only\n"
                                "* You will respond with a computer call"
                    }
                ]
            },
            {
            "role": "user",
            "content": [
                {
                "type": "input_text",
                "text": task
                },
                # Optional: include a screenshot of the initial state of the environment
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{screenshot_base64}"
                }
            ]
            }
        ],
        reasoning={
            "summary": "concise",
        },
        truncation="auto",
        temperature=0,
    )

    logger.info("OpenAI response", extra={"id": task_id, "response": response})
    computer_calls = [item for item in response.output if item.type == "computer_call"]
    logger.info("Computer calls", extra={"id": task_id, "computer_calls": computer_calls})
    # response_reasoning_items = [item for item in response.output if item.type == "reasoning"]
    # logger.info("Response reasoning items", extra={"id": task_id, "response_reasoning_items": response_reasoning_items})
    if not computer_calls:
        logger.warning("No computer calls found. Confirming..", extra={"id": task_id})
        computer_calls = confirm_computer_use(response.id, image, task_id)
    return computer_calls


def handle_click(bbox, computer_call_action, image, task, task_id):
    if computer_call_action.type == "click" and computer_call_action.button == "left":

        if check_in(bbox, computer_call_action.x, computer_call_action.y):
            logger.info("Computer call action is within the bounding box", extra={"id": task_id})
            success = True
        else:
            logger.warning("Computer call action is not within the bounding box", extra={"id": task_id, "computer_call_action": computer_call_action})
            log_image(image, task, bbox, (computer_call_action.x, computer_call_action.y), os.path.join(logs_dir, f"{task_id}.png"))
            success = False
        return success
    else:
        logger.warning("Computer call action is not a left click", extra={"id": task_id, "computer_call_action": computer_call_action})
        return False


def handle_type(action, computer_call_action, task_id):
    if computer_call_action.type == "type":
        computer_call_text = computer_call_action.text
        action_input = action.replace("type ", "")
        if action_input == computer_call_text:
            logger.info("Computer call action is correct", extra={"id": task_id})
            success = True
        else:
            logger.warning("Computer call action is incorrect", extra={"id": task_id, "computer_call_action": computer_call_text})
            success = False
        return success
    else:
        logger.warning("Computer call action is not a type action", extra={"id": task_id, "computer_call_action": computer_call_action})
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

        computer_calls = call_computer_use(item["image"], task, task_id)
        if not computer_calls:
            logger.warning("No computer calls found after confirming", extra={"id": task_id})
            success = False
        else:
            computer_call = computer_calls[0]
            computer_call_action = computer_call.action
            if action.startswith("left click"):
                success = handle_click(bbox, computer_call_action, item["image"], task, task_id)
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
    with open("config_open_ai.env", "r") as f:
        api_key = f.read().strip()
    client = OpenAI(api_key=api_key)

    logs_dir = get_log_dir("openai")
    logger = setup_json_logger(os.path.join(logs_dir, "logs.json"))

    results_logger = ResultsLogger(os.path.join(logs_dir, "results.csv"))

    main()