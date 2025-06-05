import datasets
import json
import torch
from tqdm import tqdm
from src.eval.logger import setup_json_logger
import os
from PIL import Image
from src.eval.utils import get_bbox_from_element, check_in, log_image, get_log_dir, encode_screenshot
from transformers import AutoProcessor, AutoModelForCausalLM
import argparse
from src.eval.results_logger import ResultsLogger


class AgentPipeline:
    def __init__(self, model_size, device="cuda"):
        model_name = "microsoft/Florence-2-" + model_size
        self.device = torch.device(device)
        self.torch_dtype = torch.bfloat16 if self.device.type == "cuda" else torch.float32
        self.model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype=self.torch_dtype, trust_remote_code=True).to(self.device)
        self.processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)

    def run_example(self, image, task_prompt, text_input=None):
        image = image.convert("RGB")
        if text_input is None:
            prompt = task_prompt
        else:
            prompt = task_prompt + text_input
        inputs = self.processor(text=prompt, images=[image], return_tensors="pt").to(self.device).to(self.torch_dtype)
        generated_ids = self.model.generate(
            input_ids=inputs["input_ids"].to(self.device),
            pixel_values=inputs["pixel_values"].to(self.device),
            max_new_tokens=1024,
            early_stopping=False,
            do_sample=False,
            num_beams=3,
        )
        generated_text = self.processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        parsed_answer = self.processor.post_process_generation(
            generated_text,
            task=task_prompt,
            image_size=(image.width, image.height)
        )

        return parsed_answer

    
    def call_florence(self, image, task):
        task_prompt = '<OPEN_VOCABULARY_DETECTION>'
        results = self.run_example(image, task_prompt, text_input=task)['<OPEN_VOCABULARY_DETECTION>']
        if len(results["bboxes"]) == 0:
            if len(results["polygons"][0]) != 0:
                polygon_center = calculate_florence_polygon_center(results["polygons"][0][0])
                return {"polygon": results["polygons"][0][0], "bbox_center": polygon_center}
            else:
                return False
        bbox_florence = results['bboxes'][0]
        bbox_center = (bbox_florence[0] + bbox_florence[2]) / 2, (bbox_florence[1] + bbox_florence[3]) / 2
        return {"bbox": bbox_florence, "bbox_center": bbox_center}


def calculate_florence_polygon_center(polygon):
    """
    Calculate the center point (centroid) of a Florence polygon, representation from [https://www.datature.io/blog/introducing-florence-2-microsofts-latest-multi-modal-compact-visual-language-model].

    Parameters:
    polygon (list): Flat list of coordinates in format [x0, y0, x1, y1, ..., xn, yn]
                    as used in Florence polygon representation

    Returns:
    tuple: The (x, y) coordinates of the polygon's center
    """
    if not isinstance(polygon, list) or len(polygon) < 4 or len(polygon) % 2 != 0:
        raise ValueError("Invalid polygon: Expected flat list with even number of coordinates")

    x_coords = polygon[0::2]  # All even indices (0, 2, 4, ...)
    y_coords = polygon[1::2]  # All odd indices (1, 3, 5, ...)

    center_x = sum(x_coords) / len(x_coords)
    center_y = sum(y_coords) / len(y_coords)

    return (center_x, center_y)


def main(device, model_size):
    agent = AgentPipeline(device=device, model_size=model_size)

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
        florence_prediction = agent.call_florence(image, task)

        if not florence_prediction:
            logger.warning("Florence prediction failed", extra={"id": task_id})
            success = False
        else:
            x, y = florence_prediction["bbox_center"]

            if check_in(bbox, x, y):
                logger.info("Florence prediction successful", extra={"id": task_id, "x": x, "y": y, "action": action})
                success = True
            else:
                logger.warning("Florence prediction out of bounds", extra={"id": task_id})
                log_image(image, task, bbox, (int(x), int(y)), os.path.join(logs_dir, f"{task_id}.png"))
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
    parser.add_argument("--model_size", type=str, default="base", choices=["base", "large"], help="Model size to use.")

    args = parser.parse_args()

    logs_dir = get_log_dir("florence_" + args.model_size)
    logger = setup_json_logger(os.path.join(logs_dir, "logs.json"))

    results_logger = ResultsLogger(os.path.join(logs_dir, "results.csv"))

    main(args.device, args.model_size)