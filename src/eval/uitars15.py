import re
import datasets
from tqdm import tqdm
import json
from src.eval.logger import setup_json_logger
import os
from src.eval.utils import get_bbox_from_element, check_in, log_image, get_log_dir, resize_image_bbox_qwen25
from PIL import Image
import torch
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
import argparse
from src.eval.results_logger import ResultsLogger


AGENT_PROMPT = """You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task.

## Output Format
```
Thought: ...
Action: ...
```

## Action Space

click(start_box='<|box_start|>(x1,y1)<|box_end|>')
left_double(start_box='<|box_start|>(x1,y1)<|box_end|>')
right_single(start_box='<|box_start|>(x1,y1)<|box_end|>')
drag(start_box='<|box_start|>(x1,y1)<|box_end|>', end_box='<|box_start|>(x3,y3)<|box_end|>')
hotkey(key='')
type(content='xxx') # Use escape characters \\', \\\", and \\n in content part to ensure we can parse the content in normal python string format. If you want to submit your input, use \\n at the end of content. 
scroll(start_box='<|box_start|>(x1,y1)<|box_end|>', direction='down or up or right or left')
wait() #Sleep for 5s and take a screenshot to check for any changes.
finished(content='xxx') # Use escape characters \\', \\", and \\n in content part to ensure we can parse the content in normal python string format.


## Note
- Use {language} in `Thought` part.
- Write a small plan and finally summarize your next action (with its target element) in one sentence in `Thought` part.

## User Instruction
{instruction}
"""

GROUNDING_PROMPT = """You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task. \n\n## Output Format\n\nAction: ...\n\n\n## Action Space\nclick(start_box='<|box_start|>(x1,y1)<|box_end|>')\n\n## User Instruction
{instruction}"""


class AgentPipeline:
    def __init__(self, mode, model_name="ByteDance-Seed/UI-TARS-1.5-7B", device="cuda:1"):
        self.mode = mode
        self.device = torch.device(device)
        self.torch_dtype = torch.bfloat16 if self.device.type == "cuda" else torch.float16
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype=self.torch_dtype,
            device_map="auto",
            attn_implementation="flash_attention_2",
            trust_remote_code=True,
        ).eval()
        self.processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True, use_fast=True)
        self.language = "English"
        self.tmp_image_path = os.path.join(logs_dir, "tmp_image.png")

    def _predict(self, task):
        if self.mode == "ground":
            prompt = GROUNDING_PROMPT
        elif self.mode == "agent":
            prompt = AGENT_PROMPT
        else:
            raise ValueError(f"Unknown mode: {self.mode}")
        system_prompt = prompt.format(instruction=task, language=self.language)
        conversation = [
            {
                "role": "system",
                "content": [{ "type": "text", "text": system_prompt }]
            },
            {
                "role": "user",
                "content": [
                    {"type": "image", "path": self.tmp_image_path}
                ]
            }
        ]

        # default:
        inputs = self.processor.apply_chat_template(
            conversation,
            video_fps=1,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt"
        ).to(self.model.device)
        
        # # add ids
        # prompt_with_id = processor.apply_chat_template(conversation, add_generation_prompt=True, add_vision_id=True)

        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=1024,
                num_beams=3,
                do_sample=False,
            )

        generated_ids = [output_ids[len(input_ids):] for input_ids, output_ids in zip(inputs.input_ids, output_ids)]
        output_text = self.processor.batch_decode(generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=True)[0]
        return output_text

    def _parse_output(self, output):
        if self.mode == "ground":
            # Check for click action
            click_match = re.search(r"click\(start_box='\((\d+),\s?(\d+)\)'\)", output)
            if click_match:
                x, y = map(int, click_match.groups())
                return {
                    "action": "click",
                    "coordinates": {
                        "original": {"x": x, "y": y},
                    }
                }

            # If no specific action is recognized, return the full output
            return {"action": "unknown", "raw_output": output}
        elif self.mode == "agent":
            match = re.search(r'Action: (.*)', output)
            if match:
                action = match.group(1).strip()
                if action.startswith("click"):
                    click_match = re.search(r"click\(start_box='\((\d+),\s?(\d+)\)'\)", action)
                    if click_match:
                        x, y = map(int, click_match.groups())
                        return {
                            "action": "click",
                            "coordinates": {
                                "original": {"x": x, "y": y},
                            }
                        }
                elif action.startswith("type"):
                    type_match = re.search(r"type\(content='(.*)'\)", action)
                    if type_match:
                        content = type_match.group(1).strip()
                        return {
                            "action": "type",
                            "content": content
                        }
            # If no specific action is recognized, return the full output
            return {"action": "unknown", "raw_output": output}

    def __call__(self, image, task, task_id):
        image.save(self.tmp_image_path)
        result = self._predict(task)
        logger.info("Generated text", extra={"id": task_id, "text": result})
        parsed_result = self._parse_output(result)

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

        if not task:
            item.pop("accessibility")
            print(item)
            raise
        
        element = json.loads(item["element_data"])
        bbox = get_bbox_from_element(element, scaling_factor)
        logger.info("Processing task", extra={"id": task_id, "task": task, "action": action, "bbox": bbox})


        # Resize image and bounding box
        image, bbox = resize_image_bbox_qwen25(image, bbox)

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

    args = parser.parse_args()

    logs_dir = get_log_dir("uitars15_" + args.mode)
    logger = setup_json_logger(os.path.join(logs_dir, "logs.json"))

    results_logger = ResultsLogger(os.path.join(logs_dir, "results.csv"))

    main(args.mode, args.device)