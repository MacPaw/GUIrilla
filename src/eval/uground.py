import re
import datasets
from tqdm import tqdm
import json
from src.eval.logger import setup_json_logger
import os
from src.eval.utils import get_bbox_from_element, check_in, log_image, get_log_dir, resize_image_bbox_qwen2
from PIL import Image
import torch
from transformers import AutoProcessor, AutoModelForCausalLM, Qwen2VLForConditionalGeneration
from qwen_vl_utils import process_vision_info
import argparse
from src.eval.results_logger import ResultsLogger


class AgentPipeline:
    def __init__(self, model_name="osunlp/UGround-V1-2B", device="cuda"):
        self.device = torch.device(device)
        self.torch_dtype = torch.bfloat16 if self.device.type == "cuda" else torch.float16
        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype=self.torch_dtype,
            device_map=self.device,
            trust_remote_code=True
        )
        self.processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True, use_fast=True)
        self.tmp_image_path = os.path.join(logs_dir, "tmp_image.png")


    def _predict(self, task):
        conversation = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": self.tmp_image_path},
                    {
                        "type": "text",
                        "text": f"""
Your task is to help the user identify the precise coordinates (x, y) of a specific area/element/object on the screen based on a description.

- Your response should aim to point to the center or a representative point within the described area/element/object as accurately as possible.
- If the description is unclear or ambiguous, infer the most relevant area or element based on its likely context or purpose.
- Your answer should be a single string (x, y) corresponding to the point of the interest.

Description: {task}

Answer:"""
                    },
            ],
            }
        ]

        

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
        ).to(self.device)
        
        # # add ids
        # prompt_with_id = processor.apply_chat_template(conversation, add_generation_prompt=True, add_vision_id=True)

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
        output_text = self.processor.batch_decode(generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=True)[0]

        return output_text

    def _parse_output(self, output, image_size):

        # Check for click action
        click_match = re.search(r"\((\d+),\s?(\d+)\)", output)
        if click_match:
            x, y = map(int, click_match.groups())
            x_scaled = int(x * image_size[0] / 1000)
            y_scaled = int(y * image_size[1] / 1000)
            return {
                "action": "click",
                "coordinates": {
                    "original": {"x": x, "y": y},
                    "scaled": {"x": x_scaled, "y": y_scaled},
                }
            }

        # If no specific action is recognized, return the full output
        return {"action": "unknown", "raw_output": output}

    def __call__(self, image, task, task_id):
        image.save(self.tmp_image_path)
        
        result = self._predict(task)
        logger.info("Generated text", extra={"id": task_id, "text": result})
        parsed_result = self._parse_output(result, image.size)

        if parsed_result['action'] == 'click':
            original_output = parsed_result['coordinates']['scaled']
            return original_output["x"], original_output["y"]
        else:
            raise ValueError(f"The model didn't provide a valid click action. Command was: {task}")


def main(device, model_size):
    if model_size == "2B":
        model_name = "osunlp/UGround-V1-2B"
    elif model_size == "7B":
        model_name = "osunlp/UGround-V1-7B"
    else:
        raise ValueError(f"Unknown model size: {model_size}")
    clicker = AgentPipeline(device=device, model_name=model_name)
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
        image, bbox = resize_image_bbox_qwen2(image, bbox)

        try:
            x, y = clicker(image, task, task_id)
            if check_in(bbox, x, y):
                logger.info("Prediction is within the bounding box", extra={"id": task_id})
                success = True
            else:
                logger.warning("Prediction is not within the bounding box", extra={"id": task_id, "prediction": (x, y)})
                log_image(image, task, bbox, (x, y), os.path.join(logs_dir, f"{task_id}.png"))
                success = False
        except ValueError as e:
            logger.error("Error during prediction", extra={"id": task_id, "error": str(e)})
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
    parser = argparse.ArgumentParser(description="Run the agent evaluation pipeline.")
    parser.add_argument("--device", type=str, default="cuda", help="Device to run the model on.")
    parser.add_argument("--model_size", type=str, default="2B", choices=["2B", "7B"], help="Model size to use.")

    args = parser.parse_args()

    logs_dir = get_log_dir("uground_" + args.model_size)
    logger = setup_json_logger(os.path.join(logs_dir, "logs.json"))

    results_logger = ResultsLogger(os.path.join(logs_dir, "results.csv"))

    main(args.device, args.model_size)