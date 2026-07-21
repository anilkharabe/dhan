#!/usr/bin/env python3
"""
Launcher for the trading backend. Adds backend/ to sys.path and runs main.
Run from project root: python run_backend.py
"""
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
_backend = os.path.join(_root, "backend")
if _backend not in sys.path:
    sys.path.insert(0, _backend)

import main

if __name__ == "__main__":
    main.main()
