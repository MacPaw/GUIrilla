import re
import datasets
from tqdm import tqdm
import json
from src.eval.logger import setup_json_logger
import os
from src.eval.utils import get_bbox_from_element, check_in, log_image, get_log_dir, resize_image_bbox_qwen2
from PIL import Image
import torch
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor, GenerationConfig
from qwen_vl_utils import process_vision_info
import argparse
from src.eval.results_logger import ResultsLogger


#need transformers-4.51.3


AGENT_PROMPT = """
You are now operating in Executable Language Grounding mode. Your goal is to help users accomplish tasks by suggesting executable actions that best fit their needs. Your skill set includes both basic and custom actions:

1. Basic Actions
Basic actions are standardized and available across all platforms. They provide essential functionality and are defined with a specific format, ensuring consistency and reliability. 
Basic Action 1: CLICK 
    - purpose: Click at the specified position.
    - format: CLICK <point>[[x-axis, y-axis]]</point>
    - example usage: CLICK <point>[[101, 872]]</point>
       
Basic Action 2: TYPE
    - purpose: Enter specified text at the designated location.
    - format: TYPE [input text]
    - example usage: TYPE [Shanghai shopping mall]

Basic Action 3: SCROLL
    - purpose: SCROLL in the specified direction.
    - format: SCROLL [direction (UP/DOWN/LEFT/RIGHT)]
    - example usage: SCROLL [UP]
    
2. Custom Actions
Custom actions are unique to each user's platform and environment. They allow for flexibility and adaptability, enabling the model to support new and unseen actions defined by users. These actions extend the functionality of the basic set, making the model more versatile and capable of handling specific tasks.
Custom Action 1: LONG_PRESS 
    - purpose: Long press at the specified position.
    - format: LONG_PRESS <point>[[x-axis, y-axis]]</point>
    - example usage: LONG_PRESS <point>[[101, 872]]</point>
       
Custom Action 2: OPEN_APP
    - purpose: Open the specified application.
    - format: OPEN_APP [app_name]
    - example usage: OPEN_APP [Google Chrome]

Custom Action 3: PRESS_BACK
    - purpose: Press a back button to navigate to the previous screen.
    - format: PRESS_BACK
    - example usage: PRESS_BACK

Custom Action 4: PRESS_HOME
    - purpose: Press a home button to navigate to the home page.
    - format: PRESS_HOME
    - example usage: PRESS_HOME

Custom Action 5: PRESS_RECENT
    - purpose: Press the recent button to view or switch between recently used applications.
    - format: PRESS_RECENT
    - example usage: PRESS_RECENT

Custom Action 6: ENTER
    - purpose: Press the enter button.
    - format: ENTER
    - example usage: ENTER

Custom Action 7: WAIT
    - purpose: Wait for the screen to load.
    - format: WAIT
    - example usage: WAIT

Custom Action 8: COMPLETE
    - purpose: Indicate the task is finished.
    - format: COMPLETE
    - example usage: COMPLETE

In most cases, task instructions are high-level and abstract. Carefully read the instruction and action history, then perform reasoning to determine the most appropriate next action. Ensure you strictly generate two sections: Thoughts and Actions.
Thoughts: Clearly outline your reasoning process for current step.
Actions: Specify the actual actions you will take based on your reasoning. You should follow action format above when generating. 

Your current task instruction, action history, and associated screenshot are as follows:
Screenshot: 
"""

GROUNDING_PROMPT = 'In this UI screenshot, what is the position of the element corresponding to the command \"{}\" (with bbox)?"'


class AgentPipeline:
    def __init__(self, mode, device="cuda"):
        self.mode = mode
        if mode == "ground":
            model_name = "OS-Copilot/OS-Atlas-Base-7B"
        elif mode == "agent":
            model_name = "OS-Copilot/OS-Atlas-Pro-7B"
        else:
            raise ValueError(f"Unknown mode: {mode}")
        self.device = torch.device(device)
        self.torch_dtype = torch.bfloat16 if self.device.type == "cuda" else torch.float16
        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype="auto",
            device_map="auto",
            trust_remote_code=True,
            attn_implementation="flash_attention_2"
        ).eval()
        self.processor = AutoProcessor.from_pretrained("Qwen/Qwen2-VL-7B-Instruct", trust_remote_code=True, use_fast=True)
        self.tmp_image_path = os.path.join(logs_dir, "tmp_image.png")

    def _get_messages(self, task):
        if self.mode == "ground":
            prompt = GROUNDING_PROMPT.format(task)
            conversation = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "image": self.tmp_image_path,
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            return conversation
        elif self.mode == "agent":
            conversation = [
                {
                    "role": "user",
                    "content": [
                        { "type": "text", "text": AGENT_PROMPT },
                        {"type": "image", "image": self.tmp_image_path},
                        {"type": "text", "text": f"Task instruction: {task}\nHistory: null" }
                    ]
                }
            ]
            return conversation
        else:
            raise ValueError(f"Unknown mode: {self.mode}")
        


    def _predict(self, task):
        conversation = self._get_messages(task)

        text = self.processor.apply_chat_template(
            conversation, tokenize=False, add_generation_prompt=True
        )

        image_inputs, video_inputs = process_vision_info(conversation)
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self.model.device)

        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=1024,
                num_beams=3,
                do_sample=False,
                temperature=None,
                top_k=None,
                top_p=None,
            )

        generated_ids = [output_ids[len(input_ids):] for input_ids, output_ids in zip(inputs.input_ids, output_ids)]
        output_text = self.processor.batch_decode(generated_ids, skip_special_tokens=False, clean_up_tokenization_spaces=False)[0]

        return output_text

    def _parse_output(self, output, image_size):
        if self.mode == "ground":
            # Extract text between <|box_start|> and <|box_end|> tags
            match = re.search(r'<\|box_start\|\>(.*?)<\|box_end\|\>', output)
            
            if match:
                # Get the text between the tags
                extracted_text = match.group(1)
                
                # Remove parentheses and brackets
                cleaned_text = re.sub(r'[()\[\]]', '', extracted_text)
                
                # Extract four numbers from the cleaned text
                pattern = r"(\d+),\s*(\d+),\s*(\d+),\s*(\d+)"
                numbers = re.findall(pattern, cleaned_text)
                
                if numbers:
                    # Return the first match as tuples of integers
                    x1, y1, x2, y2 = map(int, numbers[0])
                    x = (x1 + x2) / 2
                    y = (y1 + y2) / 2

                    x = int(x / 1000 * image_size[0])
                    y = int(y / 1000 * image_size[1])

                    return {
                        "action": "click",
                        "coordinates": {
                            "original": {"x": x, "y": y},
                        }
                    }
            
            return {"action": "unknown", "raw_output": output}
        elif self.mode == "agent":
            # Extract the action and coordinates from the output
            match = re.search(r'actions:\n(.*)', output)  #actions:\nCLICK <point>[[235,511]]</point><|im_end|>
            if match:
                action_text = match.group(1).strip()
                action = action_text.split()

                if len(action) == 0:
                    return {"action": "unknown", "raw_output": output} 
                
                if action[0] == "CLICK":
                    coordinates_match = re.search(r'\[\[(\d+),\s?(\d+)\]\]', action_text)
                    if coordinates_match:
                        x, y = map(int, coordinates_match.groups())
                        x = int(x / 1000 * image_size[0])
                        y = int(y / 1000 * image_size[1])
                        return {
                            "action": "click",
                            "coordinates": {
                                "original": {"x": x, "y": y},
                            }
                        }
                elif action[0] == "TYPE":
                    text_match = re.search(r'\[(.*?)\]', action_text)
                    if text_match:
                        text = text_match.group(1).strip()
                        return {
                            "action": "type",
                            "content": text
                        }
            
            return {"action": "unknown", "raw_output": output}

    def __call__(self, image, task, task_id):
        image.save(self.tmp_image_path)
        result = self._predict(task)
        logger.info("Generated text", extra={"id": task_id, "text": result})
        parsed_result = self._parse_output(result, image.size)

        return parsed_result


def handle_click(agent_action, bbox, image, task, task_id):
    if agent_action["action"] == "click":
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
    else:
        logger.warning("Prediction is not a left click", extra={"id": task_id, "prediction": agent_action})
        return False


def handle_type(action, agent_action, task_id):
    if agent_action["action"] == "type":
        agent_action_text = agent_action["content"]
        action_input = action.replace("type ", "")
        if action_input == agent_action_text:
            logger.info("Prediction is correct", extra={"id": task_id})
            success = True
        else:
            logger.warning("Prediction is incorrect", extra={"id": task_id, "prediction": agent_action_text})
            success = False
        return success
    else:
        logger.warning("Prediction is not a type action", extra={"id": task_id, "prediction": agent_action})
        return False


def main(mode, device):
    agent = AgentPipeline(mode=mode, device=device)
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

        # if "type" not in action:
        #     continue
        # if not task:
        #     item.pop("accessibility")
        #     print(item)
        #     raise
        
        element = json.loads(item["element_data"])
        bbox = get_bbox_from_element(element, scaling_factor)
        logger.info("Processing task", extra={"id": task_id, "task": task, "action": action, "bbox": bbox})


        image, bbox = resize_image_bbox_qwen2(image, bbox)

        agent_action = agent(image, task, task_id)

        if mode == "ground":
            success = handle_click(agent_action, bbox, image, task, task_id)
        else:
            if action.startswith("left click"):
                success = handle_click(agent_action, bbox, image, task, task_id)
            elif action.startswith("type"):
                success = handle_type(action, agent_action, task_id)
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
    parser = argparse.ArgumentParser(description="Run the agent evaluation pipeline.")
    parser.add_argument("--mode", type=str, default="ground", choices=["ground", "agent"], help="Mode to run the agent evaluation pipeline.")
    parser.add_argument("--device", type=str, default="cuda", help="Device to run the model on.")
    # parser.add_argument("--model_size", type=str, default="4B", choices=["4B", "7B"], help="Model size to use.")

    args = parser.parse_args()

    logs_dir = get_log_dir("atlas_" + args.mode)
    logger = setup_json_logger(os.path.join(logs_dir, "logs.json"))

    results_logger = ResultsLogger(os.path.join(logs_dir, "results.csv"))

    main(args.mode, args.device)