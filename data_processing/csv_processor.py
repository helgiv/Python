"""
CSV Data Processor

This script demonstrates common CSV data processing operations.

Usage:
    python csv_processor.py <input_file.csv> [output_file.csv]

Example:
    python csv_processor.py data.csv processed_data.csv
"""

import csv
import argparse
from pathlib import Path


def process_csv(input_file, output_file=None):
    """
    Process a CSV file and perform various operations.
    
    Args:
        input_file (str): Path to input CSV file
        output_file (str): Path to output CSV file (optional)
    """
    input_path = Path(input_file)
    
    if not input_path.exists():
        print(f"Error: File '{input_file}' not found.")
        return
    
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            data = list(reader)
            
            if not data:
                print("Error: CSV file is empty.")
                return
            
            print(f"Loaded {len(data)} rows from {input_file}")
            print(f"Columns: {', '.join(reader.fieldnames)}")
            
            # Example processing: Print first 5 rows
            print("\nFirst 5 rows:")
            for i, row in enumerate(data[:5], 1):
                print(f"Row {i}: {row}")
            
            # Example processing: Count unique values in first column
            if reader.fieldnames:
                first_col = reader.fieldnames[0]
                unique_values = set(row[first_col] for row in data if first_col in row)
                print(f"\nUnique values in '{first_col}': {len(unique_values)}")
            
            # Write processed data if output file is specified
            if output_file:
                output_path = Path(output_file)
                with open(output_path, 'w', newline='', encoding='utf-8') as f:
                    if data:
                        writer = csv.DictWriter(f, fieldnames=reader.fieldnames)
                        writer.writeheader()
                        writer.writerows(data)
                        print(f"\nProcessed data written to {output_file}")
    
    except Exception as e:
        print(f"Error processing CSV: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Process CSV files"
    )
    parser.add_argument(
        "input_file",
        help="Path to input CSV file"
    )
    parser.add_argument(
        "output_file",
        nargs="?",
        default=None,
        help="Path to output CSV file (optional)"
    )
    
    args = parser.parse_args()
    process_csv(args.input_file, args.output_file)


if __name__ == "__main__":
    main()
