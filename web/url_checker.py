"""
Simple URL Checker

This script checks if URLs are accessible and returns their status codes.

Usage:
    python url_checker.py <url1> [url2] [url3] ...

Example:
    python url_checker.py https://www.google.com https://github.com
"""

import sys
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


def check_url(url):
    """
    Check if a URL is accessible.
    
    Args:
        url (str): URL to check
        
    Returns:
        tuple: (status_code, message)
    """
    try:
        # Add a user agent to avoid being blocked by some servers
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urlopen(req, timeout=10) as response:
            status_code = response.getcode()
            return status_code, "OK"
    
    except HTTPError as e:
        return e.code, f"HTTP Error: {e.reason}"
    
    except URLError as e:
        return None, f"URL Error: {e.reason}"
    
    except Exception as e:
        return None, f"Error: {str(e)}"


def main():
    """Main function to check multiple URLs."""
    if len(sys.argv) < 2:
        print("Usage: python url_checker.py <url1> [url2] [url3] ...")
        print("Example: python url_checker.py https://www.google.com")
        sys.exit(1)
    
    urls = sys.argv[1:]
    
    print(f"Checking {len(urls)} URL(s)...\n")
    
    for url in urls:
        print(f"Checking: {url}")
        status_code, message = check_url(url)
        
        if status_code:
            if status_code == 200:
                print(f"  ✓ Status: {status_code} - {message}")
            else:
                print(f"  ⚠ Status: {status_code} - {message}")
        else:
            print(f"  ✗ {message}")
        print()


if __name__ == "__main__":
    main()
