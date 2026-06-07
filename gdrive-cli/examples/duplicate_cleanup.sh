#!/bin/bash
#
# duplicate_cleanup.sh - A script to identify and clean up duplicate files across Google Drive and OneDrive
#
# Usage: ./duplicate_cleanup.sh [options]
#
# Options:
#   --dry-run    Show what would be deleted without actually deleting (default)
#   --execute    Actually delete the identified duplicates
#
# This script:
# 1. Scans both Google Drive and OneDrive
# 2. Finds duplicates within each service
# 3. Identifies files that appear in both services
# 4. Recommends which files to delete based on modification date and size
#

set -euo pipefail

# Configuration
OUTPUT_DIR="$(pwd)/output"
DRY_RUN=true

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --execute)
      DRY_RUN=false
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Function to display usage
usage() {
  echo "Usage: $0 [options]"
  echo "Options:"
  echo "  --dry-run    Show what would be deleted without actually deleting (default)"
  echo "  --execute    Actually delete the identified duplicates"
}

# Function to run command with dry-run support
run_command() {
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would execute: $@"
  else
    echo "Executing: $@"
    "$@"
  fi
}

# Function to get file info from JSONL
get_file_info() {
  local file_path="$1"
  local file_id="$2"
  
  # Extract file info from JSONL
  grep "\"id\": \"$file_id\"" "$file_path" | sed 's/.*"name": "\([^"]*\)",.*"size": \([0-9]*\),.*"modified_time": "\([^"]*\)".*/\1|\2|\3/'
}

# Step 1: Scan Google Drive
echo "=== Scanning Google Drive ==="
gdrive-cli google scan --out "$OUTPUT_DIR/google-scan.jsonl" --all-drives

# Step 2: Scan OneDrive
echo "=== Scanning OneDrive ==="
gdrive-cli onedrive scan --out "$OUTPUT_DIR/onedrive-scan.jsonl"

# Step 3: Find duplicates in Google Drive
echo "=== Finding duplicates in Google Drive ==="
gdrive-cli google dupes "$OUTPUT_DIR/google-scan.jsonl" --exclude "backup" "temp" --min-group 2 > "$OUTPUT_DIR/google-dupes.txt"

# Step 4: Find duplicates in OneDrive
echo "=== Finding duplicates in OneDrive ==="
gdrive-cli onedrive dupes "$OUTPUT_DIR/onedrive-scan.jsonl" --exclude "backup" "temp" --min-group 2 > "$OUTPUT_DIR/onedrive-dupes.txt"

# Step 5: Identify files that appear in both services
# Extract file names from both scans
awk -F'|' '{print $1}' "$OUTPUT_DIR/google-dupes.txt" | sort > "$OUTPUT_DIR/google-files.txt"
awk -F'|' '{print $1}' "$OUTPUT_DIR/onedrive-dupes.txt" | sort > "$OUTPUT_DIR/onedrive-files.txt"

# Find common files between both services
comm -12 "$OUTPUT_DIR/google-files.txt" "$OUTPUT_DIR/onedrive-files.txt" > "$OUTPUT_DIR/common-files.txt"

# Step 6: Generate recommendations
echo "=== Recommendations ==="

if [ -s "$OUTPUT_DIR/common-files.txt" ]; then
  echo "Found $(wc -l < "$OUTPUT_DIR/common-files.txt") files that exist in both services:" 
  cat "$OUTPUT_DIR/common-files.txt"
  echo ""
  
  echo "Recommendation: Keep the most recently modified version from each service."
  echo "For each file, compare the modified_time and size to decide which to keep."
  echo ""
  
  # For each common file, get the info from both services
  while IFS= read -r filename; do
    echo "--- $filename ---"
    
    # Get Google Drive info
    google_info=$(get_file_info "$OUTPUT_DIR/google-scan.jsonl" "$(grep "\"name\": \"$filename\"" "$OUTPUT_DIR/google-scan.jsonl" | head -1 | jq -r '.id')")
    if [ -n "$google_info" ]; then
      echo "Google Drive: $google_info"
    fi
    
    # Get OneDrive info
    onedrive_info=$(get_file_info "$OUTPUT_DIR/onedrive-scan.jsonl" "$(grep "\"name\": \"$filename\"" "$OUTPUT_DIR/onedrive-scan.jsonl" | head -1 | jq -r '.id')")
    if [ -n "$onedrive_info" ]; then
      echo "OneDrive: $onedrive_info"
    fi
    
    echo ""
  done < "$OUTPUT_DIR/common-files.txt"
else
  echo "No files found that exist in both services."
fi

# Step 7: Summary
echo "=== Summary ==="
echo "Google Drive: $(grep -c '^' "$OUTPUT_DIR/google-scan.jsonl") files"
echo "OneDrive: $(grep -c '^' "$OUTPUT_DIR/onedrive-scan.jsonl") files"
echo "Duplicates in Google Drive: $(grep -c '^---' "$OUTPUT_DIR/google-dupes.txt") groups"
echo "Duplicates in OneDrive: $(grep -c '^---' "$OUTPUT_DIR/onedrive-dupes.txt") groups"
echo "Files in both services: $(wc -l < "$OUTPUT_DIR/common-files.txt")"

# Final message
if [ "$DRY_RUN" = true ]; then
  echo ""
  echo "To actually delete files, run with --execute"
  echo "WARNING: This will permanently delete files from your cloud storage!"
else
  echo ""
  echo "Execution completed. Review the recommendations above before proceeding with deletions."
fi