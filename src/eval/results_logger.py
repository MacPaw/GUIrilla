import csv

class ResultsLogger:
    def __init__(self, file_path):
        self.file_path = file_path
        # Create the CSV file and write the header if it doesn't exist
        with open(self.file_path, mode='a', newline='') as file:
            writer = csv.writer(file)
            if file.tell() == 0:  # Check if file is empty
                writer.writerow(['id', 'task', 'original_task', 'task_category', 'element_category', 'success'])

    def log(self, id, task, original_task, task_category, element_category, success):
        with open(self.file_path, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([id, task, original_task, task_category, element_category, success])