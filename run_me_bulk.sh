#!/bin/bash

# Input parameters
# -m: path to mas-cli
# -o: path to the output file
# -i: file path with the list of application details (name, bundle, store identifier(if applicable), location) - Calculator,com.apple.calculator,,os
#     possible locations: os - local and system apps, mas - mac app store, mu - mac update

# Example: ./run_me_bulk.sh -m /Path/to/mas -o ./output -i ./app_details.txt

# Use parameters or default values
while getopts "m:o:i:r:l:q:" opt; do
  case $opt in
    m) MAS_PATH="$OPTARG"
    ;;
    o) OUTPUT_DIR="$OPTARG"
    ;;
    i) INPUT_FILE="$OPTARG"
    ;;
    r) RUN_COUNT="$OPTARG"
    ;;
    l) LLM_USAGE="$OPTARG"
    ;;
    q) TOTAL_PARSE_TIME="$OPTARG"
    ;;
    \?) echo "Invalid option -$OPTARG" >&2
    exit 1
    ;;
  esac
done

# Check if required parameters are provided
if [ -z "$MAS_PATH" ] || [ -z "$OUTPUT_DIR" ] || [ -z "$INPUT_FILE" ] || [ -z "$LLM_USAGE" ]; then
  echo "Error: Missing required parameters. Usage: ./run_me_bulk.sh -m <mas_path> -o <output_dir> -i <input_file> -l <LLM_usage>"
  exit 1
fi

if [ -z "$RUN_COUNT" ]; then
  RUN_COUNT=1
fi

if [ -z "$TOTAL_PARSE_TIME" ]; then
  TOTAL_PARSE_TIME=120
fi

echo "Mas cli path: $MAS_PATH"
echo "Output directory: $OUTPUT_DIR"
echo "Input file: $INPUT_FILE"
echo "Run count: $RUN_COUNT"
echo "LLM (GPT4) usage: $LLM_USAGE"

# Check if the input file exists
if [ ! -f "$INPUT_FILE" ]; then
  echo "Error: Input file '$INPUT_FILE' not found."
  exit 1
fi

# Create the output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# Append the current date and time to the output directory
OUTPUT_DIR="$OUTPUT_DIR/$(date +'%Y-%m-%d_%H-%M-%S')"

# Read the file with the list of applications
declare -i RUN_COUNT_INT=${RUN_COUNT:-0}
for (( i=RUN_COUNT_INT; i>0; i-- )); do
    PARSE_START_TIMESTAMP=$(date +%s)

    RUN_OUTPUT_PATH="$OUTPUT_DIR/run_$i"
    echo "Run output path: $RUN_OUTPUT_PATH"

    while IFS= read -r line
    do
        echo "----------------------------------------------"
        echo "Start line processing: $line"
        echo "Line: $line"
        echo "Run #$((i)), app: $line"
        echo "----------------------------------------------"
        ./run_me.sh -a "$line" -o "$RUN_OUTPUT_PATH" -h False -m "$MAS_PATH" -c False -t True -r False -s "$PARSE_START_TIMESTAMP" -z "$RUN_COUNT" -l "$LLM_USAGE" -q "$TOTAL_PARSE_TIME"
        echo "----------------------------------------------"
        echo "Completed line processing: $line"
        echo "----------------------------------------------"
        echo "Sleep for 1 second before processing next app..."
        sleep 1
    done < "$INPUT_FILE"
done

# Run the meta-task post-processing script
# echo "Running meta-task post-processing..."
# python src/meta_tasks_post_processing.py