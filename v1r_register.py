#!/usr/bin/env python3
"""
Tesla RSA Key Registration for Powerwall LAN TEDapi v1r

Thin shim — delegates to pypowerwall.v1r_register so you do not need to
pip-install: running this script directly from a clone is sufficient.
"""
import os
import sys

# Make the pypowerwall package importable when running from a clone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pypowerwall.v1r_register import main

if __name__ == "__main__":
    main()
