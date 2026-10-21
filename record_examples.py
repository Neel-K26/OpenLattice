# Run ON THE POD (GPU). Records the model output for every example in the app, so the app also runs on a laptop.
import duckdb, agent, replay, compare_agent as ca
from examples import EXAMPLES, COMPARE
print("mode:", replay.install(agent))
con = duckdb.connect("lattice.duckdb", read_only=True)
for name, q in EXAMPLES.items():
    for gate in (True, False):
        r = agent.ask(q, gate, con); print(("ON " if gate else "OFF"), name, "->", r["status"], str(r["answer"])[:70].replace("\n", " "))
for q in COMPARE:
    r = ca.ask_compare(q); print("CMP", q[:50], "->", r["status"])
import json; print("recorded model calls:", len(json.load(open("replay_cache.json"))))
