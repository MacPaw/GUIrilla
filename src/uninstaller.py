import os
import argparse
from helpers.applications import get_app_details
from helpers.applications import AppDescriptionDetails
from helpers.applications import installed_app_url
from helpers.applications import app_for_description_details

def remove_app_from_completed_app_details(app_details: AppDescriptionDetails, app_details_string: str, mas_tool: str):
    if app_details is None:
        print(f"❌ Failed to remove app from completed app details, app details is None")
        return
    if app_details.source == "cask":
        result = os.system(f"brew uninstall --cask {app_details.identifier}")
        if result == 0:
            print(f"✅ Cask: App {app_details.identifier} uninstalled")
        else:
            print(f"❌ Cask: Failed to uninstall app {app_details.identifier}. Error: {result}")
    elif app_details.source == "mas":
        # Launch script with sudo to grant permissions
        with open('config_system_pass.env', 'r') as file:
            sudo_password = file.read().strip()
        
        try:
            cmd = f"echo {sudo_password} | sudo -S {mas_tool} uninstall {app_details.identifier}"
            result = os.system(cmd)
            if result == 0:
                print(f"✅ MAS: App {app_details.identifier} uninstalled")
            else:
                print(f"❌ MAS: Failed to uninstall app {app_details.identifier}. Error: {result}")
        except Exception as e:
            print(f"❌ MAS: Failed to uninstall app {app_details.identifier}. Error: {e}")
        # remove the app from the system
        app = app_for_description_details(app_details_string)
        url = installed_app_url(app)
        if url is not None:
            print(f"🔍 Removing app {app_details.identifier} from system, url: {url}")
            cmd = f"echo {sudo_password} | sudo -S rm -rf '{url}'"
            os.system(cmd)
            print(f"✅ App {app_details.identifier} uninstalled")
        else:
            print(f"❌ App {app_details.identifier} not found")
    
    # remove the app from the system
    app = app_for_description_details(app_details_string)
    if app.source == "cask" or app.source == "brew" or app.source == "mas":
        url = installed_app_url(app)
        if url is not None:
            print(f"🔍 Removing app {app_details.identifier} from system, url: {url}")
            cmd = f"echo {sudo_password} | sudo -S rm -rf '{url}'"
            os.system(cmd)
            print(f"✅ App {app_details.identifier} uninstalled")
    else:
        print(f"❌ App {app_details.identifier} not found")


if __name__ == "__main__":
    # create the parser
    arg_parser = argparse.ArgumentParser(
        description="Parse -a <app_details> -m <mas_tool>"
    )

    # add the arguments
    arg_parser.add_argument("-a", type=str, help="App details")
    arg_parser.add_argument("-m", type=str, help="MAS tool")

    # parse the arguments
    args = arg_parser.parse_args()

    # get the arguments
    app_details = args.a
    mas_tool = args.m
    print("app_details: ", app_details)

    details = get_app_details(app_details)
    remove_app_from_completed_app_details(details, app_details, mas_tool)