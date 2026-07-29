"""The imperative shell around the pure simulation.

`andropia.sim` is a pure fold and knows nothing about time, networks or
models. This package is where the outside world is allowed in — but under
strict separation:

* :mod:`session` is still pure. It carries pending intents, the recording,
  and transport state, and every transition returns a new value.
* :mod:`clock` is the **only** module in the project permitted to read wall
  time. If determinism is ever in question, this is the one file to audit.
"""

from .session import (
    Recording,
    Session,
    advance,
    begin,
    fork,
    pause,
    propose,
    replay,
    resume,
    set_speed,
    tick,
)

__all__ = [
    "Recording", "Session", "advance", "begin", "fork", "pause", "propose",
    "replay", "resume", "set_speed", "tick",
]
