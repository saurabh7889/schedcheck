"""Entry point for `python -m schedcheck`."""

import sys
from schedcheck.cli import main

if __name__ == "__main__":
    sys.exit(main())