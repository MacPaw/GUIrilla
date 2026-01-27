import copy
import itertools

import torch
import json
import re
import argparse
import os
from PIL import Image
import logging
from tqdm import tqdm
from glob import glob


logging.basicConfig(level=logging.INFO)
torch.manual_seed(114514)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model_type', type=str, required=True)
    parser.add_argument('--model_name_or_path', type=str, required=False)
    parser.add_argument('--screenspot_imgs', type=str, required=True)
    parser.add_argument('--screenspot_test', type=str, required=True)
    parser.add_argument('--task', type=str, required=True)
    parser.add_argument('--log_file_path', type=str, required=True)
    args = parser.parse_args()
    return args

def build_model(args):
    model_type = args.model_type
    model_name_or_path = args.model_name_or_path
    if model_type == "florence_v2":
        from models.florence_v2 import FlorenceModel
        model = FlorenceModel(model_name_or_path)
    elif model_type == "qwen-2.5-vl":
        from models.qwen2_5_vl import QwenModel
        model = QwenModel(model_name_or_path)
    else:
        raise ValueError(f"Unsupported model type {model_type}.")
    model.set_generation_config(temperature=0, max_new_tokens=256)
    return model

def collect_results_to_eval(results, data_type=None, data_source=None):
    filtered_results = []
    for sample in results:
        if (data_type is None or sample.get("data_type") == data_type) and \
           (data_source is None or sample.get("data_source") == data_source):
            filtered_results.append(sample)
    return filtered_results


def make_combinations(results, data_type=False, data_source=False):
    unique_values = {
        "data_type": set(),
        "data_source": set()
    }
    for sample in results:
        if data_type:
            unique_values["data_type"].add(sample.get("data_type"))
        if data_source:
            unique_values["data_source"].add(sample.get("data_source"))

    filtered_values = {key: list(value) for key, value in unique_values.items() if value}
    if not filtered_values:
        return []

    attribute_combinations = list(itertools.product(*filtered_values.values()))
    combinations = [dict(zip(filtered_values.keys(), comb)) for comb in attribute_combinations]
    return combinations

def calc_metric_for_result_list(results):
    """Calculates the metrics for a simple result list."""
    num_total = len(results)
    correct_num = sum(1 for res in results if res["correctness"] == "correct")
    wrong_format_num = sum(1 for res in results if res["correctness"] == "wrong_format")

    metrics = {
        "num_correct_action": correct_num,
        "num_total": num_total,
        "wrong_format_num": wrong_format_num,
        "action_acc": correct_num / num_total if num_total > 0 else 0,
     }
    return metrics


def eval_sample_positive_gt(sample, response):
    bbox = sample["bbox"]
    # bbox = [bbox[0], bbox[1], bbox[2], bbox[3]]  # x1, y1, x2, y2
    bbox = [bbox[0], bbox[1], bbox[0] + bbox[2], bbox[1] + bbox[3]]  # x1, y1, w, h
    img_size = sample["img_size"]
    bbox = [bbox[0] / img_size[0], bbox[1] / img_size[1], bbox[2] / img_size[0], bbox[3] / img_size[1]]
    
    click_point = response["point"]  # may be none
    print(click_point)
    if click_point is None:
        return "wrong_format"
    # Check if the predicted point falls in the ground truth box
    if (bbox[0] <= click_point[0] <= bbox[2]) and (bbox[1] <= click_point[1] <= bbox[3]):
        return "correct"
    else:
        return "wrong"

def evaluate_grouped(results):
    combinations = make_combinations(results, data_type=True, data_source=True)
    evaluation_result = {}

    for combo in combinations:
        filtered = collect_results_to_eval(results, **combo)
        metrics = calc_metric_for_result_list(filtered)
        if metrics["num_total"] == 0:
            continue
        key = f"type:{combo.get('data_type')} source:{combo.get('data_source')}"
        evaluation_result[key] = metrics

    return evaluation_result


def evaluate_overall(results):
    """
    Evaluates the overall metrics for all results without any filtering.
    
    Parameters:
        results (list): A list of dictionaries containing sample results.
        
    Returns:
        dict: A dictionary containing the overall metrics.
    """
    # Calculate metrics for the entire result set
    metrics = calc_metric_for_result_list(results)
    
    return metrics


def evaluate(results):
    return {
        "details": results,
        "metrics": {
            "grouped": evaluate_grouped(results),
            "overall": evaluate_overall(results)
        }
    }


def main(args):
    model = build_model(args)
    model.load_model()
    print("Load model success")

    task_filenames = glob(f"{args.screenspot_test}/*.json") if args.task == "all" else args.task.split(",")
    tasks_to_run = []

    for dataset in task_filenames:
        with open(dataset, 'r') as f:
            task_data = json.load(f)
        for item in task_data:
            if "instruction" not in item or "bbox" not in item or "img_filename" not in item:
                continue
            item = copy.deepcopy(item)
            item["task_filename"] = dataset
            item["language"] = "en"
            item["prompt_to_evaluate"] = item["instruction"]
            tasks_to_run.append(item)

    print(f"Total tasks: {len(tasks_to_run)}")

    results = []
    for sample in tqdm(tasks_to_run):
        img_path = os.path.join(args.screenspot_imgs, sample["img_filename"])
        response = model.ground_only_positive(instruction=sample["prompt_to_evaluate"], image=img_path)

        with Image.open(img_path) as img:
            img_size = img.size
        sample["img_size"] = img_size

        point = response["point"]
        point_in_pixel = [point[0] * img_size[0], point[1] * img_size[1]] if point else None

        correctness = eval_sample_positive_gt(sample, response)
        result = {
            "img_path": img_path,
            "data_type": sample.get("data_type", "unknown"),
            "data_source": sample.get("data_source", "unknown"),
            "prompt_to_evaluate": sample["prompt_to_evaluate"],
            "language": sample["language"],
            "task_filename": sample["task_filename"],
            "bbox": sample["bbox"],
            "pred": point_in_pixel,
            "raw_response": response["raw_response"],
            "correctness": correctness
        }
        results.append(result)

    report = evaluate(results)
    with open(args.log_file_path, 'w') as f:
        json.dump(report, f, indent=4)
    logging.info("Evaluation complete.")



if __name__ == "__main__":
    main(parse_args())