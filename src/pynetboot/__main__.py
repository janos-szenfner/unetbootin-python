#!/usr/bin/env python3
"""
Allow running as python -m pynetboot
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pynetboot.main import main

if __name__ == "__main__":
    main()
