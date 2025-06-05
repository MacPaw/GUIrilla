import numpy as np
import pyautogui
import logging
import ApplicationServices
import os
import time
import sentry_sdk

# import helpers.applications as applications
import helpers.element_graph as Graph
import helpers.applications as applications
import helpers.window_tools as window_tools

from helpers.uielement import UIElement, element_attribute

from agents.ordering_agent import get_clicking_order
from agents.input_agent import get_input_fields
from agents.utilities import json_to_xml

from screenshot_app_window import screenshot_app_window

from time import sleep

logger = logging.getLogger(__name__)

sentry_sdk.init(
    dsn="https://d9029ec11325e79e74f8f31c48352909@o36975.ingest.us.sentry.io/4508206814396416",
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
)

IMPACTFUL_ELEMENTS_AFTER_CLICK = 10

GENERIC_ROLES = ["AXGroup", "AXToolbar", "AXValueIndicator", "AXRadioGroup",
                 "AXGenericElement", "AXImage", "AXSplitGroup", "AXTabGroup",
                 "No role", "AXSheet", "AXTable", "AXOutline", "AXScrollArea", "AXDateTimeArea",
                 "AXGrid", "AXUnknown", "AXCell", "AXSplitter", "AXSlider", "AXLayoutArea",
                 "AXCell", "AXRow", "AXColumn", "AXPopUpButton", "AXGroup"]

NOT_MEANINGFUL_ROLES = [
    "AXToolbar", "AXSplitter", "AXSplitGroup", "AXHeading",
    "AXTabGroup", "AXOutline", "AXScrollArea", "AXLayoutArea",
    "AXGrid", "AXScrollBar", "AXSplitter", "No role",
    "AXSlider", "AXPopover", "AXUnknown", "AXValueIndicator",
]

UNROLLABLE_ELEMENTS = ["AXMenuItem", "AXPopover", "AXMenu", "AXMenuButton", "AXSheet"]
DYNAMICAL_ELEMENT_TYPES = ["AXTextField", "AXStaticText", "AXDateTimeArea", "AXCheckBox", "AXRadioButton",
                           "AXPopUpButton"]


class ActionManager:
    def __init__(self, debug_touch: bool = True):
        self.completed_action_identifiers = set()
        self.scheduled_action_identifiers = set()
        self.head_node = None
        self.debug_touch = debug_touch
        self.all_windows = {}  # identifier (of the window): [ui_element, recursive_children]
        self.all_window_nodes = []
        self.input_fields = {}
        self.checked_login = False
        self.checked_system_access = False

    def mark_action_completed(self, action: Graph.Action):
        if action.element.identifier in self.scheduled_action_identifiers:
            self.scheduled_action_identifiers.discard(action.element.identifier)
        if action.element.identifier not in self.completed_action_identifiers:
            self.completed_action_identifiers.add(action.element.identifier)


class ActionPerformer:
    def __init__(self, app_bundle: str, action_manager: ActionManager, application, add_tasks, agents_use, total_parse_time):
        self.app_bundle = app_bundle
        self.action_manager = action_manager
        self.start_time = time.time()
        self.application = application
        self.debug_with_double_click = True
        self.add_tasks = add_tasks
        self.agents_use = agents_use
        self.total_parse_time = total_parse_time

    def get_running_windows(self):
        windows = applications.windows_for_application(self.application)
        return len(windows), windows

    def extract_all_action_items(self, element: UIElement, press_key=None, add_cursor_move=False, set_unrolled=False, parent = None) -> \
    dict[
        str, Graph.Action]:
        if (
                element.role_description == "close button"
                or element.role_description == "minimize button"
                or element.role_description == "minimise button"
                or element.role_description == "full screen button"
                or element.role_description == "zoom button"
                or element.role_description == "toggle full screen"
        ):
            return {}

        all_actions = dict[str, Graph.Action]()

        # Rewriting the set of actions that can be performed on an element if a key press is required.
        if press_key is not None:
            element.action_items = [f"Press{press_key}"]
            element.identifier = f"{element.identifier}_key"

        # Rewriting the set of actions that can be performed on an element if cursor movement is required.
        if add_cursor_move == True and "_cursor" not in element.identifier:
            element.action_items = ["MoveCursor"]
            element.identifier = f"{element.identifier}_cursor"

        if set_unrolled:
            element.unrolled = True
            if parent is not None:
                element.parent = parent

        all_actions[element.identifier] = Graph.Action(
            element=element,
            action_names=element.action_items,
            is_defined_action=element.is_button(),
        )

        if ((element.value is None or len(str(element.value)) == 0)
                and (element.role_description is None or len(element.role_description) == 0)
                and (element.description is None or len(element.description) == 0)):
            all_actions.pop(element.identifier)

        for child in element.children:
            child_actions = self.extract_all_action_items(child, press_key=press_key, add_cursor_move=add_cursor_move,
                                                          set_unrolled=set_unrolled, parent=element)
            all_actions.update(child_actions)

        return all_actions

    def _skip_descrement_and_increment_buttons(self, action):
        if action.element.role_description is not None:
            if len(str(action.element.role_description)) > 0 and (
                    "decrement" in action.element.role_description or "increment" in action.element.role_description):
                logger.debug("Skipping decrement/increment button")
                return True

    def _add_new_children_to_order(self, children, parents_order):
        children.reverse()
        new_order = parents_order + children
        return new_order

    def _check_and_log_requirements(self, login_page: bool, system_access_required: bool):
        """Helper method to handle logging for login and system permissions."""
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

        if login_page and not self.action_manager.checked_login:
            self.action_manager.checked_login = True
            sentry_sdk.capture_message(f"Login Required: {self.app_bundle} {current_time}")
            logger.info(f"Login Required: {self.app_bundle}")

        if system_access_required and not self.action_manager.checked_system_access:
            self.action_manager.checked_system_access = True
            sentry_sdk.capture_message(f"System Permissions Required: {self.app_bundle} {current_time}")
            logger.info(f"System Permissions Required: {self.app_bundle}")

    def _add_new_ids_to_inputs(self, element):
        xml_data, id_mapping = json_to_xml(element.to_dict())
        if self.agents_use:

            predicted_inputs = get_input_fields(xml_data, id_mapping, self.action_manager.input_fields)

            if predicted_inputs:
                logger.info(f"Predicted inputs: {predicted_inputs, self.action_manager.input_fields}")
                self.action_manager.input_fields.update(predicted_inputs)
            else:
                logger.info(f"No inputs predicted for {element.identifier}")
                self.action_manager.input_fields.update({element.identifier: "DEFAULT"})
        else:
            logger.info(f"Default input for element {element.identifier}")
            self.action_manager.input_fields.update({element.identifier: "DEFAULT"})

    def _make_screenshot_and_crop(self, element, output_folder, add_cursor_move):
        applications.kill_store_user_notification()

        output_folder = os.path.join(output_folder, "graph", "images")
        name_and_coors = screenshot_app_window(
            self.app_bundle, element.name, element.identifier, output_folder, add_cursor_move=add_cursor_move
        )
        if name_and_coors is None:
            logger.error("Error: image name is None")
            return None
        image_name, window_coordinates = name_and_coors
        image_path = os.path.join(output_folder, image_name)
        window_tools.segment_window_components(element, image_path)
        return image_path

    def create_vertice(self,
                       element: UIElement,
                       output_folder: str,
                       add_cursor_move=False,
                       press_key=None,
                       custom_order=None) -> Graph.Vertice:
        all_action_items = self.extract_all_action_items(element, press_key=press_key, add_cursor_move=add_cursor_move)

        output_folder = os.path.join(output_folder, "graph", "images")
        print(f'Resulting output folder: {output_folder}, app bundle: {self.app_bundle}')

        name_and_coors = screenshot_app_window(
            self.app_bundle, element.name, element.identifier, output_folder, add_cursor_move
        )

        if name_and_coors is None:
            logger.error("Error: image name is None")
            return None

        image_name, window_coordinates = name_and_coors
        image_path = os.path.join(output_folder, image_name)
        if element.role == "AXWindow":
            if custom_order is None:
                print(f"Getting clicking order for {element.role, element.description}")
                xml_data, id_mapping = json_to_xml(element.to_dict())
                if self.agents_use:
                    page_analysis = get_clicking_order(xml_data, id_mapping) or {
                        "action_order": [],
                        "login_page": False,
                        "system_access_required": False,
                    }
                    children_order = page_analysis["action_order"]

                    self._check_and_log_requirements(page_analysis["login_page"], page_analysis["system_access_required"])

                    predicted_inputs = get_input_fields(xml_data, id_mapping, self.action_manager.input_fields)

                    if predicted_inputs:
                        logger.info(f"Predicted inputs: {predicted_inputs, self.action_manager.input_fields}")
                        self.action_manager.input_fields.update(predicted_inputs)

                    if children_order is None:
                        print(f"Children order is None for {element.identifier}")
                else:
                    children_order = [e.identifier for e in element.recursive_children()]
            else:
                children_order = custom_order

            order_map = {
                identifier: index for index, identifier in enumerate(children_order)
            }


            max_index = max(order_map.values())
            action_items = [None] * (max_index + 1)
            for _, (key, value) in enumerate(order_map.items()):
                item = all_action_items.get(key)
                action_items[value] = item
            action_items = [item for item in action_items if item is not None]
            action_items.reverse()

            should_be_dismissed = False
            popover_items = []
            for action in action_items:
                if action.element.role in UNROLLABLE_ELEMENTS:
                    logger.info("Popover has been found")
                    action.element.unrolled = True
                    all_child_items = self.extract_all_action_items(action.element, add_cursor_move=add_cursor_move,
                                                                    press_key=press_key, set_unrolled=True,
                                                                    parent=element)
                    popover_items.extend(all_child_items.values())

            if len(popover_items) > 0:
                cleaned_action_items = filter(
                    lambda i: i not in action_items, popover_items
                )
                action_items_popover_only = popover_items + list(cleaned_action_items)
                # We are going to click popover items first, and then all the rest
                action_items = action_items_popover_only + action_items
        else:
            action_items = []
            should_be_dismissed = False
            children_order = custom_order

        window_tools.segment_window_components(element, image_path)

        return Graph.Vertice(element, image_name, action_items, should_be_dismissed, window_coordinates,
                             clicking_order=children_order, add_tasks=self.add_tasks)

    def is_child_exists(self, element: UIElement, child: UIElement):
        if element.identifier == child.identifier:
            return True
        if element.ax_element == child.ax_element:
            return True
        for child_element in element.children:
            if self.is_child_exists(child_element, child):
                return True
        return False

    def _to_skip_completed_action(self, action):
        if (
                action.element.identifier
                in self.action_manager.completed_action_identifiers
        ):
            if action.element.role == "AXPopover":
                logger.debug("Popover has been already processed")
                self.action_manager.mark_action_completed(action)
                pyautogui.press("escape", interval=0.5)
                return True
            logger.debug("Skipping action")
            return True
        return False

    def _click_on_element(self, action: Graph.Action):
        try:
            pyautogui.click(x=action.element.center[0], y=action.element.center[1], duration=1.0)
            error = 0
        except OverflowError:
            logger.error(
                f"Overflow while clicking on {action.element.center[0], action.element.center[1]}"
            )
            error = -1
        return error

    def _failed_check_in_bounds(self, element, current_node, parent=None):

        if parent is not None:
            if parent.role in ["AXMenu", "AXSheet", "AXWindow"]:
                if self._is_on_screen(parent):
                    return False
                else:
                    return True

            # Sometimes parents coordinates are defined relative to the window's position
            offset_x = current_node.element.position.x
            offset_y = current_node.element.position.y

            left = parent.position.x + offset_x
            top = parent.position.y + offset_y
            right = parent.position.x + parent.size.width + offset_x
            bottom = parent.position.y + parent.size.height + offset_y
        else:
            left, top, right, bottom = current_node.window_coors_scaled
            print(
                f"Checking if element {element.role, element.description, element.center} is in bounds of the window {left, top, right, bottom}")

        if (min(element.center) < 0 or
                element.center[0] < left or
                element.center[0] > right or
                element.center[1] < top or
                element.center[1] > bottom):
            return True
        return False

    def _is_in_group(self, element: UIElement, group: UIElement):
        all_children = group.recursive_children()
        for child in all_children:
            if (child.identifier == element.identifier
                    or child.identifier + "_cursor" == element.identifier
                    or child.identifier + "_key" == element.identifier
            ):
                logger.info(
                    f"Element {element.role, element.description} is in a group {group.role, group.description}")
                return True
        return False

    def _is_on_screen(self, element: UIElement):
        head_screen = UIElement(self.action_manager.head_node.element.ax_element)
        all_children = head_screen.recursive_children()
        for child in all_children:
            if (child.identifier == element.identifier
                    or child.identifier + "_cursor" == element.identifier
                    or child.identifier + "_key" == element.identifier
            ):
                return True

        if len(self.action_manager.all_windows) > 1:
            for window_id in self.action_manager.all_windows:
                window_element = self.action_manager.all_windows[window_id][0]
                node_screen = UIElement(window_element.ax_element)
                recursive_children = self.action_manager.all_windows[window_id][1]

                if len(recursive_children) == 0:
                    logger.info(f"No children in the popup window with name:{node_screen.name}")
                    continue

                for child in recursive_children:
                    if child.identifier == element.identifier or child.identifier + "_cursor" == element.identifier:
                        logger.info(f"Element {element.role, element.description} is on screen in a popped window")
                        return True
        logger.info(f"Element {element.role}, {element.description} is not on the visible screen")
        return False

    def _handle_click(self, action, current_node, level, max_depth, move_cursor_default, output_folder):
        logger.info(
            f"Clicking on {action.element.role}, {action.element.description}, {action.element.role_description}....")

        if self.debug_with_double_click:
            logger.info(
                f"Checking for the popup window after clicking on {action.element.role}, {action.element.description}, {action.element.role_description}....")
            # Checking whether the popup window appeared after click
            n_before, windows_before = self.get_running_windows()
            if self.add_tasks:
                if not self._capture_pre_action_screenshot(current_node, output_folder, move_cursor_default, action):
                    logger.info("Failed to make a screenshot before a click")

            error = self._click_on_element(action)

            if self.add_tasks:
                sleep(0.5)
                if not self._capture_post_action_screenshot(current_node, output_folder, move_cursor_default, action):
                    logger.info("Failed to make a screenshot after a click")

            if action.element.role == "AXLink":
                logger.info("Clicked a link, bringing the window back")
                if action.element.unrolled:
                    pyautogui.press("escape", interval=0.5)
                window_tools.bring_window_to_front(self.app_bundle)

            current_node.executed_actions.append(action)
            sleep(0.5)
            n_after, windows_after = self.get_running_windows()

            # Handling the popup window
            if n_before < n_after:
                logger.info("Popup window appeared after click!")

                sleep(3.0)

                new_window = [w for w in windows_after if w not in windows_before][0]
                new_screen = UIElement(new_window)

                next_node = self.create_vertice(new_screen, output_folder, add_cursor_move=move_cursor_default)

                if next_node is None:
                    return 1
                self.action_manager.all_windows[new_screen.identifier] = [new_screen, new_screen.recursive_children()]
                current_node.add_child_node(action, next_node)
                self.perform_actions(next_node,
                                     output_folder,
                                     level + 1,
                                     max_depth,
                                     move_cursor_default)
                self.action_manager.mark_action_completed(action)
                return error

            # Handling the unrolled elements on a window after a single click
            unrolling_window = UIElement(current_node.element.ax_element)
            same_window = unrolling_window.identifier == current_node.element.identifier
            different_contents = unrolling_window.content_identifier != current_node.element.content_identifier
            invisible_children_added = len(unrolling_window.recursive_children()) > len(
                current_node.element.recursive_children())

            # Adding new node to process new window
            if not same_window:
                logger.info("Different window after click")
                new_screen = UIElement(current_node.element.ax_element)
                next_node = self.create_vertice(new_screen, output_folder, add_cursor_move=move_cursor_default)
                if next_node is None:
                    return 1
                current_node.add_child_node(action, next_node)
                self.perform_actions(next_node,
                                     output_folder,
                                     level + 1,
                                     max_depth,
                                     move_cursor_default)
                return error

            # Sometimes the menu-popup element is unrolled after a single click.
            # Below, checking the number of children because when hashing the contents, a child of a popup menu can have null values in important fields for the component hash, causing the content hashes to be identical even though the contents differ.

            if (same_window and different_contents) or (same_window and invisible_children_added):
                logger.info("Let's see if we can see new elements appeared after a single click...")
                added_elements = self._parse_added_elements(current_node, unrolling_window)

                inherited_elements_list, parent_clicking_order = self._get_inherited_elements(added_elements,
                                                                                              current_node,
                                                                                              move_cursor_default,
                                                                                              unrolling_window,
                                                                                              action)

                # Click on unrolled element
                if len(inherited_elements_list) == 0:
                    return error
                else:
                    logger.info(f"New {len(inherited_elements_list)} children appeared after click! Processing them...")

                    self.action_manager.mark_action_completed(action)

                    new_order = self._add_new_children_to_order(inherited_elements_list, parent_clicking_order)
                    next_node = self.create_vertice(unrolling_window,
                                                    output_folder,
                                                    add_cursor_move=move_cursor_default,
                                                    custom_order=new_order)

                    if next_node is None:
                        return 1

                    for indx, action_next in enumerate(next_node.actions):
                        if (action_next.element.role in UNROLLABLE_ELEMENTS):
                            action_next.element.unrolled = True
                            next_node.element.unrolled = True
                            next_node.element.parent = current_node.element
                    current_node.add_child_node(action, next_node)
                    self.perform_actions(next_node,
                                         output_folder,
                                         level + 1,
                                         max_depth,
                                         move_cursor_default)
                    return error
            else:
                return error

        else:

            if self.add_tasks:
                if not self._capture_pre_action_screenshot(current_node, output_folder, move_cursor_default, action):
                    logger.info("Failed to make a screenshot before a click")

            error = self._click_on_element(action)

            if self.add_tasks:
                sleep(0.5)
                if not self._capture_post_action_screenshot(current_node, output_folder, move_cursor_default, action):
                    logger.info("Failed to make a screenshot after a click")

            return error

    def _is_time_limit_reached(self):
        # Not allowing the crawler to collect the dataset for more than total_parse_time minutes
        if time.time() - self.start_time > self.total_parse_time * 60:
            logger.info("Time limit reached 🕚")
            pyautogui.press("escape", interval=0.5)
            return True
        return False

    def _is_max_depth_reached(self, level, max_depth):
        if level > max_depth:
            logger.warning("Max recursion depth reached")
            return True
        return False

    def _to_skip_sidebar_button(self, action):
        if action.element.description is not None:
            if (
                    action.element.description == "Sidebar"
                    and action.element.role == "AXButton"
            ):
                logger.debug("Skipping sidebar action")
                return True
        return False

    def _to_skip_empty_elements(self, action):
        if ((action.element.value is None or len(str(action.element.value)) == 0)
                and (action.element.role_description is None or len(action.element.role_description) == 0)
                and (action.element.description is None or len(action.element.description) == 0)):
            return True
        elif (action.element.role in GENERIC_ROLES
              and (action.element.description is None or len(action.element.description) == 0)
              and (action.element.value is None or len(str(action.element.value)) == 0)):
            return True
        else:
            return False

    def _to_skip_menu(self, action):
        if (
                action.element.description == "Overlay menu"
                or action.element.role == "AXMenu"
        ):
            logger.debug("Skipping menu action")
            self.action_manager.mark_action_completed(action)
            pyautogui.press("escape", interval=0.5)
            return True
        return False

    def _to_skip_window_standard(self, action):
        if (
                action.element.role_description == "close button"
                or action.element.role_description == "minimize button"
                or action.element.role_description == "minimise button"
                or action.element.role_description == "full screen button"
                or action.element.role_description == "zoom button"
                or action.element.role_description == "toggle full screen"
                or action.element.role_description == "standard window"
        ):
            logger.debug("Skipping action")
            self.action_manager.mark_action_completed(action)
            return True
        return False

    def _to_skip_child_verification(self, action):
        if action.element.role == "AXPopover":
            logger.debug("Skipping child verification")
            return True
        return False

    def _skip_non_meaningful_elements(self, action):
        if action.element.role in NOT_MEANINGFUL_ROLES:
            logger.debug("Skipping generic role action")
            return True
        elif action.names == ["AXScrollToVisible"]:
            logger.debug("Skipping empty AXScrollToVisible action", action.element.role, action.element.description,
                         action.element.value)
            return True

    def _process_actions_for_performing(self, current_node, move_cursor_default) -> list[Graph.Action]:
        actions_to_perform = []

        if current_node.element.role == "AXWindow" and current_node.element.description == "alert":
            for i, action_next in enumerate(current_node.actions):
                self.action_manager.scheduled_action_identifiers.add(
                    action_next.element.identifier
                )
                if move_cursor_default:
                    self.action_manager.scheduled_action_identifiers.add(
                        action_next.element.identifier + "_cursor"
                    )

                actions_to_perform.append(action_next)
            return actions_to_perform

        for i, action_next in enumerate(current_node.actions):

            if (
                    action_next.element.identifier
                    not in self.action_manager.scheduled_action_identifiers
                    and action_next.element.identifier
                    not in self.action_manager.completed_action_identifiers
            ):
                self.action_manager.scheduled_action_identifiers.add(
                    action_next.element.identifier
                )
                if move_cursor_default:
                    self.action_manager.scheduled_action_identifiers.add(
                        action_next.element.identifier + "_cursor"
                    )

                actions_to_perform.append(action_next)
        return actions_to_perform

    def _bring_window_to_front_if_needed(self, action, current_node):
        print("Checking if window should be brought to front")
        if action.element.unrolled or current_node.element.unrolled:
            logger.info("Unrolled action, or menu appeared, so window should be in the front")
        else:
            timeout = 2
            result_ = window_tools.timed_window_bring_to_front(self.app_bundle, timeout)
            # window_tools.bring_window_to_front(self.app_bundle)
            if not result_:
                logger.info(f"Window bring to front took longer than {timeout} seconds")
                pyautogui.press("escape", interval=0.5)
                sleep(0.5)
                window_tools.bring_window_to_front(self.app_bundle)
                sleep(0.5)

    def _dismiss_popover_if_needed(self, node):
        if node.should_be_dismissed:
            logger.info("Dismissing popover")
            window_tools.bring_window_to_front(self.app_bundle)
            pyautogui.press("escape", interval=0.5)
            sleep(0.5)

    def _skip_toolbar(self, action):
        if action.element.role == "AXToolbar":
            logger.debug("Skipping toolbar action")
            return True

    def _move_cursor_to_element(self, action, duration=0.1):
        pyautogui.moveTo(
            x=action.element.center[0], y=action.element.center[1], duration=duration
        )
        sleep(0.1)

    def _parse_added_elements(self, current_node, new_screen):
        added_elements = []
        all_prev_identifiers = [e.identifier for e in current_node.element.recursive_children()]
        new_node_children = set(new_screen.recursive_children())
        for e in new_node_children:
            if e.identifier + "_cursor" not in all_prev_identifiers and e.identifier not in all_prev_identifiers:
                added_elements.append(e)
        return added_elements

    def _clicked_element_on_same_center(self, e, current_node):
        if current_node.element.identifier in self.action_manager.all_windows:
            recursive_children = self.action_manager.all_windows[current_node.element.identifier][1]
            for child in recursive_children:
                if e.center is not None and child.center is not None:
                    if child.role == e.role and child.description == e.description and child.center == e.center:
                        if child.identifier in self.action_manager.completed_action_identifiers:
                            # element has been processed once
                            logger.info(f"Element {e.role}, {e.description} has been already processed once")
                            return True
                    else:
                        return False
        return False

    def _check_scheduled_or_parsed_element(self, e, current_node):
        return (e.identifier not in self.action_manager.scheduled_action_identifiers
                and e.identifier + "_cursor" not in self.action_manager.scheduled_action_identifiers
                and e.identifier not in self.action_manager.completed_action_identifiers
                and e.identifier + "_cursor" not in self.action_manager.completed_action_identifiers
                and e.identifier not in current_node.clicking_order
                and e.identifier + "_cursor" not in current_node.clicking_order
                and not self._clicked_element_on_same_center(e, current_node)
                )

    def _get_inherited_elements(self, added_elements, current_node, move_cursor_default, new_screen, action,
                                enter_pressed=False):
        new_input_field = False
        text_field_id = None
        # Finding the elements that are in the unrolled window and not in the window where we have already parsed actions.
        inherited_elements_list = []
        for e in added_elements:
            if self._check_scheduled_or_parsed_element(e, current_node):
                if move_cursor_default:
                    e.identifier += "_cursor"
                if (e.role in UNROLLABLE_ELEMENTS or action.element.unrolled):
                    e.unrolled = True
                    e.parent = current_node.element
                    inherited_elements_list.insert(0, e.identifier)
                else:
                    inherited_elements_list.append(e.identifier)

                if e.role in DYNAMICAL_ELEMENT_TYPES:
                    # checking whether a new element appeared in a different location
                    if e.center is not None and action.element.center is not None:
                        if e.center == action.element.center or np.linalg.norm(
                                np.array(e.center) - np.array(action.element.center)) < 50:
                            new_input_field = False
                            self.action_manager.completed_action_identifiers.add(e.identifier)
                            inherited_elements_list.remove(e.identifier)

                if enter_pressed:
                    if e.center is not None and action.element.center is not None:
                        if (e.center[0] >= action.element.position.x and e.center[1] >= action.element.position.y
                                and e.center[0] <= action.element.position.x + action.element.size.width
                                and e.center[1] <= action.element.position.y + action.element.size.height):
                            # new element (like cancel) appeared in the same location
                            self.action_manager.completed_action_identifiers.add(e.identifier)
                            inherited_elements_list.remove(e.identifier)
        parent_clicking_order = current_node.clicking_order
        if new_input_field:
            logger.info("New input field appeared")
            self._add_new_ids_to_inputs(new_screen)
            # adding to first parse the input fields
            inherited_elements_list.sort(key=lambda x: x == text_field_id, reverse=True)

        return inherited_elements_list, parent_clicking_order

    def _capture_pre_action_screenshot(self, current_node, output_folder, move_cursor_default, action):
        screenshot_pre_action_path = self._make_screenshot_and_crop(current_node.element, output_folder, move_cursor_default)
        if screenshot_pre_action_path is None:
            return False
        else:
            action.screenshot_pre_action_path = screenshot_pre_action_path
            return True

    def _capture_post_action_screenshot(self, current_node, output_folder, move_cursor_default, action):
        sleep(0.5)
        screenshot_post_action_path = self._make_screenshot_and_crop(current_node.element, output_folder,
                                                                     move_cursor_default)
        if screenshot_post_action_path is None:
            return False
        else:
            action.screenshot_post_action_path = screenshot_post_action_path
            return True


    def perform_actions(
            self,
            current_node: Graph.Vertice,
            output_folder: str,
            level: int = 0,
            max_depth: int = 25,
            move_cursor_default: bool = False
    ):
        if current_node.element.unrolled:
            logger.info(
                "In unrolled action, or menu")

            if self._is_time_limit_reached():
                print("Time limit reached")
                return
        else:
            if self._is_time_limit_reached():
                print("Time limit reached")
                return

        if self._is_max_depth_reached(level, max_depth):
            print("Max depth reached")
            return

        actions_to_perform = self._process_actions_for_performing(current_node, move_cursor_default)
        if len(actions_to_perform) == 0:
            logger.info("No actions to perform, potential parsing issue")
            return

        for index, action in enumerate(actions_to_perform):

            if self._skip_descrement_and_increment_buttons(action):
                print("Skipping decrement/increment button", action.element.description, action.element.value,
                      action.element.role)
                continue

            if self._to_skip_empty_elements(action):
                print("Skipping empty element", action.element.description, action.element.value, action.element.role)
                continue

            if self._skip_non_meaningful_elements(action):
                print("Skipping non-meaningful element", action.element.description, action.element.value,
                      action.element.role)
                continue

            if self._skip_toolbar(action):
                print("Skipping toolbar element", action.element.description, action.element.value, action.element.role)
                continue

            if self._to_skip_sidebar_button(action):
                print("Skipping sidebar button", action.element.description, action.element.value, action.element.role)
                continue

            if self._to_skip_completed_action(action):
                print("Skipping completed action", action.element.description, action.element.value,
                      action.element.role)
                continue

            if self._to_skip_window_standard(action):
                print("Skipping window standard action", action.element.description, action.element.value,
                      action.element.role)
                continue

            if self._clicked_element_on_same_center(action.element, current_node):
                print("Skipping clicked element on the same center", action.element.description, action.element.value,
                      action.element.role)
                continue

            print("Checking for", action.element.description, action.element.name, action.element.value,
                  action.element.role, action.element.role_description, action.element.unrolled)

            # sometimes popover items, or windows move outside the border of the window
            if not action.element.unrolled:
                if self._failed_check_in_bounds(action.element, current_node) or not self._is_on_screen(action.element):
                    print("Skipping out of bounds element", action.element.description, action.element.value,
                          action.element.role)
                    self.action_manager.scheduled_action_identifiers.remove(action.element.identifier)
                    continue
            else:
                element_failed_in_main_node = self._failed_check_in_bounds(action.element, current_node)
                element_failed_in_parent = self._failed_check_in_bounds(action.element, current_node,
                                                                        action.element.parent)
                element_in_group = self._is_in_group(action.element, action.element.parent)
                element_on_screen = self._is_on_screen(action.element)

                element_in_group_but_group_not_on_screen = element_in_group and not element_failed_in_parent
                element_in_main_node_and_on_screen = not element_failed_in_main_node and element_on_screen

                print(
                    f"Failed in node {element_failed_in_main_node}, on screen {element_on_screen}, failed in parent {element_failed_in_parent}, in group {element_in_group},  element_in_group_but_group_not_on_screen {element_in_group_but_group_not_on_screen},  element_in_main_node_and_on_screen {element_in_main_node_and_on_screen}")

                if not element_in_main_node_and_on_screen and not element_in_group_but_group_not_on_screen:
                    print("Skipping out of bounds element unrolled", action.element.description, action.element.value,
                          action.element.role)
                    self.action_manager.scheduled_action_identifiers.remove(action.element.identifier)
                    continue

            self._bring_window_to_front_if_needed(action, current_node)
            skip_scheduled_item_verification = not self._to_skip_child_verification(action)

            current_screen = UIElement(current_node.element.ax_element)
            # Initially, always move cursor to elements on the window.
            if "MoveCursor" in action.names:
                if self.add_tasks:
                    self._move_cursor_to_element(action)
                    screenshot_pre_action_path = self._make_screenshot_and_crop(current_node.element, output_folder,
                                                                                move_cursor_default)
                    if screenshot_pre_action_path is None:
                        continue
                    else:
                        action.screenshot_pre_action_path = screenshot_pre_action_path

                logger.info(f"Moving cursor to {action.element.role}, {action.element.description}")
                self._move_cursor_to_element(action, duration=0.2)

                if self.add_tasks:
                    self._move_cursor_to_element(action)
                    screenshot_post_action_path = self._make_screenshot_and_crop(current_node.element, output_folder,
                                                                                 move_cursor_default)
                    if screenshot_post_action_path is None:
                        continue
                    else:
                        action.screenshot_post_action_path = screenshot_post_action_path

                current_node.executed_actions.append(action)

                new_screen = UIElement(current_node.element.ax_element)
                same_window = new_screen.identifier + "_cursor" == current_node.element.identifier
                different_contents = new_screen.content_identifier != current_node.element.content_identifier
                invisible_children_added = len(new_screen.recursive_children()) > len(
                    current_node.element.recursive_children())

                # checking whether the content changed after moving the cursor to an object
                if (not same_window) or (same_window and different_contents) or (
                        same_window and invisible_children_added):
                    logger.info("Let's see if we can see new elements appeared after moving a cursor...")

                    added_elements = self._parse_added_elements(current_node, new_screen)

                    inherited_elements_list, parent_clicking_order = self._get_inherited_elements(added_elements,
                                                                                                  current_node,
                                                                                                  move_cursor_default,
                                                                                                  new_screen,
                                                                                                  action)

                    if len(inherited_elements_list) > 0:
                        logger.info(
                            f"{len(inherited_elements_list)} new children appeared after moving a cursor! Processing them...")
                        new_order = self._add_new_children_to_order(inherited_elements_list, parent_clicking_order)
                        next_node = self.create_vertice(new_screen,
                                                        output_folder,
                                                        add_cursor_move=move_cursor_default,
                                                        custom_order=new_order)

                        if next_node is None:
                            continue
                        current_node.add_child_node(action, next_node)
                        self.perform_actions(next_node,
                                             output_folder,
                                             level + 1,
                                             max_depth,
                                             move_cursor_default)
                        continue
                    else:
                        logger.info("No new elements appeared after moving a cursor...")

                logger.info("Creating a click action after moving a cursor...")

                # Adding clicking actions to the node
                new_id = action.element.identifier[:-7]
                added_elements = [new_id]
                # Adding clicking actions to the node
                parent_clicking_order = current_node.clicking_order

                new_order = self._add_new_children_to_order(added_elements, parent_clicking_order)
                next_node = self.create_vertice(new_screen,
                                                output_folder,
                                                add_cursor_move=False,
                                                custom_order=new_order)

                next_node.window_coors_scaled = current_node.window_coors_scaled
                if next_node is None:
                    continue
                current_node.add_child_node(action, next_node)
                self.perform_actions(next_node,
                                     output_folder,
                                     level + 1,
                                     max_depth,
                                     move_cursor_default)
                self.action_manager.mark_action_completed(action)
                continue

            # perform action on the text field and enter random text
            if (
                    action.element.role == "AXTextField" or action.element.role == "AXTextArea") and "PressEnter" not in action.names:
                if self.add_tasks:
                    if not self._capture_pre_action_screenshot(current_node, output_folder, move_cursor_default, action):
                        continue

                logger.info("Just inputting the text, without clicking enter")

                # Inputting the text
                clean_identifier = action.element.identifier.split("_")[0]
                if clean_identifier not in self.action_manager.input_fields:
                    self._add_new_ids_to_inputs(action.element)
                text_input = self.action_manager.input_fields[clean_identifier]
                ApplicationServices.AXUIElementSetAttributeValue(
                    action.element.ax_element,
                    ApplicationServices.kAXValueAttribute,
                    text_input
                )

                # Adding the post-action screenshot
                if self.add_tasks:
                    if not self._capture_post_action_screenshot(current_node, output_folder, move_cursor_default, action):
                        continue

                current_node.executed_actions.append(action)
                sleep(1.0)
                new_screen = UIElement(current_node.element.ax_element)

                # Special case of parsing inherited elements after text input
                # Adding just 1 child to press enter after text input
                added_elements = self._parse_added_elements(current_node, new_screen)

                inherited_elements_list = []
                for e in added_elements:
                    if self._check_scheduled_or_parsed_element(e, current_node):
                        if e.role == action.element.role:
                            inherited_elements_list.append(e)

                parent_clicking_order = current_node.clicking_order
                if len(inherited_elements_list) == 0:
                    inherited_elements_list = [action.element.identifier + "_key"]
                else:
                    # to avoid loops in changing the value
                    self.action_manager.completed_action_identifiers.add(inherited_elements_list[0].identifier)
                    inherited_elements_list = [inherited_elements_list[0].identifier + "_key"]

                new_order = self._add_new_children_to_order(inherited_elements_list, parent_clicking_order)

                next_node = self.create_vertice(new_screen,
                                                output_folder,
                                                add_cursor_move=False,
                                                press_key="Enter",
                                                custom_order=new_order)
                if next_node is None:
                    continue
                action.input = text_input
                current_node.add_child_node(action, next_node)
                self.perform_actions(next_node,
                                     output_folder,
                                     level + 1,
                                     max_depth,
                                     move_cursor_default)
                self.action_manager.mark_action_completed(action)
                continue

            if "PressEnter" in action.names:

                if self.add_tasks:
                    if not self._capture_pre_action_screenshot(current_node, output_folder, move_cursor_default, action):
                        continue

                logger.info(f"Pressing Enter on {action.element.role}, {action.element.description}")
                pyautogui.press("enter", interval=0.5)
                sleep(0.2)

                if self.add_tasks:
                    if not self._capture_post_action_screenshot(current_node, output_folder, move_cursor_default, action):
                        continue

                current_node.executed_actions.append(action)

                # Checking whether the popup window appeared after clicking Enter
                new_screen = UIElement(current_node.element.ax_element)
                added_elements = self._parse_added_elements(current_node, new_screen)

                inherited_elements_list, parent_clicking_order = self._get_inherited_elements(added_elements,
                                                                                              current_node,
                                                                                              move_cursor_default,
                                                                                              new_screen,
                                                                                              action,
                                                                                              enter_pressed=True)

                new_order = self._add_new_children_to_order(inherited_elements_list, parent_clicking_order)
                next_node = self.create_vertice(new_screen,
                                                output_folder,
                                                add_cursor_move=move_cursor_default,
                                                custom_order=new_order)
                if next_node is None:
                    continue
                current_node.add_child_node(action, next_node)

                self.perform_actions(next_node,
                                     output_folder,
                                     level + 1,
                                     max_depth,
                                     move_cursor_default)
                self.action_manager.mark_action_completed(action)
                continue

            if not action.element.unrolled and not self.is_child_exists(current_screen, action.element):
                logger.warning(f"Item not found: {action.element.identifier}")

                if skip_scheduled_item_verification:
                    if (
                            action.element.identifier
                            in self.action_manager.scheduled_action_identifiers
                            and level != 0
                    ):
                        logger.debug(
                            "Item is scheduled on another node: ",
                            action.element.identifier,
                        )
                        self.action_manager.mark_action_completed(action)
                        continue

            error = 0
            if action.is_defined_action or (
                    action.element.identifier
                    not in self.action_manager.completed_action_identifiers
            ):
                self._move_cursor_to_element(action)
                error = self._handle_click(action, current_node, level, max_depth, move_cursor_default, output_folder)

            last_screen = current_node.element
            new_screen = UIElement(current_node.element.ax_element)

            if error == 0:
                logger.info("Action activated")

                # Need to comment this if-clause out if we want to keep the node even when the content did not change
                if (
                        last_screen.identifier != new_screen.identifier
                        or last_screen.content_identifier != new_screen.content_identifier
                ):
                    existing_window = window_tools.is_window_exists(
                        self.action_manager.head_node, new_screen
                    )
                    if existing_window is not None:
                        logger.info("Window already exists")
                        continue

                    if len(new_screen.children) == 0:
                        logger.info("No children found")
                        self.action_manager.mark_action_completed(action)
                        continue

                    added_elements = self._parse_added_elements(current_node, new_screen)

                    if len(added_elements) > IMPACTFUL_ELEMENTS_AFTER_CLICK:
                        next_node = self.create_vertice(new_screen,
                                                        output_folder,
                                                        add_cursor_move=move_cursor_default)
                    else:
                        inherited_elements_list, parent_clicking_order = self._get_inherited_elements(added_elements,
                                                                                                      current_node,
                                                                                                      move_cursor_default,
                                                                                                      new_screen,
                                                                                                      action)

                        new_order = self._add_new_children_to_order(inherited_elements_list, parent_clicking_order)
                        next_node = self.create_vertice(new_screen,
                                                        output_folder,
                                                        add_cursor_move=move_cursor_default,
                                                        custom_order=new_order)

                    if next_node is None:
                        continue
                    current_node.add_child_node(action, next_node)

                    self.perform_actions(next_node,
                                         output_folder,
                                         level + 1,
                                         max_depth,
                                         move_cursor_default)
                    self.action_manager.mark_action_completed(action)
            else:
                logger.error("Action failed")
