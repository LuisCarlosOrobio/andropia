"""One being, two real turns, against a live Anthropic endpoint.

The thing to run when beings are not talking and you do not yet know whether
the cause is the key, the credit, the model id, the request shape or the prompt.
Each failure mode reports differently, which is the whole point — a silent
being tells you nothing, and this tells you which layer to look at.

Two turns rather than one, because a single call cannot show whether prompt
caching works: the first writes the cache and reads nothing by definition. The
second is what proves the breakpoint is above the model's minimum cacheable
prefix, which is otherwise a silent failure — no error, just full price on every
turn forever.

Costs roughly a cent. Run it before spending real money on a long session.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from andropia.beings import claude, perception, prompt, protocol  # noqa: E402
from andropia.runtime.server import demo_world  # noqa: E402

TURNS = 2


async def main() -> int:
    try:
        import anthropic
    except ImportError:
        print("the anthropic SDK is missing — pip install -e '.[claude]'")
        return 1

    world = demo_world()
    being = "ava"
    ent = world.entities[being]
    messages = prompt.messages(ent, perception.observe(world, being))
    model = claude.Claude.from_env()

    print(f"model:  {model.name}   effort={model.effort}")
    print(f"being:  {being}\n")

    client = anthropic.AsyncAnthropic()
    system, chat = claude.split(messages)

    for turn in range(1, TURNS + 1):
        try:
            response = await client.messages.create(
                model=model.name,
                max_tokens=model.max_tokens,
                system=system,
                messages=chat,
                thinking={"type": "adaptive"},
                output_config={"effort": model.effort},
            )
        except anthropic.APIStatusError as exc:
            print(f"turn {turn}: FAILED  http {exc.status_code}")
            print(f"  {exc}")
            print(f"\n{_diagnose(exc.status_code, str(exc))}")
            return 1
        except anthropic.APIConnectionError as exc:
            print(f"turn {turn}: FAILED  unreachable — {exc}")
            return 1
        except TypeError as exc:
            if "authentication" in str(exc).lower():
                print(f"turn {turn}: FAILED  no credential — set ANTHROPIC_API_KEY")
                return 1
            raise

        said = "".join(b.text for b in response.content if b.type == "text")
        usage = response.usage
        written = getattr(usage, "cache_creation_input_tokens", 0) or 0
        read = getattr(usage, "cache_read_input_tokens", 0) or 0

        print(f"turn {turn}")
        print(f"  says:    {said!r}")
        print(f"  intents: {protocol.to_intents(protocol.parse(said), being)}")
        print(f"  stop:    {response.stop_reason}")
        print(
            f"  tokens:  in {usage.input_tokens}  out {usage.output_tokens}"
            f"  cache_write {written}  cache_read {read}"
        )

    print()
    if read:
        print(
            f"prompt caching works — {read} tokens served from cache on turn {TURNS}."
        )
    else:
        print(
            "prompt caching is NOT working: cache_read stayed at zero on a repeat\n"
            "request. The cached prefix is probably below this model's minimum, so\n"
            "every turn pays full input price. Move the breakpoint later in\n"
            "`claude.split` so more of the prompt sits inside it."
        )
    return 0


def _diagnose(status: int, message: str) -> str:
    """Name the layer, so the next step is obvious."""
    if "credit balance" in message:
        return "Billing: buy credits under Plans & Billing in the Console."
    if status == 401:
        return "The key is wrong or not exported. Check ANTHROPIC_API_KEY."
    if status == 404:
        return "No such model. Check ANDROPIA_CLAUDE_MODEL; ids carry no date suffix."
    if status == 429:
        return "Rate limited. New accounts start on a low tier; wait and retry."
    if status == 400:
        return "The request was rejected — this is ours to fix, not yours."
    return "Unexpected. The request_id above is what Anthropic needs to trace it."


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
