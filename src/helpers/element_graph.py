from helpers.uielement import UIElement
from typing import Self
import random

roles_to_skip = [
    "AXSplitter",
]

def get_press_prefix():
    return random.choice(["click", "press", "tap", "select", "choose", "click on", "press on", "tap on", "select on", "choose on", "click the", "press the", "tap the", "select the", "choose the"]) + " "

def get_check_prefix():
    return random.choice(["check", "uncheck", "toggle", "check the", "uncheck the", "toggle the"]) + " "

def get_scroll_prefix():
    return random.choice(["scroll", "scroll the", "scroll to", "scroll to the"]) + " "

def get_input_text(string_to_input):
    return random.choice([f"input '{string_to_input}' into", f"write '{string_to_input}' into", f"enter '{string_to_input}' into", f"input '{string_to_input}' in", f"write '{string_to_input}' in", f"enter '{string_to_input}' in"]) + " "


def get_popover_prefix():
    actions = ["open", "show", "display", "reveal", "activate", "trigger"]
    prepositions = ["", "on", "the"]

    action = random.choice(actions)
    preposition = random.choice(prepositions)

    if preposition:
        return f"{action} {preposition} "
    else:
        return f"{action} "

def get_move_cursor_prefix():
    return random.choice(["move cursor to", "move cursor on", "move cursor to the", "move cursor on the"]) + " "

def get_double_click_prefix():
    return random.choice(["double click", "double click on", "double click the"]) + " "

def get_press_key_prefix():
    return random.choice(["press enter", "press enter key", "press the enter key"]) + " "


ACTION_TYPES = {
    "AXPress":'left click',
    "AXShowMenu":'left click',
    "AXShowAlternateUI":'left click',
    "AXPick":'left click',

    "MoveCursor":"move to",
    "DoubleClick":"double click",
    "PressEnter" : "press enter",

    "AXCancel":'left click',
    "AXRaise" : None,

    "AXConfirm":'left click',
    "AXDecrement":None,
    "AXIncrement":None,
    "AXShowDefaultUI":None,
    'AXScrollDownByPage':'scroll',
    'AXScrollUpByPage':'scroll',
    'AXScrollToVisible':'scroll',
    # _____________________________________________
    # CUSTOM-DEFINED ACTIONS (NOT EXPLICITLY DEFINED IN ACTIONTYPES OF AX LIB)
    'InputTextField':'type',
    "AXToolbar": 'scroll',
    "AXOutline": 'left click',
    'AXValueIndicator':'left click',
    "AXWebArea": 'left click',
    "AXPopUpButton": 'left click',
    "AXLayoutArea": 'left click',
    "AXCell": 'left click',
    "AXRow": 'left click',
    "AXUnknown": 'left click',
    "AXGrid": 'left click',
    "AXTextArea": 'type',
    "AXMenuButton": 'left click',
    "AXDateTimeArea": 'left click',
    "AXRadioGroup": 'left click',
    "AXRadioButton": 'left click',
    "AXList": 'left click',
    "AXBusyIndicator": 'left click',
    "No role": 'left click',
    "AXTable": 'left click',
    "AXColumn": 'left click',
    "AXSheet": 'left click',
    "AXTabGroup": 'left click',
    "AXSplitGroup":'left click',
    "AXIncrementor": 'left click',
}


per_action_str_prefix = {
    "AXCell":get_press_prefix,
    "AXLayoutArea":get_press_prefix,
    "AXPress":get_press_prefix,
    "AXScrollDownByPage":get_scroll_prefix,
    "AXScrollToVisible":get_scroll_prefix,
    "AXTextField":get_input_text,
    "AXTextArea":get_input_text,
    "MoveCursor":get_move_cursor_prefix,
    "DoubleClick":get_double_click_prefix,
    "AXToolbar": get_scroll_prefix,
    "PressEnter": get_press_key_prefix,
    "AXOutline": get_press_prefix,
    'AXValueIndicator': get_press_prefix,
    "AXWebArea": get_press_prefix,
    "AXPopUpButton": get_press_prefix,
    "AXList": get_press_prefix,
    "AXRow": get_press_prefix,
    "AXUnknown": get_press_prefix,
    "AXGrid": get_press_prefix,
    # "AXTextArea": get_press_prefix,
    "AXMenuButton": get_press_prefix,
    "AXDateTimeArea": get_press_prefix,
    "AXRadioGroup": get_press_prefix,
    "AXRadioButton": get_press_prefix,
    "AXBusyIndicator": get_press_prefix,
    "No role": get_press_prefix,
    "AXSplitter": get_press_prefix,
    "AXTable": get_press_prefix,
    "AXColumn": get_press_prefix,
    "AXSheet": get_press_prefix,
    "AXTabGroup": get_press_prefix,
    "AXSplitGroup": get_press_prefix,
    "AXIncrementor": get_press_prefix,
}


per_role_prefix = {
    "AXSplitGroup":get_press_prefix,
    "AXTabGroup":get_press_prefix,
    "AXOutline":get_press_prefix,
    "AXGenericElement":get_press_prefix,
    "AXButton":get_press_prefix,
    "AXCheckBox":get_check_prefix,
    "AXDisclosureTriangle":get_press_prefix,
    "AXScrollBar":get_scroll_prefix,
    "AXSlider":get_scroll_prefix,
    "AXHeading":get_press_prefix,
    "AXTextField":get_input_text,
    "AXStaticText":get_press_prefix,
    "AXImage":get_press_prefix,
    "AXLink":get_press_prefix,
    "AXMenu":get_press_prefix,
    "AXMenuItem":get_press_prefix,
    "AXWindow":get_press_prefix,
    "AXGroup":get_press_prefix,
    "AXScrollArea":get_scroll_prefix,
    "AXPopover":get_popover_prefix,
    "MoveCursor":get_move_cursor_prefix,
    "PressEnter" : get_press_key_prefix,
    "AXSplitter":get_press_prefix,
    "DoubleClick":get_double_click_prefix,
    "AXToolbar": get_scroll_prefix,
    "AXValueIndicator": get_press_prefix,
    "AXWebArea": get_press_prefix,
    "AXPopUpButton": get_press_prefix,
    "AXList": get_press_prefix,
    "AXLayoutArea": get_press_prefix,
    "AXCell": get_press_prefix,
    "AXRow": get_press_prefix,
    "AXUnknown": get_press_prefix,
    "AXGrid": get_press_prefix,
    "AXTextArea": get_input_text,
    "AXMenuButton": get_press_prefix,
    "AXDateTimeArea": get_press_prefix,
    "AXRadioGroup": get_press_prefix,
    "AXRadioButton": get_press_prefix,
    "AXBusyIndicator": get_press_prefix,
    "No role": get_press_prefix,
    "AXTable": get_press_prefix,
    "AXColumn": get_press_prefix,
    "AXSheet": get_press_prefix,
    "AXIncrementor": get_press_prefix,

}


per_element_description = {
    "AXLayoutArea": "layout area",
    'AXValueIndicator': 'value indicator',
    "AXOutline": "outline",
    "AXWebArea": "web area",
    "AXButton": "button",
    "AXCheckBox": "checkbox",
    "AXDisclosureTriangle": "disclosure triangle",
    "AXScrollBar": "scroll bar",
    "AXSlider": "slider",
    "AXGenericElement": "element",
    "AXGroup": "element",
    "AXHeading": "heading",
    "AXImage": "image",
    "AXLink": "link",
    "AXMenu": "menu",
    "AXMenuItem": "menu item",
    "AXStaticText": "text",
    "AXTextField": "text field",
    "AXWindow": "window",
    "AXScrollArea": "scroll area",
    "AXPopover": "popover",
    "MoveCursor":"",
    "PressEnter":"",
    "AXSplitter":"splitter",
    "DoubleClick":"button",
    "AXToolbar":"toolbar",
    "AXPopUpButton":"pop up button",
    "AXList":"list",
    "AXCell":"cell",
    "AXRow":"row",
    "AXUnknown":"element",
    "AXGrid":"grid",
    "AXTextArea":"text area",
    "AXMenuButton":"menu button",
    "AXDateTimeArea":"date time area",
    "AXRadioGroup":"radio group",
    "AXRadioButton":"radio button",
    "No role":"element",
    "AXBusyIndicator":"busy indicator",
    "AXTable":"table",
    "AXColumn":"column",
    "AXSheet"  : "sheet",
    "AXTabGroup":"tab group",
    "AXSplitGroup":"split group",
    "AXIncrementor":"incrementor",
}

ACTION_LIST = [
    'move to',
    'left click',
    'right click',  # not supported
    'double click',
    'drag to',   # not supported
    'scroll',   # not supported
    'type',
    'press',   # not supported
    'key down',   # not supported
    'key up',   # not supported
    'press enter',  # to be changed
    'hotkey'  # not supported
]



class Action:
    def __init__(
        self,
        element: UIElement,
        action_names: list[str],
        is_defined_action: bool = False,
        input = None,
        screenshot_pre_action_path = None,
        screenshot_post_action_path = None,
    ):
        self.element = element
        self.names = action_names
        self.is_defined_action = is_defined_action
        self.input = input
        self.screenshot_pre_action_path = screenshot_pre_action_path
        self.screenshot_post_action_path = screenshot_post_action_path


    def to_dict(self, add_tasks: bool = True):
        if add_tasks:
            self.task_string = self.astask()
            self.representation = self.represent()

            all_names = []
            for name in self.names:
                all_names.append(name)
            return {
                "element": self.element.to_dict(),
                "names": all_names,
                "task_string": self.task_string,
                "represent": self.representation,
                "image_name": self.screenshot_pre_action_path,
                "post_action_image_name": self.screenshot_post_action_path,
            }
        else:
            all_names = []
            for name in self.names:
                all_names.append(name)
            return {
                "element": self.element.to_dict(),
                "names": all_names,
            }
    def represent(self):

        if "PressEnter" in self.names:
            return {'string':ACTION_TYPES["PressEnter"],
                    'position': {'x':self.element.position.x, 'y':self.element.position.y},
                    'size': {'width':self.element.size.width,
                             'heght':self.element.size.height}}

        if "MoveCursor" in self.names:
            return {'string':ACTION_TYPES["MoveCursor"] + f" ({str(self.element.center[0])}, {str(self.element.center[1])})",
                    'position': {'x':self.element.position.x, 'y':self.element.position.y},
                    'size': {'width':self.element.size.width,
                             'heght':self.element.size.height}}

        if self.element.role == "AXTextField":
            part1 =  ACTION_TYPES["AXPress"] + f" ({str(self.element.center[0])}, {str(self.element.center[1])})"
            part2 = ACTION_TYPES["InputTextField"] + f" '{self.input}'"
            return {'string' : part1 + " ; " + part2,
                    'position' : {'x':self.element.position.x, 'y':self.element.position.y},
                    'size': {'width':self.element.size.width,
                             'heght':self.element.size.height}}

        else:
            if "AXPress" in self.names or "AXShowMenu" in self.names:
                repr = ACTION_TYPES["AXPress"]+ f" ({str(self.element.center[0])}, {str(self.element.center[1])})"
                return {'string':repr,
                        'position': {'x':self.element.position.x, 'y':self.element.position.y},
                        'size': {'width':self.element.size.width,
                                 'height':self.element.size.height}}

    def astask(self):

        # Removing the elements with empty names
        if ((self.element.value is None or len(str(self.element.value)) == 0)
                and (self.element.role_description is None or len(self.element.role_description) == 0)
                and (self.element.description is None or len(self.element.description) == 0 or "None" in self.element.description)
                and (self.element.name is None or len(self.element.name) == 0 or "empty-name-" in self.element.name)
        ) :
            return None

        if self.element.role not in per_role_prefix:
            print(f"Role {self.element.role} not found in per_role_prefix")
            return f"Click on {self.element.role} with name: '{self.element.name}', description: '{self.element.description}' and value: '{self.element.value}'"

        # TODO: change here!
        if "MoveCursor" in self.names:
            prefix = per_action_str_prefix["MoveCursor"]()
        elif "DoubleClick" in self.names:
            prefix = per_action_str_prefix["DoubleClick"]()
        elif "PressEnter" in self.names:
            prefix = per_action_str_prefix["PressEnter"]()
            return prefix
        elif self.element.role in ["AXTextField", "AXTextArea"]:
            prefix = per_action_str_prefix[self.element.role](self.input)
        else:
            prefix = per_role_prefix[self.element.role]()

        naming = per_element_description[self.element.role]

        task_string = prefix + naming

        if self.element.value is not None and len(str(self.element.value)) > 0:
            value = str(self.element.value)
            task_string += " with value: '" + value + "'"

        description = ''
        name = ''
        if self.element.description is not None or len(str(self.element.description)) > 0 and str(self.element.description) != "None":
            description = str(self.element.description)
        elif self.element.role_description is not None or len(str(self.element.role_description)) > 0:
            description = str(self.element.role_description)

        if self.element.name is not None or len(str(self.element.name)) > 0 or "empty" in self.element.name :
            name = str(self.element.name)
        if task_string[-1] == "'" and len(description) > 0:
            task_string += " and description: '" + description + "'"
        else:
            if len(description) > 0:
                task_string += " with description: '" + description + "'"
            if len(name) > 0 and "empty" not in name:
                task_string += " with name: '" + name + "'"

        return task_string


class Vertice:
    def __init__(
        self,
        element: UIElement,
        image_name: str,
        actions: list[Action] = [],
        should_be_dismissed: bool = False,
        window_coors_scaled: tuple[int, int, int, int] = None,
        clicking_order: list = [],
        add_tasks: bool = True,
    ):
        self.element = element
        self.edges = []
        self.image_name = image_name
        self.should_be_dismissed = should_be_dismissed
        if actions is not None:
            self.actions = actions
        if window_coors_scaled is not None:
            self.window_coors_scaled = window_coors_scaled
        self.clicking_order = clicking_order
        self.add_tasks = add_tasks
        self.executed_actions = []

    def add_child_node(self, action: Action, child_node: Self):
        edge = Edge(action, self, child_node, image_name=action.screenshot_pre_action_path)
        self.add_edge(edge)

    def add_edge(self, edge):
        self.edges.append(edge)

    def to_dict(self):
        # actions
        all_actions = []
        for action in self.executed_actions:
            all_actions.append(action.to_dict(self.add_tasks))

        # edges
        all_edge = []
        for edge in self.edges:
            all_edge.append(edge.to_dict(add_tasks=self.add_tasks))

        return {
            "element": self.element.to_dict(),
            "image_name": self.image_name,
            "actions": all_actions,
            "edges": all_edge,
        }


class Edge:
    def __init__(self, action: Action, in_vertice: Vertice, out_vertice: Vertice, image_name: str = None):
        self.action = action
        self.image_name = image_name
        self.in_vertice = in_vertice
        self.out_vertice = out_vertice

    def to_dict(self, add_tasks: bool = True):
        return {
            "action": self.action.to_dict(add_tasks),
            "out_vertice": self.out_vertice.to_dict(),
        }
