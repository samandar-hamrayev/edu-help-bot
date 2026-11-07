"""Container healthcheck for the bot worker: is the outbox loop still ticking?

Exit code 0 when the heartbeat file was touched recently, 1 otherwise.
Deliberately does not import Django so it stays cheap.
"""

import os
import sys
import time

HEARTBEAT_FILE = os.getenv("BOT_HEARTBEAT_FILE", "/tmp/edu-help-bot.heartbeat")  # noqa: S108
MAX_AGE_SECONDS = float(os.getenv("BOT_HEARTBEAT_MAX_AGE", "120"))


def main() -> int:
    try:
        age = time.time() - os.path.getmtime(HEARTBEAT_FILE)
    except OSError:
        print(f"no heartbeat file at {HEARTBEAT_FILE}")
        return 1
    if age > MAX_AGE_SECONDS:
        print(f"heartbeat is stale ({age:.0f}s old)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
