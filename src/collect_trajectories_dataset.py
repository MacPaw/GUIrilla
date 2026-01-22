import os
import pickle
import json
from glob import glob
import shutil


class TaskDatasetCollector:
    def __init__(self, app_name, path, meta_tasks_file, output_dir):
        self.app_name = app_name
        self.path = path
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        with open(f"{self.path}/{meta_tasks_file}.pkl", "rb") as f:
            self.data = pickle.load(f)

        with open(f"{self.path}/graph/data.json", 'r') as f:
            self.graph_data = json.loads(f.read())

        self._prepare()

    def _get_image_action_sequence(self, graph_data, path):

        """Find image sequence for given task and path."""
        mini_tasks = path.split(" -> ")

        def _get_images(mini_tasks_to_parse, graph_subset):
            added_actions = []

            for edge_next in graph_subset["edges"]:
                if "task_string" not in edge_next["action"] or not edge_next["action"]["represent"]:
                    continue
                task_str = edge_next["action"]["task_string"]
                task_str_processed = edge_next["action"].get("processed_task_string")
                if task_str == mini_tasks_to_parse[0] or task_str_processed == mini_tasks_to_parse[0]:
                    image_name = edge_next["action"]["image_name"].replace("_cropped", "")
                    action_representation = edge_next["action"]["represent"]["string"]
                    added_actions.append({
                        "image_path": image_name,
                        "action": action_representation
                    })
                    if len(mini_tasks_to_parse) > 1:
                        actions = _get_images(mini_tasks_to_parse[1:], edge_next["out_vertice"])
                        added_actions.extend(actions)
                        return added_actions
                    else:
                        image_name = edge_next["out_vertice"]["image_name"].replace("_cropped", "")
                        added_actions.append({
                            "image_path": image_name,
                            "action": "done"
                        })
                        return added_actions


            if len(added_actions) == 0:
                for edge_next in graph_subset["edges"]:
                    added_actions.extend(_get_images(mini_tasks_to_parse, edge_next["out_vertice"]))

            return added_actions

        return _get_images(mini_tasks, graph_data)

    def _prepare(self):
        """Prepare visualizations for all meta tasks."""
        self.all_tasks = []
        grounded_tasks = {}

        # merging unique paths under the same task_name
        for task in self.data['meta_tasks']:
            if type(task) != dict:
                continue
            if task['task_name'] not in grounded_tasks:
                grounded_tasks[task['task_name']] = set(task['paths'])
            else:
                grounded_tasks[task['task_name']].update(task['paths'])

        unique_meta_tasks = {
            'n_meta_tasks': len(grounded_tasks),
            'meta_tasks': [{'task_name': task_name, 'paths': list(paths)} for task_name, paths in
                           grounded_tasks.items()]
        }

        self.data = unique_meta_tasks

        for meta_task in self.data["meta_tasks"]:
            meta_task_name = meta_task["task_name"]
            current_paths = meta_task["paths"]

            for path in current_paths:
                actions_sequence = self._get_image_action_sequence(
                    self.graph_data,
                    path
                )

                mini_tasks = path.split(" -> ")

                if len(actions_sequence) != len(mini_tasks) + 1:
                    continue

                trajectory = []
                for action_image, mini_task in zip(actions_sequence, mini_tasks + ["done"]):
                    trajectory.append({
                        'mini_task': mini_task,
                        'action': action_image["action"],
                        'image_path': action_image["image_path"],
                    })

                self.all_tasks.append({
                    "meta_task": meta_task_name,
                    "trajectory": trajectory
                })

    def _simplify_task_name(self, task):
        return task.lower().replace(" ", "_").replace('"', '').replace("'", '').replace("/", "_").strip()

    def _get_output_dir(self, task):
        output_dir = self.output_dir + self.app_name + "/" + self._simplify_task_name(task)
        count = 0
        if os.path.exists(output_dir):
            # start while (adding "(count)" to string)
            while True:
                new_dir_name = output_dir + f'({count})'
                if os.path.exists(new_dir_name):
                    count += 1
                else:
                    os.makedirs(new_dir_name)
                    output_dir = new_dir_name
                    break
        else:
            os.makedirs(output_dir)
        return output_dir

    def run(self):
        if not self.all_tasks:
            return False

        for task in self.all_tasks:
            task_name = task["meta_task"]
            output_path = self._get_output_dir(task_name)
            new_trajectory = []
            for id, action in enumerate(task["trajectory"]):
                image_name = os.path.split(action["image_path"])[-1]
                image_path = f"{self.path}/graph/images/{image_name}"
                new_image_name = f"{id}_{self._simplify_task_name(action['mini_task'])}.png"
                new_image_path = os.path.join(output_path, new_image_name)
                shutil.copyfile(image_path, new_image_path)
                new_trajectory.append({
                    "mini_task": action["mini_task"],
                    "action": action["action"],
                    "image_name": new_image_name
                })
        
            with open(os.path.join(output_path, "task_info.json"), "w") as f:
                json.dump({
                    "meta_task": task_name,
                    "trajectory": new_trajectory
                }, f, indent=4)
        return True



# Example usage
if __name__ == "__main__":
    files = glob("output/*/*/*/meta_tasks_double-task-graph-photo_info.pkl")

    for file in files:
        file_name = os.path.splitext(file.split("/")[-1])[0]
        app = file.split("/")[-2]
        path = os.path.split(file)[0]
        visualizer = TaskDatasetCollector(app, path, file_name, "output/dataset/")
        if visualizer.data["n_meta_tasks"] == 0:
            continue
        visualizer.run()
