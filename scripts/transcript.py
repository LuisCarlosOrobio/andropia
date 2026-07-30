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
    doing: dict[str, tuple] = {}
    driver: str | None = None
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

        # Stated before any line, and again if it ever changes. The autopilot
        # speaks from eight canned phrases; a transcript of those looks like a
        # model looping rather than like the wrong driver, so the reader has to
        # be told which they are watching before they start interpreting.
        if data.get("driver") != driver:
            driver = data.get("driver")
            if driver == "autopilot":
                print(
                    "  ** driver: deterministic AUTOPILOT — canned phrases, no model.\n"
                    "     export ANTHROPIC_API_KEY (or ANDROPIA_BASE_URL) and restart\n"
                    "     `make dev` to let language models drive them.\n"
                )
            elif driver == "models":
                print("  ** driver: language models\n")
            else:
                print("  ** driver: none — nothing is driving these beings\n")

        for line in data["lines"]:
            if line["tick"] < seen:
                continue
            print(f"  t={line['tick']:<6} {line['speaker']:<8} {line['text']}")
            seen = line["tick"] + 1

        # Actions, so narration and action can be told apart. A being that
        # says "I'm going to the tree" without emitting the tag stands still,
        # and the transcript alone would read as if it had gone.
        for being, state in sorted(data.get("doing", {}).items()):
            now = (state["action"], state["emotion"], state["gaze"])
            if doing.get(being) != now:
                if being in doing:
                    bits = [state["action"]]
                    if state["emotion"]:
                        bits.append(state["emotion"])
                    if state["gaze"]:
                        bits.append(f"looking at {state['gaze']}")
                    print(f"     {'':8} {being:<8} ({', '.join(bits)})")
                doing[being] = now

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
