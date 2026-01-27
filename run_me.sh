#!/bin/bash

# Input parameters
# -a: application bundle id
# -o: output file
# -m: path to mas-cli
# -p: print window structure to the console
# -h: True/False - if True, the app will be hit tested
# -c: True/False - cursor parameter
# -t: True/False - tasks added on edges

# Example: ./run_me.sh -a com.macpaw.clearvpn.macosmas -o ./output -h True -c False -t True -l True -q 120

# Use parameters or default values
while getopts a:o:m:h:p:c:t:r:s:z:l:q: option
do
case "${option}"
in
a) APP_DETAILS=${OPTARG};;
o) OUTPUT_PATH=${OPTARG};;
h) HIT_TEST=${OPTARG};;
p) PRINT_NODES=${OPTARG};;
m) MAS_CLI_PATH=${OPTARG};;
c) CURSOR=${OPTARG};;
t) TASKS=${OPTARG};;
r) REMOVE_COMPLETED_APP_DETAILS=${OPTARG};;
s) PARSE_START_TIMESTAMP=${OPTARG};;
z) RUN_COUNT=${OPTARG};;
l) LLM_USAGE=${OPTARG};;
q) TOTAL_PARSE_TIME=${OPTARG};;
esac
done

OUTPUT_PATH=${OUTPUT_PATH:-"./output"}

HIT_TEST_PARAMETER=""
if [ "$HIT_TEST" == "True" ]; then
    HIT_TEST_PARAMETER="--hit-test"
fi

PRINT_NODES_PARAMETER=""
if [ "$PRINT_NODES" == "True" ]; then
    PRINT_NODES_PARAMETER="--print-nodes"
fi

CURSOR_PARAMETER=""
if [ "$CURSOR" == "True" ]; then
    CURSOR_PARAMETER="--cursor"
fi

TASKS_PARAMETER=""
if [ "$TASKS" == "True" ]; then
    TASKS_PARAMETER="--tasks"
fi

LLM_USAGE_PARAMETER=""
if [ "$LLM_USAGE" == "True" ]; then
    LLM_USAGE_PARAMETER="--llm-usage True"
fi

TOTAL_PARSE_TIME_PARAMETER=""
if [ -n "$TOTAL_PARSE_TIME" ]; then
    TOTAL_PARSE_TIME_PARAMETER="--total-parse-time $TOTAL_PARSE_TIME"
fi

if [ "$REMOVE_COMPLETED_APP_DETAILS" == "True" ]; then
    #remove file content if it exists
    if [ -f "completed_app_details.txt" ]; then
        echo "" > completed_app_details.txt
    fi
fi

declare -i RUN_COUNT_INT=${RUN_COUNT:-0}
if [ $RUN_COUNT_INT == 1 ]; then    
    #read app details from the completed_app_details.txt file
    COMPLETED_APP_DETAILS=$(cat completed_app_details.txt | grep -i "$APP_DETAILS" | awk -F, '{print $1}')
    if [ -n "$COMPLETED_APP_DETAILS" ]; then
        echo "App details already processed: $APP_DETAILS"
        exit 0
    fi
fi

# Prepare the app for parsing
echo "----------------------------------------------"
echo "Prepare the app for parsing... "$APP_DETAILS" mas_tool_path: $MAS_CLI_PATH"
python src/installer.py -a "$APP_DETAILS" -m "$MAS_CLI_PATH"

# Open the app
echo "----------------------------------------------"
echo "Launch the app..."
python src/launch_app.py -a "$APP_DETAILS"

# Parse application window structure
echo "----------------------------------------------"
echo "Parsing application window structure..."
python src/parse_app.py -a "$APP_DETAILS" -o "$OUTPUT_PATH" -t "$PARSE_START_TIMESTAMP" $HIT_TEST_PARAMETER $PRINT_NODES_PARAMETER $CURSOR_PARAMETER $TASKS_PARAMETER $LLM_USAGE_PARAMETER $TOTAL_PARSE_TIME_PARAMETER

# Close the app
echo "----------------------------------------------"
echo "Close the app..."
python src/close_app.py -a "$APP_DETAILS"

if [ $RUN_COUNT_INT == 1 ]; then
    # Uninstall the app
    echo "----------------------------------------------"
    echo "Uninstall the app..."
    python src/uninstaller.py -a "$APP_DETAILS" -m "$MAS_CLI_PATH"
fi
