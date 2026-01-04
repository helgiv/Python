"""
Task Scheduler Script

This script demonstrates a simple task scheduler that runs specified tasks
at defined intervals.

Usage:
    python task_scheduler.py

Note: Modify the tasks dictionary to add your own scheduled tasks.
"""

import time
import schedule
from datetime import datetime


def example_task():
    """Example task that prints a message."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Task executed!")


def backup_task():
    """Example backup task."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running backup...")
    # Add your backup logic here


def cleanup_task():
    """Example cleanup task."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running cleanup...")
    # Add your cleanup logic here


def main():
    """
    Main function to set up and run scheduled tasks.
    
    Modify the schedule calls below to customize your tasks.
    """
    print("Task Scheduler started...")
    print("Press Ctrl+C to stop\n")
    
    # Schedule tasks
    # Examples of different scheduling options:
    
    # Run every 10 seconds (for testing)
    schedule.every(10).seconds.do(example_task)
    
    # Run every hour
    # schedule.every().hour.do(example_task)
    
    # Run every day at specific time
    # schedule.every().day.at("10:30").do(backup_task)
    
    # Run every Monday
    # schedule.every().monday.do(cleanup_task)
    
    # Run every Wednesday at 13:15
    # schedule.every().wednesday.at("13:15").do(example_task)
    
    # Keep the script running
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nScheduler stopped.")


if __name__ == "__main__":
    # Note: This script requires the 'schedule' package
    # Install it with: pip install schedule
    try:
        main()
    except ImportError:
        print("Error: 'schedule' package not found.")
        print("Install it with: pip install schedule")
