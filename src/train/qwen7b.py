from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple
import logging

import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model
from transformers import (
    Qwen2_5_VLForConditionalGeneration,
    AutoProcessor,
)
from trl import SFTConfig, SFTTrainer
import wandb
from utils import resize_image_bbox_qwen25, get_bbox_from_element
import json
from PIL import Image
from accelerate import PartialState


# ---------------------------------------------------------------------------
# CONFIGURATION (edit freely)
# ---------------------------------------------------------------------------
DATASET_NAME = "GUIrilla/GUIrilla-Task"
MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"  # checkpoint name on HF Hub
OUTPUT_DIR = Path("qwen2_5_vl_7b_guirilla_lora")
WANDB_PROJECT = "qwen2_5_vl_7b_guirilla"
RUN_NAME = OUTPUT_DIR.name

# LoRA hyper‑parameters
LORA_CFG = dict(r=32, 
                lora_alpha=16, 
                lora_dropout=0.1, 
                bias="none",
                target_modules=['down_proj','o_proj','k_proj','q_proj','gate_proj','up_proj','v_proj'],
                init_lora_weights="gaussian",
                task_type="CAUSAL_LM"
                )


# Trainer hyper‑parameters
TRAIN_ARGS = dict(
    num_train_epochs=2,
    per_device_train_batch_size=2,
    per_device_eval_batch_size=2,
    gradient_accumulation_steps=4,
    learning_rate=2e-5,
    optim="adamw_torch_fused",
    lr_scheduler_type="cosine",
    logging_steps=10,
    eval_steps=500,
    eval_strategy="steps",
    save_strategy="steps",
    save_steps=500,
    metric_for_best_model="eval_loss",
    greater_is_better=False,
    load_best_model_at_end=True,
    bf16=True,
    max_grad_norm=0.3,
    warmup_ratio=0.05,
    push_to_hub=True,
    hub_model_id="GUIrilla/GUIrilla-See-7B",
    hub_private_repo=True,
    report_to="wandb",
    gradient_checkpointing=False,
    gradient_checkpointing_kwargs={"use_reentrant": False},
    label_names=["labels"],
    dataset_kwargs={"skip_prepare_dataset": True},
    remove_unused_columns=False,
    ddp_find_unused_parameters=False,
)

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------

def format_sample(sample: Dict[str, Any]) -> Dict[str, Any]:
    try:
        element = json.loads(sample["element_data"])
    except json.JSONDecodeError:
        element = eval(sample["element_data"])
    image = sample["image"]
    scaling_factor = sample["scaling_factor"]
    if scaling_factor == 2:
        image = image.resize((image.size[0] // 2, image.size[1] // 2), Image.LANCZOS)
        scaling_factor = 1
    bbox = get_bbox_from_element(element, scaling_factor)
    image, bbox = resize_image_bbox_qwen25(image, bbox)
    bbox_center = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
    return {"image_scaled": image, "bbox_center": bbox_center}


def load_data_splits() -> Tuple[List[Any], List[Any]]:
    LOGGER.info(f"Loading {DATASET_NAME} splits")
    dataset = load_dataset(DATASET_NAME, split="train")
    ## split into train and val by app_name
    app_names = set(dataset['app_name'])
    train_app_names = app_names[:int(len(app_names) * 0.95)]
    val_dataset = dataset.filter(lambda x: x['app_name'] not in train_app_names)
    train_dataset = dataset.filter(lambda x: x['app_name'] in train_app_names)

    val_dataset = val_dataset.map(format_sample,
                                  remove_columns=["image", "scaling_factor", "element_data", "screen_id", "action", "accessibility"],
                                  num_proc=32)
    train_dataset = train_dataset.map(format_sample,
                                      remove_columns=["image", "scaling_factor", "element_data", "screen_id", "action", "accessibility"],
                                      num_proc=32)
    return train_dataset, val_dataset


def build_model():
    """Load Qwen‑VL in 4‑bit NF4 and wrap with LoRA PEFT."""
    LOGGER.info("Loading base model %s …", MODEL_ID)
    device_string = PartialState().process_index
    
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(MODEL_ID, 
                                                            device_map={'':device_string},
                                                            use_cache=False,
                                                            torch_dtype=torch.bfloat16,
                                                            attn_implementation="flash_attention_2",
                                                            )
    processor = AutoProcessor.from_pretrained(MODEL_ID, use_fast=True)
    processor.tokenizer.padding_side = "right"
    peft_cfg = LoraConfig(**LORA_CFG)
    model = get_peft_model(model, peft_cfg)
    model.print_trainable_parameters()
    return model, processor


def apply_chat_template(example):
    return [{
                    "role": "user",
                    "content": [
                        {"type": "image", "image": example["image_scaled"]},
                        {
                            "type": "text",
                            "text": "Your task is to help the user identify the precise coordinates (x, y) of a specific area/element/object on the screen based on a description."
                                    "- Your response should aim to point to the center or a representative point within the described area/element/object as accurately as possible."
                                    "- If the description is unclear or ambiguous, infer the most relevant area or element based on its likely context or purpose."
                                    "- Your answer should be a single string (x, y) corresponding to the point of the interest."

                                    f"\nDescription: {example['task']}"

                                    "\nAnswer:"
                        },
                    ],
                },
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": f"({example['bbox_center'][0]}, {example['bbox_center'][1]})"}],
                }
    ]


def make_collator(processor):
    def collate_fn(examples):
        messages = [apply_chat_template(example) for example in examples]

        texts = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        image_inputs = [example[0]["content"][0]["image"] for example in messages]

        batch = processor(
            text=texts, images=image_inputs, return_tensors="pt", padding=True
        )

        labels = batch["input_ids"].clone()
        labels[labels == processor.tokenizer.pad_token_id] = -100

        image_tokens = [151652, 151653, 151655]
        for image_token_id in image_tokens:
            labels[labels==image_token_id] = -100
        batch["labels"] = labels

        return batch

    return collate_fn


def setup_wandb(cfg: SFTConfig) -> None:
    LOGGER.info("Initialising Weights & Biases run …")
    wandb.init(project=WANDB_PROJECT, name=RUN_NAME, config=cfg)


def build_trainer(model, processor, train_set, val_set) -> SFTTrainer:
    train_cfg = SFTConfig(output_dir=str(OUTPUT_DIR), **TRAIN_ARGS)
    collator = make_collator(processor)
    return SFTTrainer(
        model=model,
        args=train_cfg,
        train_dataset=train_set,
        eval_dataset=val_set,
        data_collator=collator,
        peft_config=LoraConfig(**LORA_CFG),
        processing_class=processor.tokenizer,
    )


def main():
    train_data, val_data = load_data_splits()
    model, processor = build_model()
    trainer = build_trainer(model, processor, train_data, val_data)
    setup_wandb(trainer.args)

    LOGGER.info("Starting training …")
    trainer.train()

    LOGGER.info("Saving artefacts to %s", OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(OUTPUT_DIR))
    processor.save_pretrained(str(OUTPUT_DIR))

    trainer.push_to_hub()


if __name__ == "__main__":  # pragma: no cover
    main()
