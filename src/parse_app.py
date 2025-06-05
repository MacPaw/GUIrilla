import ApplicationServices
import AppKit
import argparse
import os
import time
import graph_plotting
import datetime
import logging
import json

import helpers.window_tools as window_tools
import helpers.files as files
import helpers.applications as applications
import helpers.element_graph as Graph
import generate_dashboard

from helpers.uielement import UIElement, element_attribute
from action_performer import ActionManager, ActionPerformer

# Configure logging at the start of the script
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class AccessibilityError(Exception):
    pass


def extract_extra_menu_bar(application, app_bundle, output_folder):
    menu_attribute = element_attribute(
        application, ApplicationServices.kAXExtrasMenuBarAttribute
    )
    if menu_attribute is None:
        return

    menu = UIElement(menu_attribute)
    menu_output_file = os.path.join(output_folder, f"{app_bundle}_status_item.json")
    files.store_data_to_file(menu, menu_output_file)


def click_extra_menu_bar_and_extract(
    action_performer, application, action_manager, app_bundle, output_folder
):
    menuBar = element_attribute(
        application, ApplicationServices.kAXExtrasMenuBarAttribute
    )
    if menuBar is None:
        return

    children = element_attribute(menuBar, ApplicationServices.kAXChildrenAttribute)
    for child in children:
        child_element = UIElement(child)
        if child_element.role == "AXMenuBarItem":
            error = ApplicationServices.AXUIElementPerformAction(
                child, ApplicationServices.kAXPressAction
            )

            if error != ApplicationServices.kAXErrorSuccess:
                logger.error("Error clicking on the menu bar item")
                raise AccessibilityError("Failed to perform action on menu bar item")

            windows = applications.windows_for_application(application)
            window_children = UIElement(windows[0]).children

            if len(window_children) > 0:
                window = UIElement(windows[0])
                extracted = window_tools.extract_window(
                    window, app_bundle, output_folder, perform_hit_test, print_nodes
                )

                if extracted:
                    if action_performer.action_manager.head_node is None:
                        action_performer.action_manager.head_node = action_manager.create_vertice(
                            window
                        )
                        action_performer.perform_actions(
                            action_performer.action_manager.head_node, action_performer.app_bundle
                        )

                        logger.info("---------------------")
                        graph_plotting.draw_plot(
                            action_performer.action_manager.head_node, output_folder
                        )
                        graph_plotting.print_graph(
                            action_performer.action_manager.head_node, output_folder
                        )

                menu_output_file = os.path.join(
                    output_folder, f"{app_bundle}_extra_menu.json"
                )
                files.store_data_to_file(window, menu_output_file)


def extract_menu_bar(application, app_bundle, output_folder):
    menu_output_file = os.path.join(output_folder, f"{app_bundle}_menu.json")
    menu = element_attribute(application, ApplicationServices.kAXMenuBarAttribute)
    if menu is None:
        return
    menu_element = UIElement(menu)
    if len(menu_element.children) > 0:
        menu_element.children.remove(menu_element.children[0])

    for bar_item in menu_element.children:
        for menu in bar_item.children:
            menu.children = [
                menu_item for menu_item in menu.children if menu_item.name != ""
            ]

    files.store_data_to_file(menu_element, menu_output_file)


def is_action_belong_to_element(action: Graph.Action, element: UIElement):
    if action.element.identifier == element.identifier:
        return True
    for child in element.children:
        if is_action_belong_to_element(action, child):
            return True
    return False


def extract_app_windows(
    application, app_bundle, output_folder, perform_hit_test, print_nodes, move_cursor, add_tasks, agents_use, total_parse_time
) -> bool:
    windows = applications.windows_for_application(application)

    at_least_one_window_extracted = False
    for window in windows:
        window_element = UIElement(window)

        error = ApplicationServices.AXUIElementPerformAction(
            window, ApplicationServices.kAXRaiseAction
        )

        if error != ApplicationServices.kAXErrorSuccess:
            logger.error("Error raising of the window")
        
        time.sleep(1)

        extracted = window_tools.extract_window(
            window_element, app_bundle, output_folder, perform_hit_test, print_nodes
        )


        if extracted:
            action_manager = ActionManager()
            action_performer = ActionPerformer(app_bundle, action_manager, application, add_tasks, agents_use, total_parse_time)
            action_manager.head_node = action_performer.create_vertice(
                window_element, 
                output_folder, 
                add_cursor_move=move_cursor
            )
            action_manager.all_windows[window_element.identifier] = [window_element, window_element.recursive_children()]

            action_performer.perform_actions(action_manager.head_node, 
                                            output_folder, 
                                            0,
                                            100,
                                            move_cursor)

            last_screen = UIElement(action_manager.head_node.element.ax_element)
            last_screen_output_file = os.path.join(output_folder, f"{app_bundle}_last_screen.json")
            files.store_data_to_file(last_screen, last_screen_output_file)

            logger.info("---------------------")
            graph_plotting.draw_plot(action_manager.head_node, output_folder)
            graph_plotting.print_graph(action_manager.head_node, output_folder)
        
        at_least_one_window_extracted = True

    return at_least_one_window_extracted


def start_processing(app_bundle, perform_hit_test, print_nodes, output_folder, move_cursor, add_tasks, agents_use, total_parse_time) -> bool:
    logger.info("Processing of running applications")

    workspace = AppKit.NSWorkspace.sharedWorkspace()

    at_least_one_window_processed = False

    for app in workspace.runningApplications():
        if app_bundle is not None:
            if app.bundleIdentifier() != app_bundle:
                continue
        if app.localizedName() is None or len(app.localizedName()) == "":
            app_name = app.name()
        else:
            app_name = app.localizedName()
        logger.info(f"App name: {app_name}")

        app.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
        application = applications.application_for_process_id(app.processIdentifier())

        at_least_one_window_extracted = extract_app_windows(
            application,
            app_bundle,
            output_folder,
            perform_hit_test,
            print_nodes,
            move_cursor,
            add_tasks,
            agents_use,
            total_parse_time
        )

        if at_least_one_window_extracted:
            at_least_one_window_processed = True
    return at_least_one_window_processed

# add app details as a new line to the completed app_details.txt file
def _add_app_details_to_file(app_details, app_details_file):
    with open(app_details_file, "a") as f:
        f.writelines(f"{app_details}\n")
        print(f'Updated completed list with details: {app_details}')

def _add_report_item_to_file(report_item, report_file):
    print(f'Adding report item to file: {report_item}')
    try:
        with open(report_file, "r+") as f:
            all_items = json.load(f)
            if "items" not in all_items:
                all_items["items"] = {}
            bundle_id = report_item["app_bundle_id"]
            all_items["items"][bundle_id] = report_item
            f.seek(0)
            json.dump(all_items, f, indent=4)
            f.truncate()
            print(f'Updated report file with details: {report_item}')
    except FileNotFoundError:
        # If the file does not exist, create it and add the report_item
        with open(report_file, "w") as f:
            all_items = {"items": {report_item["app_bundle_id"]: report_item}}
            json.dump(all_items, f, indent=4)
            print(f'Created report file with details: {report_item}')

if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="Parse -a, -o, --cursor, --tasks, --print-nodes, --hit-test -t --total-parse-time argument")

    arg_parser.add_argument("-a", type=str, help="The application details")
    arg_parser.add_argument("-o", type=str, help="Output file")
    arg_parser.add_argument("--cursor", action="store_true", help="Cursor move in graph parsing")
    arg_parser.add_argument("--tasks", action="store_true", help="Add task strings on graph")
    arg_parser.add_argument("--print-nodes", action="store_true", help="Print nodes structure")
    arg_parser.add_argument("--hit-test", action="store_true", help="Perform hit test")
    arg_parser.add_argument("-t", type=str, help="Initial processing start time")
    arg_parser.add_argument("--llm-usage", type=str, help="LLM (GPT4) usage")
    arg_parser.add_argument("--total-parse-time", type=int, help="Maximum total parsing time per application in minutes")

    # parse the arguments
    args = arg_parser.parse_args()

    app_details = args.a
    output_path = args.o
    parse_start_timestamp = args.t

    perform_hit_test = False
    if args.hit_test:
        perform_hit_test = True

    print_nodes = False
    if args.print_nodes:
        print_nodes = True
    
    # store the screen scaling factor
    window_tools.store_screen_scaling_factor()

    move_cursor = False
    if args.cursor:
        move_cursor = True

    add_tasks = False
    if args.tasks:
        add_tasks = True


    agents_use = False
    if args.llm_usage:
        agents_use = True
    print("LLM usage: ", agents_use)

    total_parse_time = 120
    if args.total_parse_time:
        total_parse_time = int(args.total_parse_time)
    print("Total parse time: ", total_parse_time)

    # get the app details
    app = applications.app_for_description_details(app_details)

    perform_hit_test = False

    if app.bundle_id is None:
        logger.error("Application bundle is not specified")
        raise ValueError("Application bundle is not specified")

    output_folder = os.path.join(output_path, app.bundle_id)
    logger.info(f"Output folder: {output_folder}")
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    start_time = time.time()
    logger.info(f"Start time: {start_time}")
    if len(parse_start_timestamp) == 0:
        parse_start_timestamp = start_time

    at_least_one_window_processed = start_processing(app.bundle_id, perform_hit_test, print_nodes, output_folder, move_cursor, add_tasks, agents_use, total_parse_time)

    end_time = time.time()
    logger.info(f"End time: {end_time}")


    total_elapsed_time = end_time - start_time
    elapsed_time_str = time.strftime('%H:%M:%S', time.gmtime(total_elapsed_time))
    logger.info(f"Elapsed time: {elapsed_time_str}")

    success_report = 0
    if len(os.listdir(f"{output_folder}")) > 0:
        for dir_ in os.listdir(f"{output_folder}"):
            if dir_ == "graph":
                for file in os.listdir(f"{output_folder}/{dir_}"):
                    if file == "data.json":
                        success_report = 1


    if success_report:
        print("Success report: ", success_report)
        _add_app_details_to_file(app_details, "success_app_details.txt")
    else:
        print("No success report")
        _add_app_details_to_file(app_details, "failed_app_details.txt")

    report_item = {
        "app_name": app.name,
        "app_bundle_id": app.bundle_id,
        "app_localized_name": app.name,
        "input_app_details": app_details,
        "elapsed_time_str": elapsed_time_str,
        "elapsed_time_seconds": int(total_elapsed_time),
        "at_least_one_window_processed": at_least_one_window_processed # if at least one window was processed then the window has accessibility enabled
    }

    report_total_time = elapsed_time_str
    if parse_start_timestamp is not None:
        print("Parse start timestamp: ", parse_start_timestamp)
        report_total_time = time.strftime('%H:%M:%S', time.gmtime(int(end_time) - int(parse_start_timestamp)))
        print("Report total time: ", report_total_time)
        
    report_file_path = os.path.join(output_path, "completed_app_report.json")
    _add_report_item_to_file(report_item, report_file_path)

    generate_dashboard.generate_dashboard(output_path, report_file_path, report_total_time)

    logger.info("App parsing completed")
