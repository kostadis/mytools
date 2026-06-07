#!/bin/bash
#
# file_organization.sh - A script to organize files in Google Drive and OneDrive by type and date
#
# Usage: ./file_organization.sh [options]
#
# Options:
#   --dry-run    Show what would be moved without actually moving (default)
#   --execute    Actually move the files
#
# This script:
# 1. Scans a specified directory in Google Drive and OneDrive
# 2. Organizes files by type (documents, images, videos, etc.)
# 3. Creates year/month subfolders and moves files accordingly
# 4. Handles both services with the same logic
#

set -euo pipefail

# Configuration
OUTPUT_DIR="$(pwd)/output"
DRY_RUN=true
SOURCE_FOLDER="Documents"  # Change this to the folder you want to organize

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
    --source)
      SOURCE_FOLDER="$2"
      shift 2
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
  echo "  --dry-run    Show what would be moved without actually moving (default)"
  echo "  --execute    Actually move the files"
  echo "  --source     Source folder to organize (default: Documents)"
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

# Function to get folder ID by name
get_folder_id() {
  local service="$1"
  local folder_name="$2"
  
  # First, scan the service to get all files
  local scan_file="$OUTPUT_DIR/${service}-scan.jsonl"
  gdrive-cli ${service} scan --out "$scan_file" --all-drives
  
  # Then find the folder ID
  grep "\"name\": \"$folder_name\"" "$scan_file" | grep "\"mimeType\": \"application/vnd.google-apps.folder\"" | head -1 | jq -r '.id'
}

# Function to move files by type
move_files_by_type() {
  local service="$1"
  local source_folder_id="$2"
  
  echo "Organizing files in $service for folder ID: $source_folder_id"
  
  # Create a temporary file with all files in the source folder
  local all_files="$OUTPUT_DIR/${service}_files_in_source.jsonl"
  grep "\"parents\": \[\"$source_folder_id\"\]" "$OUTPUT_DIR/${service}-scan.jsonl" > "$all_files"
  
  # Process by file type
  local types=("pdf" "doc" "docx" "txt" "jpg" "jpeg" "png" "mp4" "avi" "mov" "zip" "rar")
  
  for type in "${types[@]}"; do
    # Skip if no files of this type
    if ! grep -q "\"name\": \".*\.$type\"" "$all_files"; then
      continue
    fi
    
    echo "Processing $type files..."
    
    # Create year/month folders and move files
    while IFS= read -r line; do
      # Extract file info
      file_name=$(echo "$line" | jq -r '.name')
      file_id=$(echo "$line" | jq -r '.id')
      modified_time=$(echo "$line" | jq -r '.modified_time')
      
      # Extract year and month from modified_time (format: 2023-12-01T10:30:00.000Z)
      year=$(echo "$modified_time" | cut -d'-' -f1)
      month=$(echo "$modified_time" | cut -d'-' -f2)
      
      # Create target folder name
      target_folder_name="$type/$year/$month"
      
      # Check if target folder exists
      target_folder_id=$(get_folder_id "$service" "$target_folder_name")
      
      # If folder doesn't exist, create it
      if [ -z "$target_folder_id" ] || [ "$target_folder_id" = "null" ]; then
        # Create parent folder structure
        parent_path="$type/$year"
        parent_folder_id=$(get_folder_id "$service" "$parent_path")
        
        if [ -z "$parent_folder_id" ] || [ "$parent_folder_id" = "null" ]; then
          # Create type folder
          type_folder_id=$(get_folder_id "$service" "$type")
          if [ -z "$type_folder_id" ] || [ "$type_folder_id" = "null" ]; then
            # Create type folder
            run_command gdrive-cli ${service} move "$source_folder_id" --to "$type" --create-folder --execute
            type_folder_id=$(get_folder_id "$service" "$type")
          fi
          
          # Create year folder
          run_command gdrive-cli ${service} move "$type_folder_id" --to "$year" --create-folder --execute
          parent_folder_id=$(get_folder_id "$service" "$parent_path")
        fi
        
        # Create month folder
        run_command gdrive-cli ${service} move "$parent_folder_id" --to "$month" --create-folder --execute
        target_folder_id=$(get_folder_id "$service" "$target_folder_name")
      fi
      
      # Move the file
      if [ -n "$target_folder_id" ] && [ "$target_folder_id" != "null" ]; then
        run_command gdrive-cli ${service} move "$file_id" --to "$target_folder_id" --execute
      fi
      
    done < <(grep "\"name\": \".*\.$type\"" "$all_files")
  done
}

# Step 1: Scan Google Drive
echo "=== Scanning Google Drive ==="
gdrive-cli google scan --out "$OUTPUT_DIR/google-scan.jsonl" --all-drives

# Step 2: Scan OneDrive
echo "=== Scanning OneDrive ==="
gdrive-cli onedrive scan --out "$OUTPUT_DIR/onedrive-scan.jsonl"

# Step 3: Get source folder IDs
echo "=== Getting source folder IDs ==="
google_source_id=$(get_folder_id "google" "$SOURCE_FOLDER")
onedrive_source_id=$(get_folder_id "onedrive" "$SOURCE_FOLDER")

# Check if source folders exist
if [ -z "$google_source_id" ] || [ "$google_source_id" = "null" ]; then
  echo "Error: Google Drive source folder \"$SOURCE_FOLDER\" not found."
  exit 1
fi

if [ -z "$onedrive_source_id" ] || [ "$onedrive_source_id" = "null" ]; then
  echo "Error: OneDrive source folder \"$SOURCE_FOLDER\" not found."
  exit 1
fi

# Step 4: Organize files in Google Drive
echo "=== Organizing files in Google Drive ==="
move_files_by_type "google" "$google_source_id"

# Step 5: Organize files in OneDrive
echo "=== Organizing files in OneDrive ==="
move_files_by_type "onedrive" "$onedrive_source_id"

# Step 6: Summary
echo "=== Summary ==="
echo "Source folder: $SOURCE_FOLDER"
echo "Google Drive source folder ID: $google_source_id"
echo "OneDrive source folder ID: $onedrive_source_id"
echo "Organization completed."

if [ "$DRY_RUN" = true ]; then
  echo ""
  echo "To actually move files, run with --execute"
  echo "WARNING: This will move files in your cloud storage!"
else
  echo ""
  echo "Execution completed. Files have been organized by type and date."
fi