"""Beings: the half of Andropia that thinks.

The simulation is a pure fold and must stay one. Language models are neither
pure nor fast nor reliable, so they live strictly outside it, and the boundary
between the two is the **intent log**.

    perception  world  -> what one being can see        pure
    prompt      that   -> chat messages                 pure
    adapter     those  -> a model's reply               the only impure part
    protocol    reply  -> intents                       pure
    session     intents-> next world                    pure

Only ``adapter`` touches the network. Everything else is a function over plain
data, which is why the interesting behaviour here can be tested without a
model, a key or a socket.

That layout is also what keeps replay honest. A recorded run stores the intents
a being produced, not the prompts that produced them, so replaying never calls
a model: the same intent log gives the same world, whatever the temperature was
and whether or not the endpoint still exists. Determinism is a property of the
simulation, and nothing here is allowed to weaken it.
"""

from __future__ import annotations
