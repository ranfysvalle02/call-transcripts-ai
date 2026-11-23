#!/usr/bin/env python3
"""Enable `python -m callintel ...`."""
from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
