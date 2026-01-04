"""
File Organizer Utility

This script organizes files in a directory by their extensions.
It creates subdirectories for each file type and moves files accordingly.

Usage:
    python file_organizer.py [directory_path]

Example:
    python file_organizer.py ~/Downloads
"""

import os
import shutil
from pathlib import Path
import argparse


def organize_files(directory):
    """
    Organize files in the specified directory by their extensions.
    
    Args:
        directory (str): Path to the directory to organize
    """
    dir_path = Path(directory)
    
    if not dir_path.exists():
        print(f"Error: Directory '{directory}' does not exist.")
        return
    
    if not dir_path.is_dir():
        print(f"Error: '{directory}' is not a directory.")
        return
    
    # Get all files in the directory
    files = [f for f in dir_path.iterdir() if f.is_file()]
    
    if not files:
        print("No files to organize.")
        return
    
    print(f"Organizing {len(files)} files in {directory}...")
    
    for file in files:
        # Get file extension
        extension = file.suffix.lower()
        
        if not extension:
            extension = ".no_extension"
        else:
            extension = extension[1:]  # Remove the dot
        
        # Create directory for this file type if it doesn't exist
        type_dir = dir_path / extension
        type_dir.mkdir(exist_ok=True)
        
        # Move file to the appropriate directory
        destination = type_dir / file.name
        
        try:
            shutil.move(str(file), str(destination))
            print(f"Moved: {file.name} -> {extension}/")
        except Exception as e:
            print(f"Error moving {file.name}: {e}")
    
    print("Organization complete!")


def main():
    parser = argparse.ArgumentParser(
        description="Organize files in a directory by their extensions"
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to organize (default: current directory)"
    )
    
    args = parser.parse_args()
    organize_files(args.directory)


if __name__ == "__main__":
    main()
