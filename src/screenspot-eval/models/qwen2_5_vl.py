import os
import re
import math
import peft
import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

from transformers.models.qwen2_vl.image_processing_qwen2_vl_fast import smart_resize

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

    def load_model(self):
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self.base_model,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            attn_implementation="flash_attention_2",
            trust_remote_code=True
        ).eval()
        self.processor = AutoProcessor.from_pretrained(
            self.base_model,
            trust_remote_code=True,
            use_fast=True
        )
        print(f"Loaded Qwen model: {self.base_model}")

        self.model = peft.PeftModel.from_pretrained(self.model, self.model_name)
        self.model = self.model.merge_and_unload()
        print(f"Loaded Qwen model: {self.base_model} with adapter: {self.model_name}")

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

    def resize_qwen_style(self, image, bbox=None, resize_to_small=False, min_pixels=100 * 28 * 28, max_pixels=16384 * 28 * 28):
        """Apply Qwen-style resizing."""

        resized_height, resized_width = smart_resize(
            image.height,
            image.width,
            factor=self.processor.image_processor.patch_size * self.processor.image_processor.merge_size,
            min_pixels=self.processor.image_processor.min_pixels,
            max_pixels=99999999,
        )
        print(f"Resized image size: {resized_width}x{resized_height}")
        resized_image = image.resize((resized_width, resized_height))


        if resized_image.mode != "RGB":
            resized_image = resized_image.convert("RGB")

        return resized_image, (resized_height, resized_width), bbox

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
                num_beams=1,
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
        
        # Resize both image and bbox (if provided)
        resized_image, qwen_resize_factor, resized_bbox = self.resize_qwen_style(image, bbox=bbox)

        result_text = self._predict(instruction, resized_image)
        parsed_result = self._parse_output(result_text)

        if parsed_result['action'] == 'click':
            pred_x = parsed_result['coordinates']['x'] / qwen_resize_factor[1]
            pred_y = parsed_result['coordinates']['y'] / qwen_resize_factor[0]


            point = [pred_x, pred_y]
        else:
            point = None

        return {
            "result": "positive",
            "bbox": resized_bbox,  # This is the bbox used in inference/evaluation
            "point": point,
            "raw_response": result_text
        }