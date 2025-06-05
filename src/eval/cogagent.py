import re
import datasets
from tqdm import tqdm
import json
from src.eval.logger import setup_json_logger
import os
from src.eval.utils import get_bbox_from_element, check_in, log_image, get_log_dir, convert_image
from PIL import Image
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, GenerationConfig
from src.eval.results_logger import ResultsLogger


#transformers==4.46.0



class AgentPipeline:
    def __init__(self, model_name="THUDM/cogagent-9b-20241220", device='cuda'):
        self.device = device
        self.torch_dtype = torch.bfloat16
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=self.torch_dtype,
            device_map="auto",
            trust_remote_code=True,
            attn_implementation="flash_attention_2",
        ).eval()
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        self.tmp_image_path = os.path.join(logs_dir, "tmp_image.png")

        format_dict = {
            "action_op_sensitive": "(Answer in Action-Operation-Sensitive format.)",
            "status_plan_action_op": "(Answer in Status-Plan-Action-Operation format.)",
            "status_action_op_sensitive": "(Answer in Status-Action-Operation-Sensitive format.)",
            "status_action_op": "(Answer in Status-Action-Operation format.)",
            "action_op": "(Answer in Action-Operation format.)",
        }

        self.format_str = format_dict["action_op"]

    def _predict(self, task, image):
        # Prepare query
        history_str = "\nHistory steps: "
        platform_str = "Mac"
        query = f"Task: {task}{history_str}\n{platform_str}{self.format_str}"

        
        inputs = self.tokenizer.apply_chat_template(
            [{"role": "user", "image": image, "content": query}],
            add_generation_prompt=True,
            tokenize=True,
            return_tensors="pt",
            return_dict=True,
        ).to(self.model.device)
        # Generate response
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs
            )
            outputs = outputs[:, inputs["input_ids"].shape[1]:]
            response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        return response

    def _parse_response(self, response, image_size):
        # Extract bounding boxes from the response
        if "CLICK" in response:
            match = re.search(r"CLICK\(box\=\[\[(.*?)\]\]", response)
            if match:
                click_str = match.group(1)
                click_coords = [int(coord.strip()) for coord in click_str.split(",")]
                click_point = [click_coords[0] / 1000 * image_size[0], click_coords[1] / 1000 * image_size[1]]
                x, y = int(click_point[0]), int(click_point[1])
                return {
                            "action": "click",
                            "coordinates": {
                                "original": {"x": x, "y": y},
                            }
                        }
        elif "TYPE" in response:
            match = re.search(r"text=\'(.*?)\'", response)
            if match:
                content = match.group(1).strip()
                return {
                    "action": "type",
                    "content": content
                }
        # If no specific action is recognized, return the full output
        return {"action": "unknown", "raw_output": response}


    def __call__(self, image, task, task_id):
        image = convert_image(image)
        result = self._predict(task, image)
        logger.info("Generated text", extra={"id": task_id, "text": result})
        return self._parse_response(result, image.size)


def handle_click(agent_action, bbox, image, task, task_id):
    if agent_action["action"] != "click":
        logger.warning("Agent did not return a click action", extra={"id": task_id, "action": agent_action["action"]})
        return False
    
    x = agent_action["coordinates"]["original"]["x"]
    y = agent_action["coordinates"]["original"]["y"]
    if check_in(bbox, x, y):
        logger.info("Prediction is within the bounding box", extra={"id": task_id})
        success = True
    else:
        logger.warning("Prediction is not within the bounding box", extra={"id": task_id, "prediction": (x, y)})
        log_image(image, task, bbox, (x, y), os.path.join(logs_dir, f"{task_id}.png"))
        success = False
    return success


def handle_type(action, agent_action, task_id):
    if agent_action["action"] != "type":
        logger.warning("Agent did not return a type action", extra={"id": task_id, "action": agent_action["action"]})
        return False
    agent_action_text = agent_action["content"]
    action_input = action.replace("type ", "")
    if action_input == agent_action_text:
        logger.info("Prediction is correct", extra={"id": task_id})
        success = True
    else:
        logger.warning("Prediction is incorrect", extra={"id": task_id, "prediction": agent_action_text})
        success = False
    return success


def main():
    agent = AgentPipeline()
    dataset = datasets.load_dataset("GUIrilla/GUIrilla-Task", split="test")

    results = []

    for item in tqdm(dataset):
        task_id = item["screen_id"]
        task = item["task"]
        action = item["action"]
        scaling_factor = item["scaling_factor"]
        image = item["image"]

        if scaling_factor == 2:
            image = image.resize((image.size[0] // 2, image.size[1] // 2), Image.LANCZOS)
            scaling_factor = 1

        if not task:
            item.pop("accessibility")
            print(item)
            raise
        
        element = json.loads(item["element_data"])
        bbox = get_bbox_from_element(element, scaling_factor)
        logger.info("Processing task", extra={"id": task_id, "task": task, "action": action, "bbox": bbox})

        agent_action = agent(image, task, task_id)

        if action.startswith("left click"):
            success = handle_click(agent_action, bbox, image, task, task_id)
        elif action.startswith("type"):
            success = handle_type(action, agent_action, task_id)
        else:
            logger.warning("Unknown action type", extra={"id": task_id, "action": agent_action["action"]})
            success = False

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
    logs_dir = get_log_dir("cogagent")
    logger = setup_json_logger(os.path.join(logs_dir, "logs.json"))

    results_logger = ResultsLogger(os.path.join(logs_dir, "results.csv"))

    main()