"""CLI entrypoint for health checks."""

import asyncio
import sys

from services.observability.health.service import _cli_main

if __name__ == "__main__":
    sys.exit(asyncio.run(_cli_main()))
