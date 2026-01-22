import logging
from pythonjsonlogger import jsonlogger
from datetime import datetime


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    A custom JSON formatter to define custom log fields.
    """

    def add_fields(self, log_record, record, message_dict):
        log_record['log_level'] = record.levelname  # Human-readable log level
        log_record['timestamp'] = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")  # Add timestamp field in seconds
        # Call the base method to populate default fields
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)


def setup_json_logger(file_path):
    """
    Configures a logger to output JSON logs to a file.
    """
    # Create a logger
    logger = logging.getLogger("json_logger")
    logger.setLevel(logging.DEBUG)  # Set minimum log level

    # Create a file handler
    file_handler = logging.FileHandler(file_path, mode="w")
    file_handler.setLevel(logging.DEBUG)

    # Define the custom JSON formatter
    custom_formatter = CustomJsonFormatter()
    file_handler.setFormatter(custom_formatter)

    # Add the handler to the logger
    logger.addHandler(file_handler)

    return logger


# Example Usage
if __name__ == "__main__":
    # Setup logger
    logger = setup_json_logger("app_logs.json")

    # Log some messages with custom fields
    message = {
        "meta_task": "gafas",
        "step": 0,
        "screenshot_file_path": "dasd",
        "evaluator": {
            "screenshot_description": "",
            "status": "asd",
            "thought": "sa",
            "rate": 1,
            "answer": "a"
        },
        "planner": {
            "operation": "",
            "thought": "",
            "action": "",
            "command": "",
            "ground_truth": "",
            "description": ""
        },
        "screenshot_after_action_file_path": "",
        "reflector": {
            "analysis": ""
        }
    }
    logger.info("STEP 1", extra=message)
    logger.info("STEP 2", extra=message)