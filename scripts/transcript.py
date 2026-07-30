"""Tail a running world's transcript.

Run in a second terminal while ``make dev`` holds the first. The 3D view is the
right instrument for watching bodies and the wrong one for judging conversation:
speech bubbles expire, and a being can walk out of frame mid-sentence. This
prints every line as it lands and keeps it on screen.

Also surfaces each being's trouble, once, when it changes. A being that cannot
reach its model simply stands there, and the whole point of a transcript is to
tell you the difference between a being with nothing to say and a being that is
broken.
"""

from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8600"
POLL = 1.0


def main() -> int:
    import json

    seen = 0
    trouble: dict[str, str] = {}
    print(f"tailing {URL}  (ctrl-c to stop)\n")

    while True:
        try:
            with urllib.request.urlopen(f"{URL}/api/transcript?since={seen}") as r:
                data = json.load(r)
        except urllib.error.URLError:
            # The world runs whether anyone is watching, and so does this — a
            # server restart should not require restarting the tail.
            time.sleep(POLL)
            continue
        except KeyboardInterrupt:
            return 0

        for line in data["lines"]:
            if line["tick"] < seen:
                continue
            print(f"  t={line['tick']:<6} {line['speaker']:<8} {line['text']}")
            seen = line["tick"] + 1

        for being, message in sorted(data.get("trouble", {}).items()):
            if trouble.get(being) != message:
                print(f"  !! {being}: {message}")
                trouble[being] = message
        for being in tuple(trouble):
            if being not in data.get("trouble", {}):
                print(f"  ok {being}: recovered")
                del trouble[being]

        time.sleep(POLL)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print()
