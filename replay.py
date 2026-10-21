"""Record/replay wrapper for the language model, so the app also runs on a laptop without a GPU.
On the GPU pod every model call is recorded in replay_cache.json. Without a GPU (or with LATTICE_REPLAY=1) the recorded
model output is replayed for the same prompt; the database query and the physics gate still run live."""
import json, os, hashlib
class ReplayMiss(RuntimeError): pass
FILE = os.environ.get("LATTICE_CACHE", "replay_cache.json")

def _gpu():
    try:
        import torch; return torch.cuda.is_available()
    except Exception: return False

def mode():
    return "replay" if (os.environ.get("LATTICE_REPLAY") == "1" or not _gpu()) else "live"

def _load():
    try: return json.load(open(FILE))
    except Exception: return {}

def install(agent):
    if getattr(agent, "_replay_installed", False): return mode()
    orig, cache = agent.generate, _load()
    def gen(messages, max_new=400):
        k = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()
        if mode() == "replay":
            if k in cache: return cache[k]
            raise ReplayMiss("Replay mode (no GPU): this exact question was not recorded. Pick one of the examples, or run on the GPU pod.")
        out = orig(messages, max_new); cache[k] = out; json.dump(cache, open(FILE, "w")); return out
    ask0 = agent.ask
    def ask(q, gate, con):
        try: return ask0(q, gate, con)
        except ReplayMiss as e:
            return dict(status="failed", answer="Could not answer.", claims={}, sq_limit=None, sql=None, table=None, n_flagged=0,
                        notes=[str(e) + " (Impossible claims and out-of-scope questions are still checked live.)"])
    agent.ask = ask
    agent.generate = gen; agent._replay_installed = True
    return mode()
