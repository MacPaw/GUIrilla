import json
import os
import random
from typing import Any, Dict, List, Tuple

import numpy as np
import supervision as sv
import torch
import wandb
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm
from transformers import AutoModelForCausalLM, AutoProcessor
from peft import LoraConfig, get_peft_model
import wandb
import json
import os
import torch
import numpy as np
from tqdm import tqdm
from PIL import Image
import supervision as sv
from torch.optim import AdamW
import transformers
import random
import datasets


BATCH_SIZE = 8
NUM_WORKERS = 0

DEVICE = "cuda"

def collate_fn(batch):
    questions, answers, images = zip(*batch)
    inputs = processor(text=list(questions), images=list(images), return_tensors="pt", padding=True).to(DEVICE)
    return inputs, answers


def normalize_bbox(bbox, img_width, img_height):
    x1 = round((bbox[0] / img_width) * 1000)
    y1 = round((bbox[1] / img_height) * 1000)
    x2 = round((bbox[2] / img_width) * 1000)
    y2 = round((bbox[3] / img_height) * 1000)

    return [
        max(0, min(999, x1)),
        max(0, min(999, y1)),
        max(0, min(999, x2)),
        max(0, min(999, y2))
    ]


def map_function(x):
    image = x["image"]
    image_width, image_height = image.size
    element_data = json.loads(x["element_data"])
    sf = x["scaling_factor"]
    absolute_position = element_data['absolute_position']
    size = element_data['size']
    # Parse absolute_position (format: 'x;y')
    x1, y1 = map(float, absolute_position.split(';'))
    # Parse size (format: 'width;height')
    width, height = map(float, size.split(';'))
    bbox = [x1 * sf, y1 * sf, x1 * sf + width * sf, y1 * sf + height * sf]
    norm_bbox = normalize_bbox(bbox, image_width, image_height)
    task = x["task"]

    return {
        "prefix": f"<OPEN_VOCABULARY_DETECTION>{task}",
        "suffix": f"{task}<loc_{norm_bbox[0]}><loc_{norm_bbox[1]}><loc_{norm_bbox[2]}><loc_{norm_bbox[3]}>",
    }


train_dataset = datasets.load_dataset("GUIrilla/GUIrilla-Task", split="train")
## split into train and val by app_name
app_names = set(train_dataset['app_name'])
train_app_names = app_names[:int(len(app_names) * 0.9)]
val_dataset = train_dataset.filter(lambda x: x['app_name'] not in train_app_names)
train_dataset = train_dataset.filter(lambda x: x['app_name'] in train_app_names)

train_dataset = train_dataset.map(map_function)[["prefix", "suffix", "image"]]
val_dataset = val_dataset.map(map_function)[["prefix", "suffix", "image"]]

train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, collate_fn=collate_fn, num_workers=NUM_WORKERS, shuffle=True)
val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, collate_fn=collate_fn, num_workers=NUM_WORKERS, shuffle=True)

CHECKPOINT = "microsoft/Florence-2-large-ft"
DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

model = AutoModelForCausalLM.from_pretrained(CHECKPOINT, trust_remote_code=True).to(DEVICE)
processor = AutoProcessor.from_pretrained(CHECKPOINT, trust_remote_code=True)

config = LoraConfig(
    r=8,
    lora_alpha=16,
    target_modules=["q_proj", "o_proj", "k_proj", "v_proj", "linear", "Conv2d", "lm_head", "fc2"],
    task_type="CAUSAL_LM",
    lora_dropout=0.05,
    bias="none",
    inference_mode=False,
    use_rslora=True,
    init_lora_weights="gaussian"
)

peft_model = get_peft_model(model, config)
peft_model.print_trainable_parameters()


def calculate_florence_polygon_center(polygon):
    if not isinstance(polygon, list) or len(polygon) < 4 or len(polygon) % 2 != 0:
        raise ValueError("Invalid polygon: Expected flat list with even number of coordinates")

    x_coords = polygon[0::2]  # All even indices (0, 2, 4, ...)
    y_coords = polygon[1::2]  # All odd indices (1, 3, 5, ...)

    center_x = sum(x_coords) / len(x_coords)
    center_y = sum(y_coords) / len(y_coords)

    return (center_x, center_y)

def task_predicted_correctly(task, answer, image):
    task_prompt = '<OPEN_VOCABULARY_DETECTION>'
    predicted_inputs = processor(text=task, images=image, return_tensors="pt").to('cuda')
    generated_ids = model.generate(
        input_ids=predicted_inputs["input_ids"].to(DEVICE),
        pixel_values=predicted_inputs["pixel_values"].to(DEVICE),
        max_new_tokens=1024,
        early_stopping=False,
        do_sample=False,
        num_beams=3,
    )
    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
    prediction = processor.post_process_generation(
        generated_text,
        task=task_prompt,
        image_size=(image.width, image.height)
    )['<OPEN_VOCABULARY_DETECTION>']

    if len(prediction["bboxes"]) == 0:
        if len(prediction["polygons"]) > 0 and len(prediction["polygons"][0]) != 0:
            bbox_center = calculate_florence_polygon_center(prediction["polygons"][0][0])
        else:
            bbox_center = (0, 0)
    else:
        bbox_florence = prediction['bboxes'][0]
        bbox_center = (bbox_florence[0] + bbox_florence[2]) / 2, (bbox_florence[1] + bbox_florence[3]) / 2

    gt = processor.post_process_generation(
        answer,
        task=task_prompt,
        image_size=(image.width, image.height)
    )['<OPEN_VOCABULARY_DETECTION>']

    x1, y1, x2, y2 = gt['bboxes'][0]
    x, y = bbox_center
    if x1 <= x <= x2 and y1 <= y <= y2:
        return True
    return False

def eval_accuracy(dataset, n_samples=1000):
    correct = 0
    total = 0
    for task, answer, image in tqdm(dataset):
        try:
            prediction = task_predicted_correctly(task, answer, image)
            correct += prediction
            total += 1
        except:
            total += 1

        if total >= n_samples:
            return correct / total if total > 0 else 0
    return correct / total if total > 0 else 0


def log_inference_results(model, dataset, count, epoch):
    """Log inference results to wandb"""
    wandb_images = []
    count = min(count, len(dataset))
    random_ids = random.choices(range(len(dataset.dataset)), k=count)

    for i in random_ids:
        image, data = dataset.dataset[i]
        prefix = data['prefix']
        suffix = data['suffix']

        # Get model prediction
        inputs = processor(text=prefix, images=image, return_tensors="pt").to(DEVICE)
        generated_ids = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=1024,
            num_beams=3
        )
        generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        answer = processor.post_process_generation(generated_text, task='<OPEN_VOCABULARY_DETECTION>', image_size=image.size)

        # Create annotated image
        try:
            detections = sv.Detections.from_lmm(sv.LMM.FLORENCE_2, answer, resolution_wh=image.size)

            # Annotate with bounding boxes
            annotated_image = image.copy()  # Start with a copy of the original image
            annotated_image = sv.BoxAnnotator(color_lookup=sv.ColorLookup.INDEX).annotate(annotated_image, detections)

            # Annotate with labels
            annotated_image = sv.LabelAnnotator(color_lookup=sv.ColorLookup.INDEX).annotate(annotated_image, detections)
        except Exception as e:
            print(f'Failed to render model response for image {i}: {str(e)}')
            annotated_image = image.copy()

        # Create caption with model response
        caption = f"Sample {i}: {json.dumps(answer)}"
        # Add to wandb images
        wandb_images.append(wandb.Image(annotated_image, caption=caption))

    # Log batch of images to wandb
    wandb.log({f"inference_results_epoch_{epoch}": wandb_images})



def train_model(train_loader, val_loader, model, processor, epochs=10, lr=1e-6):
    optimizer = AdamW(model.parameters(), lr=lr)
    num_training_steps = epochs * len(train_loader)
    lr_scheduler = transformers.get_scheduler(
        name="cosine",
        optimizer=optimizer,
        num_warmup_steps=int(0.05 * num_training_steps),
        num_training_steps=num_training_steps,
    )

    steps_per_epoch = len(train_loader)
    eval_every_n_steps = steps_per_epoch // 4

    # Initial inference visualization
    log_inference_results(model, val_loader.dataset, 6, epoch=0)

    for epoch in range(epochs):
        i = 0
        model.train()
        train_loss = 0
        for inputs, answers in tqdm(train_loader, desc=f"Training Epoch {epoch + 1}/{epochs}"):
            i += 1
            input_ids = inputs["input_ids"]
            pixel_values = inputs["pixel_values"]
            labels = processor.tokenizer(
                text=answers,
                return_tensors="pt",
                padding=True,
                return_token_type_ids=False
            ).input_ids.to(DEVICE)

            outputs = model(input_ids=input_ids, pixel_values=pixel_values, labels=labels)
            loss = outputs.loss

            loss.backward()
            optimizer.step()
            lr_scheduler.step()
            optimizer.zero_grad()
            train_loss += loss.item()

            if (i) % eval_every_n_steps == 0:
                # Evaluate
                current_step = i
                fraction_epoch = current_step / steps_per_epoch
                avg_train_loss = train_loss / current_step
                print(f"\nEpoch {epoch}, Step {current_step} (Epoch {epoch + fraction_epoch:.2f})")
                print(f"Average Training Loss: {avg_train_loss}")
                wandb.log({
                    "avg_train_loss": avg_train_loss,
                    "epoch": epoch + fraction_epoch,
                    "lr": lr_scheduler.get_last_lr()[0]
                })

                model.eval()
                val_loss = 0

                with torch.no_grad():
                    for inputs, answers in tqdm(val_loader, desc=f"Validation Epoch {epoch + 1}/{epochs}"):
                        input_ids = inputs["input_ids"]
                        pixel_values = inputs["pixel_values"]
                        labels = processor.tokenizer(
                            text=answers,
                            return_tensors="pt",
                            padding=True,
                            return_token_type_ids=False
                        ).input_ids.to(DEVICE)

                        outputs = model(input_ids=input_ids, pixel_values=pixel_values, labels=labels)
                        loss = outputs.loss

                        val_loss += loss.item()

                    avg_val_loss = val_loss / len(val_loader)
                    print(f"Average Validation Loss: {avg_val_loss}")
                    wandb.log({
                        "avg_val_loss": avg_val_loss,
                        "epoch": epoch,
                        "lr": lr_scheduler.get_last_lr()[0]
                    })

                log_inference_results(model, val_loader.dataset, 6, epoch=epoch+1)
                model.train()

        avg_train_loss = train_loss / len(train_loader)
        print(f"Average Training Loss: {avg_train_loss}")
        wandb.log({
            "avg_train_loss": avg_train_loss,
            "epoch": epoch,
            "lr": lr_scheduler.get_last_lr()[0]
        })

        model.eval()
        val_loss = 0

        with torch.no_grad():
            for inputs, answers in tqdm(val_loader, desc=f"Validation Epoch {epoch + 1}/{epochs}"):
                input_ids = inputs["input_ids"]
                pixel_values = inputs["pixel_values"]
                labels = processor.tokenizer(
                    text=answers,
                    return_tensors="pt",
                    padding=True,
                    return_token_type_ids=False
                ).input_ids.to(DEVICE)

                outputs = model(input_ids=input_ids, pixel_values=pixel_values, labels=labels)
                loss = outputs.loss

                val_loss += loss.item()

            avg_val_loss = val_loss / len(val_loader)
            print(f"Average Validation Loss: {avg_val_loss}")
            wandb.log({
                "avg_val_loss": avg_val_loss,
                "epoch": epoch,
                "lr": lr_scheduler.get_last_lr()[0]
            })

        # Log inference visualizations to wandb
        log_inference_results(model, val_loader.dataset, 6, epoch=epoch+1)

        # Run predictions to calculate accuracy
        val_accuracy = eval_accuracy(val_loader.dataset)
        wandb.log({"val_accuracy": val_accuracy})
        print(f"Average Accuracy: {val_accuracy}")

        output_dir = f"./model_checkpoints/epoch_{epoch+1}"
        os.makedirs(output_dir, exist_ok=True)
        model.save_pretrained(output_dir)
        processor.save_pretrained(output_dir)

EPOCHS = 4
LR = 5e-6

wandb.init(
    # set the wandb project where this run will be logged
    project="monkey-see",
    name="",

    # track hyperparameters and run metadata
    config={
    "learning_rate": LR,
    "augmentation": "basic",
    "optimizer": "AdamW",
    "epochs": EPOCHS,
    "batch_size": 8,
    }
)

train_model(train_loader, val_loader, peft_model, processor, epochs=EPOCHS, lr=LR)


