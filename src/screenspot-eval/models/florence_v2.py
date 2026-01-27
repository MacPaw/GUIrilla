import os
import torch
import peft
from PIL import Image
from transformers import AutoProcessor, AutoModelForCausalLM

class FlorenceModel:
    def __init__(self, model_name, base_model="microsoft/Florence-2-large-ft", revision=False):
        self.base_model = base_model
        self.model_name = model_name  
        self.model = None
        self.processor = None
        self.revision = revision
        self.override_generation_config = {
            "temperature": 0.0,
            "max_new_tokens": 1024
        }

    def load_model(self):
        """Load the Florence model and processor with adapter."""
        DEVICE = torch.device("cuda:1" if torch.cuda.is_available() else "cpu")

        # Load base model
        self.model = AutoModelForCausalLM.from_pretrained(
            self.base_model,
            trust_remote_code=True
        ).to(DEVICE)

        # Load processor
        self.processor = AutoProcessor.from_pretrained(
            self.base_model,
            trust_remote_code=True
        )

        print("Base model successfully loaded")

        # Apply PEFT adapter
        self.model = peft.PeftModel.from_pretrained(self.model, self.model_name)

        print(f"Loaded Florence model: {self.base_model} with adapter: {self.model_name}")

    def set_generation_config(self, **kwargs):
        """Update generation configuration parameters."""
        self.override_generation_config.update(kwargs)

    def run_example(self, image, task_prompt, text_input=None):
        """Run the Florence model with provided inputs."""
        if text_input is None:
            prompt = task_prompt
        else:
            prompt = task_prompt + text_input

        DEVICE = torch.device("cuda:1" if torch.cuda.is_available() else "cpu")
        inputs = self.processor(text=prompt, images=image, return_tensors="pt").to(DEVICE)

        generated_ids = self.model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=self.override_generation_config.get("max_new_tokens", 1024),
            early_stopping=False,
            do_sample=False,
            num_beams=3
        )

        generated_text = self.processor.batch_decode(generated_ids, skip_special_tokens=False)[0]

        parsed_answer = self.processor.post_process_generation(
            generated_text,
            task=task_prompt,
            image_size=(image.width, image.height)
        )[task_prompt]

        return parsed_answer, generated_text

    def calculate_florence_polygon_center(self, polygon):
        """Calculate the center of a polygon if present."""
        if not polygon:
            return (0, 0)
        try:
            x_coords = [point[0] for point in polygon]
            y_coords = [point[1] for point in polygon]

            center_x = sum(x_coords) / len(x_coords)
            center_y = sum(y_coords) / len(y_coords)
            return (center_x, center_y)

        except:
            return (0, 0)

    def ground_only_positive(self, instruction, image):
        """Process instruction assuming target exists (always positive case)."""
        if isinstance(image, str):
            image_path = image
            assert os.path.exists(image_path) and os.path.isfile(image_path), "Invalid input image path."
            image = Image.open(image_path).convert('RGB')
        assert isinstance(image, Image.Image), "Invalid input image."

        task_prompt = '<OPEN_VOCABULARY_DETECTION>'
        prediction, raw_response = self.run_example(image, task_prompt, text_input=instruction)

        # Extract bounding box and click point
        if len(prediction["bboxes"]) == 0:
            if len(prediction["polygons"]) > 0 and len(prediction["polygons"][0]) != 0:
                click_point = self.calculate_florence_polygon_center(prediction["polygons"][0][0])
                bbox = None  # No direct bounding box available
            else:
                click_point = None
                bbox = None
        else:
            bbox = prediction['bboxes'][0]
            # Normalize bbox coordinates to [0,1] range
            width, height = image.size
            bbox = [
                bbox[0] / width,
                bbox[1] / height,
                bbox[2] / width,
                bbox[3] / height
            ]
            click_point = [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]

        result_dict = {
            "result": "positive",
            "bbox": bbox,
            "point": click_point,
            "raw_response": raw_response
        }

        return result_dict