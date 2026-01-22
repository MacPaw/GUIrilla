import sqlite3
import time
import os
import argparse

from helpers import applications
from typing import List, Dict

tcc_db_path = '~/Library/Application Support/com.apple.TCC/TCC.db'
tcc_db_path = os.path.abspath(os.path.expanduser(tcc_db_path))

def grant_permissions(bundle_id: str, app_path: str, add: bool) -> bool:
    if bundle_id == "":
        print(f"❌ Failed to grant permissions, app bundle id is empty")
        return False
    
    protected_resources = _get_app_protected_resources(app_path)
    if len(protected_resources) == 0:
        print(f"🔑 No protected resources found for {bundle_id}")
        return False
    
    # Add all TCC services from the enumeration
    # Critical
    protected_resources.add("kTCCServiceLiverpool")  # location
    protected_resources.add("kTCCServiceUbiquity")   # icloud
    protected_resources.add("kTCCServiceShareKit")   # sharing
    protected_resources.add("kTCCServiceSystemPolicyAllFiles")  # fda
    
    # Common
    protected_resources.add("kTCCServiceAccessibility")  # accessibility
    protected_resources.add("kTCCServicePostEvent")      # keystrokes
    protected_resources.add("kTCCServiceListenEvent")    # inputMonitoring
    protected_resources.add("kTCCServiceDeveloperTool")  # developerTools
    protected_resources.add("kTCCServiceScreenCapture")  # screenCapture
    
    # File access
    protected_resources.add("kTCCServiceSystemPolicySysAdminFiles")  # adminFiles
    protected_resources.add("kTCCServiceSystemPolicyDesktopFolder")  # desktopFolder
    protected_resources.add("kTCCServiceSystemPolicyDeveloperFiles") # developerFiles
    protected_resources.add("kTCCServiceSystemPolicyDocumentsFolder") # documentsFolder
    protected_resources.add("kTCCServiceSystemPolicyDownloadsFolder") # downloadsFolder
    protected_resources.add("kTCCServiceSystemPolicyNetworkVolumes")  # networkVolumes
    
    # Service access
    protected_resources.add("kTCCServiceAddressBook")        # addressBook
    protected_resources.add("kTCCServiceAppleEvents")        # appleEvents
    protected_resources.add("kTCCServiceUserAvailability")   # availability
    protected_resources.add("kTCCServiceBluetoothAlways")    # bluetooth_always
    protected_resources.add("kTCCServiceCalendar")           # calendar
    protected_resources.add("kTCCServiceCamera")             # camera
    protected_resources.add("kTCCServiceContactsFull")       # contacts_full
    protected_resources.add("kTCCServiceContactsLimited")    # contacts_limited
    protected_resources.add("kTCCServiceLocation")           # currentLocation
    protected_resources.add("kTCCServiceFileProviderDomain") # fileAccess
    protected_resources.add("kTCCServiceFileProviderPresence") # fileAccess_request
    protected_resources.add("kTCCServiceMotion")             # fitness
    protected_resources.add("kTCCServiceFocusStatus")        # focus_notifications
    protected_resources.add("kTCCServiceGameCenterFriends")  # gamecenter
    protected_resources.add("kTCCServiceWillow")             # homeData
    protected_resources.add("kTCCServiceMediaLibrary")       # mediaLibrary
    protected_resources.add("kTCCServiceMicrophone")         # microphone
    protected_resources.add("kTCCServicePhotos")             # photos
    protected_resources.add("kTCCServicePhotosAdd")          # photos_add
    protected_resources.add("kTCCServicePrototype3Rights")   # protoRight
    protected_resources.add("kTCCServiceReminders")          # reminders
    protected_resources.add("kTCCServiceSystemPolicyRemovableVolumes") # removableVolumes
    protected_resources.add("kTCCServiceSiri")               # siri
    protected_resources.add("kTCCServiceSpeechRecognition")  # speechRecognition
    protected_resources.add("kTCCServiceUserTracking")       # userTracking
    protected_resources.add("kTCCServiceHealthShare")        # healthShare
    protected_resources.add("kTCCServiceHealthUpdate")       # healthUpdate
    protected_resources.add("NSNetworkVolumesUsageDescription")        # networkVolumes
    protected_resources.add("NSLocalNetworkUsageDescription") # localNetwork
    protected_resources.add("kTCCServiceSystemPolicyAppBundles") # appBundles
    protected_resources.add("kTCCServiceSystemPolicyAppData") # appData

    for resource in protected_resources:
        print(f"🔑 Granting permission for: {resource}")
        _update_app_permissions(bundle_id, resource, add)

    return True



def _get_app_protected_resources(app_path: str) -> List[str]:
    protected_resources = set()
    info_plist_path = applications.read_app_plist(app_path)
    if info_plist_path is None:
        print(f"❌ Failed to read Info.plist: {info_plist_path}")
        return []
    
    for key, _ in info_plist_path.items():
        if key.endswith("UsageDescription"):
            protected_resources.add(key)
    return protected_resources



def _all_protected_resource_keys() -> Dict[str, str]:
    return {
    "NSAccessibilityUsageDescription": "kTCCServiceAccessibility",
    "NSBluetoothAlwaysUsageDescription": "kTCCServiceBluetoothAlways",
    "NSBluetoothPeripheralUsageDescription" : "kTCCServiceBluetoothAlways",
    "NSCalendarsFullAccessUsageDescription": "kTCCServiceCalendar",
    "NSCalendarsWriteOnlyAccessUsageDescription": "kTCCServiceCalendar",
    "NSRemindersFullAccessUsageDescription": "kTCCServiceReminders",
    "NSCameraUsageDescription": "kTCCServiceCamera",
    "NSMicrophoneUsageDescription": "kTCCServiceMicrophone",
    "NSContactsUsageDescription": "kTCCServiceAddressBook",
    "NSDesktopFolderUsageDescription": "kTCCServiceSystemPolicyDesktopFolder",
    "NSDocumentsFolderUsageDescription": "kTCCServiceSystemPolicyDocumentsFolder",
    "NSDownloadsFolderUsageDescription": "kTCCServiceSystemPolicyDownloadsFolder",
    "NSNetworkVolumesUsageDescription": "kTCCServiceSystemPolicyAllFiles",
    "NSRemovableVolumesUsageDescription": "kTCCServiceSystemPolicyAllFiles",
    "NSFileProviderDomainUsageDescription": "kTCCServiceSystemPolicyAllFiles",
    "NSHealthClinicalHealthRecordsShareUsageDescription": "kTCCServiceHealthShare",
    "NSLocationAlwaysAndWhenInUseUsageDescription": "kTCCServiceLocation",
    "NSLocationWhenInUseUsageDescription": "kTCCServiceLocation",
    "NSLocationAlwaysUsageDescription": "kTCCServiceLocation",
    "NSMotionUsageDescription": "kTCCServiceMotion",
    "NSLocalNetworkUsageDescription": "kTCCServiceSystemPolicyNetworkVolumes",
    "NSPhotoLibraryAddUsageDescription": "kTCCServicePhotosAdd",
    "NSPhotoLibraryUsageDescription": "kTCCServicePhotos",
    "NSUserTrackingUsageDescription": "kTCCServiceUserTracking",
    "NSAppleEventsUsageDescription": "kTCCServiceAppleEvents",
    "NSSystemAdministrationUsageDescription": "kTCCServiceSystemPolicyAllFiles",
    "NSSiriUsageDescription": "kTCCServiceSiri",
    "NSSpeechRecognitionUsageDescription": "kTCCServiceSpeechRecognition",
  }

def _modify_tcc_db(service, client, client_type, auth_value):
    print(f"🔑 Modifying TCC DB for {service} {client} {client_type} {auth_value}")
    print(f"🔑 TCC DB path: {tcc_db_path}")
    
    conn = sqlite3.connect(tcc_db_path)
    cursor = conn.cursor()
    if auth_value < 0:
        cursor.execute(
            'delete from access where service = ? and client = ? and client_type = ?;',
            (service, client, client_type)
        )
    else:
        cursor.execute(
            'insert or replace into access (service, client, client_type, auth_value, auth_reason, ' + \
            'auth_version, csreq, policy_id, indirect_object_identifier_type, indirect_object_identifier, ' + \
            'indirect_object_code_identity, flags, last_modified) ' + \
            'values(?, ?, ?, ?, 0, 1, null, null, 0, \'UNUSED\', null, 0, ?);',
            (service, client, client_type, auth_value, int(time.time()))
        )
    cursor.close()
    conn.commit()
    conn.close()

def _add_app_to_tcc(bundle_id: str, resource: str) -> bool:
    if bundle_id == "":
        print(f"❌ Failed to add app to TCC, app bundle id is empty")
        return False
    
    if resource == "":
        print(f"❌ Failed to add app to TCC, resource is empty")
        return False
    
    _modify_tcc_db(resource, bundle_id, 0, 2)
    return True
    

def _remove_app_from_tcc(bundle_id: str, resource: str) -> bool:
    if bundle_id == "":
        print(f"❌ Failed to remove app from TCC, app bundle id is empty")
        return False
    
    if resource == "":
        print(f"❌ Failed to remove app from TCC, resource is empty")
        return False
    
    _modify_tcc_db(resource, bundle_id, 0, -1)

    return True

def _is_root():
    return os.geteuid() == 0

def _update_app_permissions(bundle_id: str, resource: str, add: bool) -> bool:
    if not _is_root():
        print('❌ System permissions are required to grant permissions to the app.')
        return False

    if add:
        _add_app_to_tcc(bundle_id, resource)
    else:
        _remove_app_from_tcc(bundle_id, resource)
    
    print(f"✅ Updated permissions for {bundle_id} to {resource}")
    return True

if __name__ == "__main__":
    # create the parser
    arg_parser = argparse.ArgumentParser(
        description="Parse -b <bundle_id>"
    )

    # add the arguments
    arg_parser.add_argument("-b", type=str, help="Bundle ID")
    arg_parser.add_argument("-p", type=str, help="App path")
    group = arg_parser.add_mutually_exclusive_group()
    group.add_argument("--add", action="store_true", help="Add the resource")
    group.add_argument("--remove", action="store_false", dest="add", help="Remove the resource")

    # parse the arguments
    args = arg_parser.parse_args()

    # get the arguments
    bundle_id = args.b
    app_path = args.p
    add = args.add

    # bundle_id = "org.whispersystems.signal-desktop"
    # add = True
    print(f"🔑 Granting permissions for {bundle_id} to {add}")

    # grant permissions
    grant_permissions(bundle_id, app_path, add)