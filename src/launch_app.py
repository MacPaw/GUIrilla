import argparse
import subprocess
import AppKit

from helpers import applications
from time import sleep


# check if application is running
def check_app_running(workspace, app_bundle):
    for app in workspace.runningApplications():
        if app.bundleIdentifier() == app_bundle:
            return True
    return False


# launch the application
def launch_app(bundle_id):
    print(f"Launching app with bundle id: {bundle_id}")
    try:
        subprocess.check_call(["open", "-b", bundle_id])
        sleep(3)
    except subprocess.CalledProcessError as e:
        print(f"Failed to launch app with bundle id {bundle_id}. Error: {e}")
        print("Attempt to launch again")
        subprocess.run(f'open -b {bundle_id}', shell=True)
        sleep(5)
    applications.hide_all_apps_apple_script(app.name)
        

if __name__ == "__main__":
    # Create the parser
    arg_parser = argparse.ArgumentParser(description="Parse -a argument")

    # Add the arguments
    arg_parser.add_argument("-a", type=str, help="The application details")

    # Parse the arguments
    args = arg_parser.parse_args()

    # Get the arguments
    app_details = args.a
    print(f'App details: {app_details}')

    # Get the application details and create app object
    app = applications.app_for_description_details(app_details)
    
    print(f"Launching App: {app.name}")
    # Check if the arguments are provided
    if app.bundle_id:
        print(f"Processing application: {app.bundle_id}")
    else:
        print("Application bundle is not specified, processing all the running applications")

    applications.cleanup_environment()
    
    sleep(0.3)

    workspace = AppKit.NSWorkspace.sharedWorkspace()
    # Check if the application is running
    if not check_app_running(workspace, app.bundle_id):
        print("Application is not running")
        launch_app(app.bundle_id)
