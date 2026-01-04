"""
Backup Utility

This script creates timestamped backups of specified files or directories.

Usage:
    python backup.py <source_path> [backup_directory]

Example:
    python backup.py /path/to/important/folder
    python backup.py myfile.txt ./backups
"""

import os
import shutil
from datetime import datetime
from pathlib import Path
import argparse


def create_backup(source, backup_dir=None):
    """
    Create a backup of the specified file or directory.
    
    Args:
        source (str): Path to the file or directory to backup
        backup_dir (str): Directory where backups will be stored (default: ./backups)
    """
    source_path = Path(source)
    
    if not source_path.exists():
        print(f"Error: Source '{source}' does not exist.")
        return
    
    # Set default backup directory if not provided
    if backup_dir is None:
        backup_dir = Path("./backups")
    else:
        backup_dir = Path(backup_dir)
    
    # Create backup directory if it doesn't exist
    backup_dir.mkdir(exist_ok=True)
    
    # Create timestamp for backup name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{source_path.name}_{timestamp}"
    backup_path = backup_dir / backup_name
    
    try:
        if source_path.is_file():
            shutil.copy2(str(source_path), str(backup_path))
            print(f"Backup created: {backup_path}")
        elif source_path.is_dir():
            shutil.copytree(str(source_path), str(backup_path))
            print(f"Backup created: {backup_path}")
        
        print(f"Backup size: {get_size(backup_path)}")
    except Exception as e:
        print(f"Error creating backup: {e}")


def get_size(path):
    """
    Get the size of a file or directory.
    
    Args:
        path (Path): Path to measure
        
    Returns:
        str: Human-readable size
    """
    if path.is_file():
        size = path.stat().st_size
    else:
        size = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
    
    # Convert to human-readable format
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def main():
    parser = argparse.ArgumentParser(
        description="Create timestamped backups of files or directories"
    )
    parser.add_argument(
        "source",
        help="Path to the file or directory to backup"
    )
    parser.add_argument(
        "backup_dir",
        nargs="?",
        default=None,
        help="Directory where backups will be stored (default: ./backups)"
    )
    
    args = parser.parse_args()
    create_backup(args.source, args.backup_dir)


if __name__ == "__main__":
    main()
