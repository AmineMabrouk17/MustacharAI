"""Allow running ``python -m mustachar.cli``."""

from __future__ import annotations

import sys

from mustachar.cli.index import main

main(sys.argv[1:])
