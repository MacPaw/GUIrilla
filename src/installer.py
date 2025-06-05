import argparse
import os
import helpers.applications as applications
import time

from helpers import applications
from helpers.applications import App, AppDescriptionDetails


# install application from the Mac App Store
def install_mas_app(app: App) -> bool | None:
    print(
        f"🛠️️  MAS: Installing {app.name}, bundle: {app.bundle_id}, version {app.version} from MAS"
    )

    # if is_os_version_supported(app):
    #     print(f"🔍 OS version supported for app {app.name}")
    # else:
    #     print(f"❌ OS version not supported for app {app.name}")
    #     return

    if app.is_free():
        print(f"🆓 MAS: App {app.bundle_id} is free")
        # perform terminal command: mas purchase <app.store_id>
        result = os.popen(f"{mas_cli_path} purchase {app.store_id}").read()
        if result.startswith("No downloads"):
            print(f"❌ MAS: Failed to install app {app.bundle_id}, storeID: {app.store_id}. Error: {result}")
            return False
        else:
            print(f"✅ MAS: App {app.bundle_id} installed")
            return applications.installed_app_url(app)
    else:
        print(
            f"⏭️ MAS: Skipping app installation from MAS, app {app.bundle_id} is not free"
        )
        return None


def install_cask_app(app: App) -> bool | None:
    print(
        f"🛠️️  Cask: Installing {app.name}, identifier: {app.store_id}, version {app.version} from Cask"
    )
    if app.is_free():
        print(f"🆓 Cask: App {app.store_id} is free")
        
        # perform terminal command: brew install --cask <app.bundle_id>
        result = os.system(f"brew install --cask --no-quarantine {app.store_id}")
        if result == 0:
            print(f"✅ Cask: App {app.store_id} installed")
            if app.bundle_id == "":
                app.bundle_id = read_bundle_id(app)
            removed_from_quarantine = _remove_app_from_quarantine(app)
            if removed_from_quarantine:
                print(f"✅ Cask: App {app.store_id} removed from quarantine")
            else:
                print(f"❌ Cask: Failed to remove app {app.store_id} from quarantine")
            return removed_from_quarantine
        else:
            print(f"❌ Cask: Failed to install app {app.store_id}. Error: {result}")
            return False
    else:
        print(
            f"⏭️ Cask: Skipping app installation from Cask, app {app.store_id} is not free"
        )
        return None


# check if app version is supported by the OS
def is_os_version_supported(app: App) -> bool:
    print(f"🔍 Checking OS version for app {app.name}")
    if app.minimum_os_version == "Unknown" or not app.minimum_os_version:
        print(f"⚠️ Minimum OS version unknown for app {app.name}, proceeding with installation")
        return True
        
    try:
        os_version = applications.current_os_version()
        print(f"🔍 Current OS version: {os_version}, supported app version: {app.minimum_os_version}")
        
        # Split version strings into components and compare numerically
        os_parts = [int(x) for x in os_version.split('.')]
        min_parts = [int(x) for x in app.minimum_os_version.split('.')]
        
        # Compare each component
        for i in range(max(len(os_parts), len(min_parts))):
            os_part = os_parts[i] if i < len(os_parts) else 0
            min_part = min_parts[i] if i < len(min_parts) else 0
            if os_part > min_part:
                return True
            elif os_part < min_part:
                return False
        return True  # All parts equal
        
    except (ValueError, IndexError) as e:
        print(f"❌ Error comparing OS versions: {e}")
        return False


# check if app is installed and analyse or install
def process_app(app: App):
    print(f"🛠  Processing {app.name}, bundle: {app.bundle_id}, version {app.version}")
    installed_app_url = applications.installed_app_url(app)
    if installed_app_url is not None and len(installed_app_url) > 0:  # app is installed
        print(f"✅ App {app.name} is installed")
    else:
        print(
            f"❌ Failed to install {app.name}, bundle: {app.bundle_id}, version {app.version}"
        )


# fetch application info
def fetch_app_info_mas(app_details: AppDescriptionDetails) -> App | None:
    print(f'🛠  Processing app details: {app_details}')

    app: App | None = None
    if app_details.bundle != "":
        print(f"🔄 iTunes API: Fetching app info for bundle: {app_details.bundle}")
        app = applications.get_app_info_mas_by_bundle_id(app_details.bundle)
    elif app_details.identifier != "":
        print(f"🔄 iTunes API: Fetching app info for store id: {app_details.identifier}")
        app = applications.get_app_info_mas_by_store_id(app_details.identifier)
    else:
        print(f"❌ Failed to fetch app info for app details: {app_details}")
        return None

    installed_app_url = applications.installed_app_url(app)
    if installed_app_url is None or installed_app_url == "":
        print(f"📵 App {app.bundle_id} is not installed")

        if app is None:
            print(f"❌ iTunes API: Failed to fetch app info for bundle: {app_details.bundle}, store id: {app_details.identifier}")
        else:
            print(f"✅ iTunes API: App info fetched for bundle: {app.bundle_id}, store id: {app.store_id}")
    else:
        print(f"✅ App {app.bundle_id.upper()} is already installed")
        app_name = installed_app_url.split("/")[-1].replace(".app", "")
        app = App(app_name, "Unknown", "Unknown", app_details.bundle, "Unknown", "Unknown", 0)
    return app


def fetch_app_info_cask(app_identifier: str) -> App | None:
    print(f"🔄 Cask: Fetching app info for identifier: {app_identifier}")
    app = applications.get_app_info_cask(app_identifier)
    if app is None:
        print(f"❌ Cask: Failed to fetch app info for identifier: {app_identifier}")
    else:
        print(f"✅ Cask: App info fetched for identifier: {app_identifier}")
    return app


def _remove_app_from_quarantine(app: App) -> bool:
    if app.bundle_id != "":
        if app.bundle_id == "cask":
            aliases = applications.search_app_aliases(app)
            for alias in aliases:
                result = os.popen(f'xattr -cr {alias}').read()
                if result == "":
                    print(f"✅ App {app.name} removed from quarantine")
                    return True
                else:
                    print(f"❌ Failed to remove app from quarantine, error: {result}")
                    return False
        else:
            print(f"🔑 No need to remove app from quarantine")
    else:
        print(f"❌ Failed to remove app from quarantine, app bundle id is empty")
        return False


def _grant_permissions(app: App):
    if app is None:
        print(f"❌ Failed to grant permissions, app is None")
        return
    print(f"🔑 Granting permissions for {app.bundle_id}")
    app_path = applications.installed_app_url(app)

    if app_path is None:
        print(f"❌ Failed to grant permissions, app path is None")
        return
    # Launch script with sudo to grant permissions
    with open('config_system_pass.env', 'r') as file:
        sudo_password = file.read().strip()
    script_path = "src/tcc_updater.py"
    cmd = f"echo {sudo_password} | sudo -S python3 {script_path} -b {app.bundle_id} -p {app_path} --add"
    os.system(cmd)
    

def read_bundle_id(app: App) -> str:
    if app is not None and app.bundle_id != "":
        return app.bundle_id
    else:
        aliases = applications.search_app_aliases(app)
        for alias in aliases:
            path = os.path.abspath(alias)
            
            plist = applications.read_app_plist(path)
            if "CFBundleIdentifier" in plist:
                return plist["CFBundleIdentifier"]
            else:
                print(f"❌ Failed to read bundle id for app {app.name}")
    return ""

if __name__ == "__main__":
    # create the parser
    arg_parser = argparse.ArgumentParser(
        description="Parse -a <app_details>, -m <mas-cli path>"
    )

    # add the arguments
    arg_parser.add_argument("-a", type=str, help="App details")
    arg_parser.add_argument("-m", type=str, help="mas-cli path")

    # parse the arguments
    args = arg_parser.parse_args()

    # get the arguments
    app_details = args.a
    mas_cli_path = args.m

    # app_details = "Colouring Your - ZOO,com.mezz.sketch.fbz.mac,1090511041,mas"
    # mas_cli_path = "/Users/ivan/Downloads/mas-main/.build/arm64-apple-macosx/release/mas"

    print("app_details: ", app_details)
    print("mas_cli_path: ", mas_cli_path)

    # Get the application details and create app object
    details = applications.get_app_details(app_details)
    if details.source == "mas":
        app = fetch_app_info_mas(details)
        installed_app_url = install_mas_app(app)
        _grant_permissions(app)
        if app is not None and installed_app_url is not None:
            process_app(app)
    elif details.source == "mu":
        app = applications.get_app_info_mu(details.identifier)
        
        _grant_permissions(app)
    elif details.source == "cask":
        app = fetch_app_info_cask(details.identifier)
        app_installed = install_cask_app(app)
        
        _grant_permissions(app)
    elif details.source == "os":
        print("🔄 Skipping app installation for pre-installed app")

    print("✅ Done installing apps")
