import os
import re
import math
import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

class QwenModel:
    def __init__(self, model_name, base_model="Qwen/Qwen2.5-VL-7B-Instruct"):
        self.model_name = model_name
        self.base_model = base_model
        self.model = None
        self.processor = None
        self.override_generation_config = {
            "temperature": 0.0,
            "max_new_tokens": 1024
        }
        self.fixed_target_size = (1775, 962)

    def load_model(self):
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self.model_name,
            torch_dtype="auto",
            device_map="cuda:1",
            trust_remote_code=True
        )
        self.processor = AutoProcessor.from_pretrained(
            self.model_name,
            trust_remote_code=True,
            use_fast=True
        )
        print(f"Loaded Qwen model: {self.model_name}")

    def set_generation_config(self, **kwargs):
        self.override_generation_config.update(kwargs)

    def _resize_bbox(self, bbox, from_size, to_size):
        """Resize bbox [x1, y1, x2, y2] from from_size to to_size."""
        scale_x = to_size[0] / from_size[0]
        scale_y = to_size[1] / from_size[1]
        return [
            int(bbox[0] * scale_x),
            int(bbox[1] * scale_y),
            int(bbox[2] * scale_x),
            int(bbox[3] * scale_y)
        ]

    def resize_to_fixed_then_qwen_style(self, image, bbox=None, resize_to_small=False, min_pixels=100 * 28 * 28, max_pixels=16384 * 28 * 28):
        """Resize image to 1775×962, then apply Qwen-style resizing. Resize bbox too if given."""
        orig_size = image.size
        resized_bbox = bbox

        # Step 1: Resize to fixed target size
        image = image.resize(self.fixed_target_size, resample=Image.BILINEAR)
        if bbox:
            resized_bbox = self._resize_bbox(resized_bbox, orig_size, self.fixed_target_size)

        # Step 2: Qwen-style resizing based on total pixel count
        resize_factor = 1.0
        curr_pixels = image.width * image.height

        if curr_pixels > max_pixels:
            resize_factor = math.sqrt(max_pixels / curr_pixels)
        elif curr_pixels < min_pixels:
            resize_factor = math.sqrt(min_pixels / curr_pixels)

        if resize_factor != 1.0:
            new_size = (int(image.width * resize_factor), int(image.height * resize_factor))
            image = image.resize(new_size, resample=Image.BILINEAR)
            if resized_bbox:
                resized_bbox = [int(coord * resize_factor) for coord in resized_bbox]

        if image.mode != "RGB":
            image = image.convert("RGB")

        return image, resize_factor, resized_bbox

    def _predict(self, task, image):
        conversation = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {
                        "type": "text",
                        "text": "Your task is to help the user identify the precise coordinates (x, y) of a specific area/element/object on the screen based on a description."
                                "- Your response should aim to point to the center or a representative point within the described area/element/object as accurately as possible."
                                "- If the description is unclear or ambiguous, infer the most relevant area or element based on its likely context or purpose."
                                "- Your answer should be a single string (x, y) corresponding to the point of the interest."
                                f"\nDescription: {task}"
                                "\nAnswer:"
                    },
                ],
            }
        ]

        texts = self.processor.apply_chat_template(conversation, tokenize=False, add_generation_prompt=True)
        image_inputs = [example["content"][0]["image"] for example in conversation]

        inputs = self.processor(
            text=texts, images=image_inputs, return_tensors="pt", padding=True
        ).to(self.model.device)

        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=self.override_generation_config.get("max_new_tokens", 1024),
                num_beams=3,
                do_sample=False,
                temperature=None,
                top_k=None,
                top_p=None,
            )

        generated_ids = [output_ids[i][len(inputs.input_ids[i]):] for i in range(len(output_ids))]
        output_text = self.processor.batch_decode(generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=True)[0]

        return output_text

    def _parse_output(self, output):
        click_match = re.search(r"\((\d+),\s?(\d+)\)", output)
        if click_match:
            x, y = map(int, click_match.groups())
            return {
                "action": "click",
                "coordinates": {
                    "x": x,
                    "y": y,
                }
            }
        return {"action": "unknown", "raw_output": output}

    def ground_only_positive(self, instruction, image, bbox=None):
        if isinstance(image, str):
            image_path = image
            assert os.path.exists(image_path) and os.path.isfile(image_path), "Invalid input image path."
            image = Image.open(image_path)
        assert isinstance(image, Image.Image), "Invalid input image."

        original_width, original_height = image.size

        # Resize both image and bbox (if provided)
        resized_image, qwen_resize_factor, resized_bbox = self.resize_to_fixed_then_qwen_style(image, bbox=bbox)

        result_text = self._predict(instruction, resized_image)
        parsed_result = self._parse_output(result_text)

        if parsed_result['action'] == 'click':
            pred_x = parsed_result['coordinates']['x']
            pred_y = parsed_result['coordinates']['y']

            # Undo Qwen resize
            fixed_x = pred_x / qwen_resize_factor
            fixed_y = pred_y / qwen_resize_factor

            # Undo 1775×962 resize
            scale_x = original_width / self.fixed_target_size[0]
            scale_y = original_height / self.fixed_target_size[1]
            orig_x = int(fixed_x * scale_x)
            orig_y = int(fixed_y * scale_y)

            norm_x = orig_x / original_width
            norm_y = orig_y / original_height

            point = [norm_x, norm_y]
        else:
            point = None

        return {
            "result": "positive",
            "bbox": resized_bbox,  # This is the bbox used in inference/evaluation
            "point": point,
            "raw_response": result_text
        }