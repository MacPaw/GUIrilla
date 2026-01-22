from transformers import AutoModelForCausalLM, AutoProcessor
import torch
import re
import datasets
from tqdm import tqdm
import json
from src.eval.logger import setup_json_logger
import os
from src.eval.utils import get_bbox_from_element, check_in, log_image, get_log_dir, convert_image
from PIL import Image
import argparse
from src.eval.results_logger import ResultsLogger


COMMAND_TEMPLATE = "What to do to execute the command?  {task_string}"


class TinyClickPipeline:
    def __init__(self, model_name="Samsung/TinyClick", device="cuda"):
        self.device = torch.device(device)
        self.torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        self.processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=self.torch_dtype,
            trust_remote_code=True
        ).to(self.device)
        self.model_input_size = (768, 768)  # Default input size for TinyClick

    def _predict(self, image, command):
        input_text = f"{command.strip()}".lower()
        inputs = self.processor(text=input_text, images=image, return_tensors="pt").to(self.device, self.torch_dtype)

        with torch.no_grad():
            outputs = self.model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=1024,
                num_beams=3,
                do_sample=False
            )

        generated_text = self.processor.batch_decode(outputs, skip_special_tokens=False)[0]
        return generated_text

    def _parse_output(self, output, image_size):
        # Remove special tokens
        clean_output = output.replace("</s>", "").replace("<s>", "").strip()

        # Check for click action
        click_match = re.search(r'click <loc_(\d+)><loc_(\d+)>', clean_output)
        if click_match:
            x, y = map(int, click_match.groups())
            x_scaled = int(x * (image_size[0] / 1000))
            y_scaled = int(y * (image_size[1] / 1000))
            return {
                "action": "click",
                "coordinates": {
                    "original": {"x": x, "y": y},
                    "scaled": {"x": x_scaled, "y": y_scaled}
                }
            }

        # If no specific action is recognized, return the full output
        return {"action": "unknown", "raw_output": clean_output}

    def __call__(self, image, task):
        image = convert_image(image)
        command = COMMAND_TEMPLATE.format(task_string=task)
        result = self._predict(image, command)
        parsed_result = self._parse_output(result, image.size)

        if parsed_result['action'] == 'click':
            scaled_output = parsed_result['coordinates']['scaled']
            return scaled_output["x"], scaled_output["y"]
        else:
            raise f"The model didn't provide a valid click action. Command was: {command}"


def main(device):
    agent = TinyClickPipeline(device=device)
    dataset = datasets.load_dataset("GUIrilla/GUIrilla-Task", split="test", streaming=True)

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

        x, y = agent(image, task)

        if check_in(bbox, x, y):
            logger.info("Prediction is within the bounding box", extra={"id": task_id})
            success = True
        else:
            logger.warning("Prediction is not within the bounding box", extra={"id": task_id, "prediction": (x, y)})
            log_image(image, task, bbox, (x, y), os.path.join(logs_dir, f"{task_id}.png"))
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

    args = parser.parse_args()

    logs_dir = get_log_dir("tinyclick")
    logger = setup_json_logger(os.path.join(logs_dir, "logs.json"))

    results_logger = ResultsLogger(os.path.join(logs_dir, "results.csv"))

    main(args.device)