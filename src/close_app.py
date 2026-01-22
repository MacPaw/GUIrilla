import argparse
import subprocess
import AppKit
import os

from helpers.applications import App
from helpers import applications


# check if application is running
def check_app_running(bundle_id):
    workspace = AppKit.NSWorkspace.sharedWorkspace()
    for app in workspace.runningApplications():
        if app.bundleIdentifier() == bundle_id:
            return True
    return False



# kill the app using app bundle
def kill_app(app: App):
    try:
        subprocess.check_call(["osascript", "-e", f'quit app id "{app.bundle_id}"'])
        print("Application was killed")
    except subprocess.CalledProcessError as e:
        print(f"Failed to kill app with bundle id {app.bundle_id}. Error: {e}")
        result = os.system(f'killall "{app.name}"')
        if result == 0:
            print("Application was killed")
        else:
            print(f"Failed to kill app with bundle id {app.bundle_id}. Error: {result}")

if __name__ == "__main__":
    # Create the parser
    arg_parser = argparse.ArgumentParser(description="Parse -a argument")

    # Add the arguments
    arg_parser.add_argument("-a", type=str, help="The application bundle identifier")

    # Parse the arguments
    args = arg_parser.parse_args()

    # Get the arguments
    app_details = args.a

    # Get the application details and create app object
    app = applications.app_for_description_details(app_details)

    # Check if the arguments are provided
    if app.bundle_id:
        print(f"Closing application: {app.bundle_id}")
    else:
        print(
            "Application bundle is not specified, processing all the running applications"
        )

    workspace = AppKit.NSWorkspace.sharedWorkspace()
    # Check if the application is running
    if check_app_running(app.bundle_id):
        print("Application is running")
        kill_app(app)
    else:
        print("Application is not running")

    applications.cleanup_environment()