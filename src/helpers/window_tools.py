import AppKit
import ApplicationServices
import shutil
import os
import subprocess
import helpers.uielement as uielement

import time
import threading
from PIL import Image, ImageDraw
from time import sleep
import helpers.files as files
from helpers.uielement import UIElement

_screen_scaling_factor = 1

# get the screen scaling factor
def store_screen_scaling_factor():
    for screen in AppKit.NSScreen.screens():
        global _screen_scaling_factor
        _screen_scaling_factor = screen.backingScaleFactor()
        print(f"Screen scaling factor: {_screen_scaling_factor}")

# get color for the role
def color_for_role(role):
    color = "red"
    if role == "AXButton":
        color = "blue"
    elif role == "AXTextField":
        color = "green"
    elif role == "AXStaticText":
        color = "yellow"
    elif role == "AXImage":
        color = "purple"
    elif role == "AXGroup":
        color = "orange"
    elif role == "AXScrollBar":
        color = "brown"
    elif role == "AXRow":
        color = "pink"
    elif role == "AXColumn":
        color = "cyan"
    elif role == "AXCell":
        color = "magenta"
    elif role == "AXTable":
        color = "lightblue"
    elif role == "AXOutline":
        color = "lightgreen"
    elif role == "AXLayoutArea":
        color = "lightyellow"
    elif role == "AXLayoutItem":
        color = "lavender"
    elif role == "AXHandle":
        color = "peachpuff"
    elif role == "AXSplitter":
        color = "lightsalmon"
    elif role == "AXIncrementor":
        color = "lightpink"
    elif role == "AXBusyIndicator":
        color = "lightcyan"
    elif role == "AXProgressIndicator":
        color = "plum"
    elif role == "AXToolbar":
        color = "darkred"
    elif role == "AXPopover":
        color = "darkblue"
    elif role == "AXMenu":
        color = "darkgreen"
    elif role == "AXMenuItem":
        color = "olive"
    elif role == "AXMenuBar":
        color = "rebeccapurple"
    elif role == "AXMenuBarItem":
        color = "darkorange"
    elif role == "AXMenuButton":
        color = "saddlebrown"
    elif role == "AXMenuItemCheckbox":
        color = "palevioletred"
    elif role == "AXMenuItemRadio":
        color = "darkcyan"
    elif role == "AXMenuItemPopover":
        color = "darkmagenta"
    elif role == "AXMenuItemSplitter":
        color = "black"
    elif role == "AXMenuItemTable":
        color = "white"
    elif role == "AXMenuItemTextField":
        color = "lightgray"
    elif role == "AXMenuItemStaticText":
        color = "darkgray"
    elif role == "AXMenuItemImage":
        color = "salmon"
    elif role == "AXMenuItemGroup":
        color = "lightblue"
    elif role == "AXMenuItemScrollBar":
        color = "lightgreen"
    elif role == "AXMenuItemRow":
        color = "lightyellow"
    elif role == "AXMenuItemColumn":
        color = "lavender"
    elif role == "AXMenuItemCell":
        color = "peachpuff"
    elif role == "AXMenuItemOutline":
        color = "burlywood"
    elif role == "AXMenuItemLayoutArea":
        color = "lightpink"
    elif role == "AXMenuItemLayoutItem":
        color = "lightcyan"
    elif role == "AXMenuItemHandle":
        color = "plum"
    elif role == "AXMenuItemSplitter":
        color = "darkred"
    elif role == "AXMenuItemIncrementor":
        color = "darkblue"
    elif role == "AXMenuItemBusyIndicator":
        color = "darkgreen"
    elif role == "AXMenuItemProgressIndicator":
        color = "darkyellow"
    elif role == "AXMenuItemToolbar":
        color = "rebeccapurple"
    elif role == "AXMenuItemPopover":
        color = "darkorange"
    return color


# convert point from screen coordinates to window coordinates
def convert_point_to_window(point, window_element):
    for screen in AppKit.NSScreen.screens():
        if AppKit.NSPointInRect(point, screen.frame()):
            screen_height = screen.frame().size.height
            return AppKit.NSMakePoint(
                point.x + window_element.x,
                point.y - 1 + window_element.y,
            )
    return AppKit.NSMakePoint(0.0, 0.0)


# perform a hit test on the specified point
def hit_test(point, window_element):
    window_point = convert_point_to_window(point, window_element.position)
    system_component = ApplicationServices.AXUIElementCreateSystemWide()
    err, value = ApplicationServices.AXUIElementCopyElementAtPosition(
        system_component, window_point.x, window_point.y, None
    )
    if err == ApplicationServices.kAXErrorSuccess:
        return value
    return None


# extract the window
def extract_window(
    window, app_bundle, output_folder, perform_hit_test, print_nodes
) -> bool:
    if window is None:
        return
    window_offset_x = window.position.x
    window_offset_y = window.position.y

    # print the node with its children and attributes
    if perform_hit_test:
        print("Parsing window using hit test")
        point = AppKit.NSMakePoint(window_offset_x + 50, window_offset_y + 50)
        group_element = hit_test(point, window)

        if group_element is None:
            print("Hit test failed")
            return

        # find the root window
        found_root_element = UIElement.find_root_element(group_element)
        root_element = UIElement(found_root_element, window_offset_x, window_offset_y)
        parent_window = uielement.element_attribute(
            found_root_element, ApplicationServices.kAXWindowAttribute
        )
        if parent_window is not None:
            parent_window_element = UIElement(
                parent_window, window_offset_x, window_offset_y
            )

            if windows_are_equal(window, parent_window_element):
                element_not_found = True
                for child in window.children:
                    if (
                        child.identifier == root_element.identifier
                        and child.content_identifier == root_element.content_identifier
                    ):
                        element_not_found = False
                if element_not_found:
                    window.children.append(root_element)
                    window.calculate_hashes()
        else:
            window.children.append(root_element)
            window.calculate_hashes()

        # print the node with its children and attributes
        if print_nodes:
            uielement.print_node(root_element)

        output_file = os.path.join(output_folder, f"{app_bundle}.json")
        files.store_data_to_file(window, output_file)
    else:
        print("Parsing regular window structure")

        return True

# bring the window to the front
def bring_window_to_front(app_bundle):
    print(f"Bringing window to front: {app_bundle}")
    subprocess.run(["osascript", "-e", f'tell app id "{app_bundle}" to activate'])

def timed_window_bring_to_front(app_bundle, timeout=2):
    # Create a flag to track if the operation completed
    operation_completed = threading.Event()

    # Create a thread to run the window bring to front operation
    def run_operation():
        try:
            bring_window_to_front(app_bundle)
            operation_completed.set()
        except Exception as e:
            print(f"Error bringing window to front: {e}")

    # Start the thread
    operation_thread = threading.Thread(target=run_operation)
    operation_thread.start()

    # Wait for the operation to complete or timeout
    if not operation_completed.wait(timeout):
        # print(f"Window bring to front took longer than {timeout} seconds")
        # Execute alternative command here
        return False
    # Ensure the thread is cleaned up
    operation_thread.join()
    return True






# check if the window exists
def is_window_exists(node, window):
    while True:
        if node is None:
            return None
        if (
            node.element.identifier == window.identifier
            and node.element.content_identifier == window.content_identifier
        ):
            return node
        if len(node.edges) == 0:
            return None
        for edge in node.edges:
            if is_window_exists(edge.out_vertice, window):
                return True
        return None


# check if the windows are equal
def windows_are_equal(window1, window2):
    if (
        window1.name == window2.name
        and window1.role == window2.role
        and window1.position == window2.position
        and window1.size == window2.size
    ):
        return True
    return False


# segment the window components
def segment_window_components(window, image_path: str):
    print(f"Segmenting window {window.name}")
    segment_image_path = None

    if image_path is None or len(image_path) == 0:
        print(f"Image for window {window.name} not found")
        return

    print(f"Window name: {image_path}")

    # copy the image for segmentation using new path
    segment_image_path = image_path.replace(".png", "_segmented.png")

    # copy the image for segmentation
    shutil.copy2(image_path, segment_image_path)

    sleep(0.5)

    # segment the image
    segment_image(segment_image_path, window)

    sleep(0.5)


# paint all children to a different color on the screenshot
def segment_image(image_path, window_element, image_drawer=None, image=None):
    if image_path is None:
        return

    # open the image and create a drawer
    draw = image_drawer
    image = image

    # validate the image and drawer
    if image_drawer is None:
        # draw a rectangle on the image
        image = Image.open(image_path)
        draw = ImageDraw.Draw(image)

    # iterate over all children
    for child in window_element.children:
        bbox = child.visible_bbox

        if bbox is None:
            continue

        # position = child.position
        size = child.size

        if size is None:
            continue

        # skip the element if it has no size
        if size.width == 0 or size.height == 0:
            continue

        height_offset = 2
        if size.height < 2:
            height_offset = 0

        retina_position = (bbox[0] * _screen_scaling_factor, (bbox[1] * _screen_scaling_factor))

        # update the bottom right coordinate to support retina displays
        bottom_right = (
            (bbox[2] * _screen_scaling_factor) - 1,
            ((bbox[3]) * _screen_scaling_factor) - height_offset + 1,
        )

        color = color_for_role(child.role)

        if bottom_right[0] < 0 or bottom_right[0] < retina_position[0]:
            bottom_right = (retina_position[0], bottom_right[1])
        if bottom_right[1] < 0 or bottom_right[1] < retina_position[1]:
            bottom_right = (bottom_right[0], retina_position[1])

        try:
            # draw a rectangle with a colored border
            draw.rectangle([retina_position, bottom_right], outline=color, width=2)
        except Exception as e:
            print(f"Error drawing rectangle: {e}")
        segment_image(image_path, child, image_drawer=draw, image=image)
    if image_drawer is None:
        # save the image
        print(f"Saving segmented image to {image_path}")
        image.save(image_path)
