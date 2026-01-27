import base64
from io import BytesIO
import cv2
import numpy as np
import os
from PIL import Image
import math


def get_log_dir(postfix):
    logs_dir = "src/eval/logs_" + postfix
    new_logs_dir = logs_dir
    i = 0
    while os.path.exists(new_logs_dir):
        new_logs_dir = logs_dir + str(i)
        i += 1
    logs_dir = new_logs_dir
    os.makedirs(logs_dir, exist_ok=True)
    return logs_dir


def get_bbox_from_element(element, scaling_factor=1):
    x, y = element["absolute_position"].split(";")
    x, y = int(float(x)), int(float(y))
    width, height = element["size"].split(";")
    width, height = int(float(width)), int(float(height))

    # height_offset = 2
    # if height < 2:
    #     height_offset = 0

    # bbox = [x * scaling_factor, 
    #         y * scaling_factor, 
    #         (x + width) * scaling_factor - 1, 
    #         (y + height) * scaling_factor - height_offset + 1]

    bbox = [int(x * scaling_factor), 
            int(y * scaling_factor), 
            int((x + width) * scaling_factor), 
            int((y + height) * scaling_factor)]
    return bbox


def check_in(bbox, x, y):
    x1, y1, x2, y2 = bbox
    return x1 <= x <= x2 and y1 <= y <= y2


def log_image(image, task, bbox, predicted_click, output_path):
    image = np.array(image)
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    # Write the task text on the image with a black background
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.5
    font_thickness = 1
    text_color = (255, 255, 255)  # White
    background_color = (0, 0, 0)  # Black

    # Get text size
    text_size = cv2.getTextSize(f"Task: {task}", font, font_scale, font_thickness)[0]
    text_x, text_y = 10, 20
    text_width, text_height = text_size

    # Draw black rectangle as background for text
    cv2.rectangle(image, (text_x - 2, text_y - text_height - 2), (text_x + text_width + 2, text_y + 2), background_color, -1)

    # Put white text on top of the black background
    cv2.putText(image, f"Task: {task}", (text_x, text_y), font, font_scale, text_color, font_thickness)

    # Draw the bounding box
    x1, y1, x2, y2 = bbox
    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 255), 2)  # Red rectangle

    # Draw the predicted action point
    predicted_x, predicted_y = predicted_click[0], predicted_click[1]
    cv2.circle(image, (predicted_x, predicted_y), 5, (255, 0, 0), -1)  # Blue dot

    cv2.imwrite(output_path, image)


def encode_screenshot(screenshot):
    # Convert screenshot to base64
    buffered = BytesIO()
    screenshot.save(buffered, format="PNG")
    screenshot_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return screenshot_base64


def resize_image_and_bbox_width(image, bbox, max_width=1280):
    width = image.width
    height = image.height
    if width > max_width:
        scale_factor = max_width / width
        target_width = max_width
        target_height = int(height * scale_factor)
        image = image.resize((target_width, target_height), Image.LANCZOS)
        new_bbox = [int(i * scale_factor) for i in bbox]
        return image, new_bbox
    return image, bbox


def resize_image_and_bbox_pixels(image, bbox, max_pixels):
    width = image.width
    height = image.height
    current_pixels = width * height
    if current_pixels > max_pixels:
        scale_factor = math.sqrt(max_pixels / current_pixels)
        target_width = math.floor(width * scale_factor)
        target_height = math.floor(height * scale_factor)
        image = image.resize((target_width, target_height), Image.LANCZOS)
        new_bbox = [math.floor(i * scale_factor) for i in bbox]
        return image, new_bbox
    return image, bbox


def convert_image(image):
    # Check if image is RGBA and convert it to RGB
    if image.mode == "RGBA":
        rgb_img = Image.new("RGB", image.size, (255, 255, 255))
        rgb_img.paste(image, mask=image.split()[3])

        return rgb_img
    return image


def resize_image_bbox_qwen2(image, bbox, min_pixels=100 * 28 * 28, max_pixels=16384 * 28 * 28):
    new_bbox = bbox.copy()
    if image.width * image.height > max_pixels:
        resize_factor = math.sqrt(max_pixels / (image.width * image.height))
        width, height = int(image.width * resize_factor), int(image.height * resize_factor)
        image = image.resize((width, height))
        new_bbox = [int(i * resize_factor) for i in bbox]
    if image.width * image.height < min_pixels:
        resize_factor = math.sqrt(min_pixels / (image.width * image.height))
        width, height = math.ceil(image.width * resize_factor), math.ceil(image.height * resize_factor)
        image = image.resize((width, height))
        new_bbox = [math.ceil(i * resize_factor) for i in bbox]

    if image.mode != "RGB":
        image = image.convert("RGB")
    
    return image, new_bbox


def resize_image_bbox(image, bbox, target_width, target_height):
    # Get the original size of the image
    original_width, original_height = image.size

    # Resize the image
    image = image.resize((target_width, target_height), Image.LANCZOS)

    # Calculate the scaling factors
    height_scale = target_height / original_height
    width_scale = target_width / original_width

    # Resize the bounding box
    new_bbox = [
        int(bbox[0] * width_scale),
        int(bbox[1] * height_scale),
        int(bbox[2] * width_scale),
        int(bbox[3] * height_scale)
    ]

    return image, new_bbox


def get_qwen25_size(
    height, width, factor=28, min_pixels=100 * 28 * 28, max_pixels=16384 * 28 * 28, max_ratio=200,
) -> tuple[int, int]:
    if max(height, width) / min(height, width) > max_ratio:
        raise ValueError(
            f"absolute aspect ratio must be smaller than {max_ratio}, got {max(height, width) / min(height, width)}"
        )

    def round_by_factor(number: int, factor: int) -> int:
        """Returns the closest integer to 'number' that is divisible by 'factor'."""
        return round(number / factor) * factor

    def floor_by_factor(number: int, factor: int) -> int:
        """Returns the largest integer less than or equal to 'number' that is divisible by 'factor'."""
        return math.floor(number / factor) * factor

    def ceil_by_factor(number: int, factor: int) -> int:
        """Returns the smallest integer greater than or equal to 'number' that is divisible by 'factor'."""
        return math.ceil(number / factor) * factor

    h_bar = max(factor, round_by_factor(height, factor))
    w_bar = max(factor, round_by_factor(width, factor))
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = floor_by_factor(height / beta, factor)
        w_bar = floor_by_factor(width / beta, factor)
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = ceil_by_factor(height * beta, factor)
        w_bar = ceil_by_factor(width * beta, factor)
    return h_bar, w_bar


def resize_image_bbox_qwen25(image, bbox, min_pixels=100 * 28 * 28, max_pixels=16384 * 28 * 28):
    # Get the original size of the image
    original_width, original_height = image.size

    # Get the new size for the image
    new_height, new_width = get_qwen25_size(original_height, original_width)

    # Resize the image
    image = image.resize((new_width, new_height), Image.LANCZOS)

    # Calculate the scaling factors
    height_scale = new_height / original_height
    width_scale = new_width / original_width

    # Resize the bounding box
    new_bbox = [
        int(bbox[0] * width_scale),
        int(bbox[1] * height_scale),
        int(bbox[2] * width_scale),
        int(bbox[3] * height_scale)
    ]

    return image, new_bbox
    

def image_to_base64(image):
    # Convert the image to a base64 string
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return img_str