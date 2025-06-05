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

click(point='(x,y)')
left_double(point='(x,y)')
right_single(point='(x,y)')
drag(start='(x1,y1)', end='(x2,y2)')
hotkey(key='')
type(content='xxx') # Use escape characters \\', \\\", and \\n in content part to ensure we can parse the content in normal python string format. If you want to submit your input, use \\n at the end of content. 
scroll(start='(x,y)', direction='down or up or right or left')
wait() #Sleep for 5s and take a screenshot to check for any changes.
finished(content='xxx') # Use escape characters \\', \\", and \\n in content part to ensure we can parse the content in normal python string format.


## Note
- Use {language} in `Thought` part.
- Write a small plan and finally summarize your next action (with its target element) in one sentence in `Thought` part.

## User Instruction
{instruction}
"""

GROUNDING_PROMPT = """You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task. \n\n## Output Format\n\nAction: ...\n\n\n## Action Space\nclick(point='(x,y)')\n\n## User Instruction
{instruction}"""


class AgentPipeline:
    def __init__(self, mode, model_name="Qwen/Qwen2.5-VL-3B-Instruct", device="cuda"):
        self.mode = mode
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            attn_implementation="flash_attention_2",
            trust_remote_code=True
        )
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
                temperature=None,
            )

        generated_ids = [output_ids[len(input_ids):] for input_ids, output_ids in zip(inputs.input_ids, output_ids)]
        output_text = self.processor.batch_decode(generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=True)[0]
        return output_text

    def _parse_output(self, output):
        if self.mode == "ground":
            # Check for click action
            click_match = re.search(r"click\(point\=\'?\((\d+),\s?(\d+)\)\'?\)", output)
            if click_match:
                x, y = map(int, click_match.groups())
                return {
                    "action": "click",
                    "coordinates": {
                        "original": {"x": x, "y": y},
                    }
                }
        elif self.mode == "agent":
            match = re.search(r'Action: (.*)', output)
            if match:
                action = match.group(1).strip()
                if action.startswith("click"):
                    click_match = re.search(r"click\(point\=\'?\((\d+),\s?(\d+)\)\'?\)", output)
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
    

def handle_click(parsed_result, bbox, image, task, task_id):
    if parsed_result["action"] == "click":
        original_output = parsed_result['coordinates']['original']
        x, y = original_output["x"], original_output["y"]
        if check_in(bbox, x, y):
            logger.info("Prediction is within the bounding box", extra={"id": task_id})
            success = True
        else:
            logger.warning("Prediction is not within the bounding box", extra={"id": task_id, "prediction": (x, y)})
            log_image(image, task, bbox, (x, y), os.path.join(logs_dir, f"{task_id}.png"))
            success = False
        return success
    else:
        logger.warning("Unknown action type", extra={"id": task_id, "action": parsed_result["action"]})
        return False


def handle_type(parsed_result, action, task_id):
    if parsed_result["action"] == "type":
        action_input = action.replace("type ", "")
        generated_text = parsed_result['content']
        logger.info("Generated text for typing", extra={"id": task_id, "text": generated_text})
        if action_input == generated_text:
            logger.info("Generated text is correct", extra={"id": task_id})
            success = True
        else:
            logger.warning("Generated text is incorrect", extra={"id": task_id, "generated_text": generated_text})
            success = False
        return success
    else:
        logger.warning("Unknown action type", extra={"id": task_id, "action": parsed_result["action"]})
        return False


def main(mode, device, model_size):
    if model_size == "3B":
        model_name = "Qwen/Qwen2.5-VL-3B-Instruct"
    elif model_size == "7B":
        model_name = "Qwen/Qwen2.5-VL-7B-Instruct"
    else:
        raise ValueError(f"Unknown model size: {model_size}")
    agent = AgentPipeline(mode=mode, model_name=model_name, device=device)
    dataset = datasets.load_dataset("GUIrilla/GUIrilla-Task", split="test")

    results = []

    for item in tqdm(dataset):
        task_id = item["screen_id"]
        task = item["task"]
        action = item["action"]
        scaling_factor = item["scaling_factor"]
        image = item["image"]

        if not task:
            item.pop("accessibility")
            print(item)
            raise

        if scaling_factor == 2:
            image = image.resize((image.size[0] // 2, image.size[1] // 2), Image.LANCZOS)
            scaling_factor = 1
        
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
                success = handle_type(agent_action, action, task_id)
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
    parser.add_argument("--model_size", type=str, default="3B", choices=["3B", "7B"], help="Model size to use.")

    args = parser.parse_args()

    logs_dir = get_log_dir("qwen25_" + args.model_size + "_" + args.mode)
    logger = setup_json_logger(os.path.join(logs_dir, "logs.json"))

    results_logger = ResultsLogger(os.path.join(logs_dir, "results.csv"))

    main(args.mode, args.device, args.model_size)