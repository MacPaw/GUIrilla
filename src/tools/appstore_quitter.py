#!/usr/bin/env python3

import subprocess
import time
import sys

def run_applescript(script):
    """Run an AppleScript command and return its output."""
    try:
        process = subprocess.Popen(['osascript', '-e', script], 
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        return stdout.decode().strip(), stderr.decode().strip()
    except Exception as e:
        print(f"Error running AppleScript: {e}")
        return None, str(e)

def check_and_dismiss_dialog():
    """Check for storeui process and dismiss any error dialog."""
    # Check if storeui process exists
    process_check = '''
    tell application "System Events"
        return exists process "storeuid"
    end tell
    '''
    exists, err = run_applescript(process_check)
    
    if exists.lower() != "true":
        return False
        
    # Try to find and click the OK button
    dismiss_script = '''
    tell application "System Events"
        tell process "storeuid"
            try
                click button "OK" of window 1
                return true
            on error
                return false
            end try
        end tell
    end tell
    '''
    
    result, err = run_applescript(dismiss_script)
    return result.lower() == "true"

def main():
    print("Starting App Store dialog monitor...")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            if check_and_dismiss_dialog():
                print("Dialog dismissed!")
            time.sleep(15)
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
        sys.exit(0)

if __name__ == "__main__":
    main()
