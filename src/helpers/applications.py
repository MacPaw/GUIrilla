import ApplicationServices
import AppKit
import os
import requests
import helpers.uielement as uielement
import plistlib
import glob
import subprocess

from typing import List

class App:
    def __init__(
        self,
        name: str,
        version: str,
        store_id: str,
        bundle_id: str,
        genre_id: str,
        minimum_os_version: str,
        price: float = 0,
        source: str = None,
    ):
        self.name = name
        self.version = version
        self.store_id = store_id
        self.bundle_id = bundle_id
        self.genre_id = genre_id
        self.minimum_os_version = minimum_os_version
        self.price = price
        self.deep_link_url_schemes = []
        self.action_script_files = []
        self.source = source

    def is_free(self) -> bool:
        return self.price == 0


class AppDescriptionDetails:
    def __init__(self, name, bundle, identifier, source):
        self.name = name
        self.bundle = bundle
        self.identifier = identifier
        self.source = source


# get application for bundle identifier
def application_for_process_id(pid):
    return ApplicationServices.AXUIElementCreateApplication(pid)


# get windows for application
def windows_for_application(app):
    err, value = ApplicationServices.AXUIElementCopyAttributeValue(
        app, ApplicationServices.kAXWindowsAttribute, None
    )
    if err != ApplicationServices.kAXErrorSuccess:
        if err == ApplicationServices.kAXErrorNotImplemented:
            print("Attribute not implemented")
        else:
            print("Error retrieving attribute")
        return []
    return uielement.CFAttributeToPyObject(value)


# get dialog windows for application
def dialog_windows_for_application(app) -> list:
    windows = windows_for_application(app)
    dialog_windows = []
    for window in windows:
        identifier = uielement.element_attribute(
            window, ApplicationServices.kAXIdentifierAttribute
        )
        if identifier == "open-panel" or identifier == "save-panel":
            dialog_windows.append(window)
    return dialog_windows


def get_app_details(app_details: str) -> AppDescriptionDetails:
    details = parse_app_details(app_details)
    return AppDescriptionDetails(
        name=details[0], bundle=details[1], identifier=details[2], source=details[3]
    )


def app_for_description_details(app_details: str) -> App | None:
    details = get_app_details(app_details)
    if details.source == "mas":
        if details.bundle is not None and details.bundle != "": 
            return get_app_info_mas_by_bundle_id(app_bundle=details.bundle)
        elif details.identifier is not None and details.identifier != "":
            return get_app_info_mas_by_store_id(app_store_id=details.identifier)
    elif details.source == "mu":
        return get_app_info_mu(details.identifier)
    elif details.source == "cask":
        return get_app_info_cask(details.identifier)
    elif details.source == "os":
        return get_app_info_os(details.bundle)


def parse_app_details(app_details: str) -> str:
    return app_details.strip().replace("\n", "").split(",")


# check if app installed by the app name
def is_app_installed(app_name: str) -> bool:
    print(f"🔍 Looking for installed app with name: {app_name}")
    apps = AppKit.NSWorkspace.sharedWorkspace().runningApplications()
    for app in apps:
        if app_name in app.localizedName():
            print(f"✅ Installed app found with name: {app_name}")
            return True
    print(f"❌ Installed app not found with name: {app_name}")
    return False

def search_app_aliases(app: App) -> List[str]:
    arm_path = "/opt/homebrew/Caskroom"
    x86_path = "/usr/local/Caskroom"

    if os.path.exists(arm_path):
        caskroom_path = os.path.join(arm_path, app.store_id)
    elif os.path.exists(x86_path):
        caskroom_path = os.path.join(x86_path, app.store_id)
    else:
        print(f"❌ Failed to find caskroom path for app identifier: {app.store_id}")
        return []

    print(f"🔍 Searching for *.app aliases in {caskroom_path}")

    if not os.path.exists(caskroom_path):
        print(f"❌ The path {caskroom_path} does not exist.")
        return []

    if not os.path.isdir(caskroom_path):
        print(f"❌ The path {caskroom_path} is not a directory.")
        return []

    # Pattern to match all .app directories
    pattern = os.path.join(caskroom_path, app.version, "*.app")
    app_paths = glob.glob(pattern)
    
    app_aliases = []
    for app_path in app_paths:
        if os.path.islink(app_path):
            target_path = os.readlink(app_path)
            print(f"🔗 Found alias: {app_path} -> {target_path}")
            app_aliases.append(app_path)
            app_aliases.append(target_path)
        elif os.path.isdir(app_path):
            print(f"🏢 Found actual app bundle: {app_path}")
            app_aliases.append(app_path)
        else:
            print(f"❓ Unknown item type: {app_path}")

    if not app_aliases:
        print(f"❌ No *.app aliases found in {caskroom_path}")
    else:
        print(f"✅ Found {len(app_aliases)} '*.app' aliases/directories.")
    return app_aliases


# get application for bundle identifier
def installed_app_url(app: App) -> str | None:
    print(f"🔍 Looking for installed app with bundle id: {app.bundle_id}")
    urls = os.popen(f'mdfind kMDItemCFBundleIdentifier = "{app.bundle_id}"').read()
    urls = urls.split("\n")
    url = urls[0].replace("\n", "")
    if url == "" or url is None:
        if app.source == "cask":
            aliases = search_app_aliases(app)
            for alias in aliases:
                if os.path.exists(alias):
                    print(f"✅ Installed app path: {alias}")
                    return alias
        print(f"❌ Installed app not found with bundle id: {app.bundle_id}")
        return None 
    
    print(f"✅ Installed app path: {url}")
    try:
        file_path = str(url.path())
    except:
        file_path = url
    return file_path


# fetch application info from MAS
def get_app_info_mas_by_bundle_id(app_bundle: str) -> App | None:
    url = f"https://itunes.apple.com/lookup?bundleId={app_bundle}"
    response = requests.get(url, timeout=5)
    try:
        response_json = response.json()
        return _json_to_app(response_json)
    except:
        print(f"❌ MAS: Failed to fetch app info for bundle: {app_bundle}")
    return None
    


def get_app_info_mas_by_store_id(app_store_id: str) -> App | None:
    url = f"https://itunes.apple.com/lookup?id={app_store_id}"
    response = requests.get(url, timeout=5)
    try:
        response_json = response.json()
        return _json_to_app(response_json)
    except:
        print(f"❌ MAS: Failed to fetch app info for store id: {app_store_id}")
    return None

def _json_to_app(response_json: dict) -> App | None:
    result = response_json["results"]
    if len(result) == 0:
        return None
    result = result[0]
    name = result["trackName"]
    version = result["version"]
    store_id = result["trackId"]
    bundle_id = result["bundleId"]
    genre_id = result["primaryGenreId"]
    minimum_os_version = result["minimumOsVersion"]

    price = 0
    if "price" in result:
        price = result["price"]
    return App(
        name, version, store_id, bundle_id, genre_id, minimum_os_version, price, "MAS"
    )


def get_app_info_mu(app_bundle: str) -> App | None:
    return None


def read_app_plist(app_path: str) -> dict:
    plist_path = os.path.join(app_path, "Contents", "Info.plist")
    try:
        with open(plist_path, "rb") as f:
            return plistlib.load(f)
    except Exception as e:
        print(f"❌ Failed to read plist file {plist_path}. Error: {e}")
        return {}


def get_app_info_cask(app_identifier: str) -> App | None:
    response = os.popen(f'brew info --cask "{app_identifier}"').read()
    if len(response) == 0:
        print(f"❌ Cask: Failed to get app info {app_identifier}. Error: {result}")
    else:
        app = App(
            name="",
            version="",
            store_id=app_identifier,
            bundle_id="",
            genre_id="",
            minimum_os_version="",
            price=0,
            source="Cask",
        )

        result = response.split("==>")
        for item in result:
            item = item.strip()
            if item.startswith(app_identifier):
                app_version = item.split(" ")[1]
                app_version = app_version.split("\n")[0]
                app.version = app_version
                if "Not installed" in item:
                    print(f"❌ Cask: App {app_identifier} is not installed")
                else:
                    app.minimum_os_version = current_os_version()
            elif item.startswith("Name"):
                app.name = item.removeprefix("Name\n")
            elif item.startswith("Artifacts"):
                full_app_name = item.removeprefix("Artifacts\n")
                app_name = full_app_name.split(".app")[0] + ".app"
                app_path = f"/Applications/{app_name}"

                if os.path.exists(app_path):
                    plist = read_app_plist(app_path)
                    app.bundle_id = plist.get("CFBundleIdentifier", "")
                else:
                    print(f"❌ Cask: App {app_identifier} is not installed")
                    app.bundle_id = app_identifier
                    app_path = installed_app_url(app)
                    if app_path is not None:
                        plist = read_app_plist(app_path)
                        app.bundle_id = plist.get("CFBundleIdentifier", "")
        return app
    return None


def get_app_info_os(app_identifier: str) -> App | None:
    app = App(
        name="",
        version="",
        store_id="",
        bundle_id=app_identifier,
        genre_id="",
        minimum_os_version="",
        price=0,
        source="OS",
    )
    app_path = installed_app_url(app)
    if app_path is not None:
        plist = read_app_plist(app_path)
        app.name = plist.get("CFBundleName", "")
        app.version = plist.get("CFBundleShortVersionString", "")
        app.bundle_id = plist.get("CFBundleIdentifier", "")
        app.minimum_os_version = plist.get("LSMinimumSystemVersion", "")
        return app
    return None


def current_os_version() -> str:
    os_version = os.popen("sw_vers -productVersion").read()
    os_version = os_version.replace("\n", "")
    return os_version

def cleanup_environment():
    _close_openned_apps()
    _kill_store_prompt()
    kill_store_user_notification()

def kill_store_user_notification():
    try:
        subprocess.check_call(["osascript", "-e", f'quit app id "com.apple.UserNotificationCenter"'])
        print("Store user notification was killed")
    except subprocess.CalledProcessError as e:
        print(f"Failed to kill store user notification. Error: {e}")

def _kill_store_prompt():
    try:
        subprocess.check_call(["killall", "storeuid"])
        print("Store prompt was killed")
    except subprocess.CalledProcessError as e:
        print(f"Failed to kill store prompt. Error: {e}")

def _close_openned_apps():
    subprocess.check_call(["osascript", "-e", f'quit app id "com.apple.systempreferences"'])
    subprocess.check_call(["osascript", "-e", f'quit app id "com.apple.appstore"'])
    subprocess.check_call(["osascript", "-e", f'quit app id "com.apple.safari"'])

    os.system(f'killall "Mail"')
    os.system(f'killall "App Store"')
    os.system(f'killall "Safari"')
    os.system(f'killall "Passwords"')

    print("All opened apps were closed")

def hide_all_apps_apple_script(app_name: str):   
    print(f"Hiding all apps except {app_name}")
    result = os.system(f'''osascript -e 'tell application "System Events" to set visible of every process whose visible is true and name is not "{app_name}" and frontmost is false to false' ''')
    print(f"Result: {result}")


