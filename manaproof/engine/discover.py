"""Discovery pipeline: enumerate → symbolic filter → search → novelty → Lean.

Runs as a background job owned by the server; every stage reports to an event
bus so the web UI can watch it live.
"""
import hashlib, itertools, json, multiprocessing as mp, os, queue, threading, time
from concurrent.futures import ThreadPoolExecutor
from .model import Engine, mana_total
from .pool import DB, POOL
from .symbolic import Symbolic
from . import search, leangen, describe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "data", "store.json")
OUTCOME_LABEL = {"mana": "Infinite mana", "life": "Infinite life", "damage": "Infinite damage",
                 "draw": "Infinite draw", "mill": "Infinite mill", "tokens": "Infinite tokens",
                 "counters": "Infinite counters"}
WINS = {"damage", "mill"}

E = Engine(DB)
SYM = Symbolic(DB)
_wE = None


def _winit():
    global _wE
    _wE = Engine(DB)


def _work(args):
    ids, max_nodes, max_depth, tl = args
    t = time.time()
    try:
        res, nodes = search.search_set(_wE, ids, max_nodes, max_depth, tl)
    except Exception as ex:  # a search bug must not kill the run
        return ids, [], 0, time.time() - t, repr(ex)
    return ids, res, nodes, time.time() - t, None


class Bus:
    """Fan-out of events to SSE subscribers, with a replay buffer."""

    def __init__(self):
        self.subs = []; self.lock = threading.Lock(); self.recent = []; self.seq = 0

    def emit(self, kind, **data):
        with self.lock:
            self.seq += 1
            ev = {"seq": self.seq, "t": time.time(), "kind": kind, **data}
            if kind in ("log", "combo", "verify"):
                self.recent.append(ev); self.recent = self.recent[-400:]
            for q in list(self.subs):
                try: q.put_nowait(ev)
                except queue.Full: pass
        return ev

    def subscribe(self):
        q = queue.Queue(maxsize=2000)
        with self.lock:
            self.subs.append(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.subs: self.subs.remove(q)


class Store:
    def __init__(self, path=STORE):
        self.path = path; self.lock = threading.RLock()
        self.combos = {}; self.runs = []; self._dirty = False
        if os.path.exists(path):
            try:
                d = json.load(open(path))
                self.combos = d.get("combos", {}); self.runs = d.get("runs", [])
            except Exception:
                pass

    def save(self, force=False):
        with self.lock:
            if not (self._dirty or force): return
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            json.dump({"combos": self.combos, "runs": self.runs}, open(tmp, "w"), separators=(",", ":"))
            os.replace(tmp, self.path); self._dirty = False

    def put(self, c):
        with self.lock:
            self.combos[c["id"]] = c; self._dirty = True

    def sub_outcomes(self, ids):
        """Outcomes already achieved by proper subsets of `ids`, and those combos' ids."""
        s = set(ids); out = set(); ext = []
        with self.lock:
            for c in self.combos.values():
                cs = set(c["ids"])
                if cs < s:
                    out.update(c["outcomes"]); ext.append(c["id"])
        return out, ext


def jact(a):
    return [list(x) if isinstance(x, tuple) else x for x in a]


def tact(a):
    return tuple(tuple(x) if isinstance(x, list) else x for x in a)


def make_combo(r, extends, run_id):
    names = [DB[k].name for k in r["ids"]]
    key = "|".join(sorted(names)) + "#" + ",".join(sorted(r["outcomes"]))
    cid = hashlib.sha1(key.encode()).hexdigest()[:10]
    per = describe.acc_str(r["delta"]) if any(r["delta"]) else ""
    grows = [o for o in r["outcomes"] if o in ("tokens", "counters")]
    claim = " + ".join(OUTCOME_LABEL[o] for o in r["outcomes"])
    return {
        "id": cid, "ids": r["ids"], "names": names, "size": len(names),
        "mv": sum(DB[k].mv for k in r["ids"]),
        "cards": [list(x) for x in r["cards"]], "float": list(r["float"]),
        "pre": [jact(a) for a in r["pre"]], "loop": [jact(a) for a in r["loop"]],
        "grade": r["grade"], "outcomes": r["outcomes"], "win": bool(WINS & set(r["outcomes"])),
        "delta": list(r["delta"]), "summary": [r["summary"][0], list(r["summary"][1])] if r["summary"] else None,
        "claim": claim, "per_iter": ", ".join(x for x in (per, "board grows" if grows else "") if x),
        "setup_mana": mana_total(r["float"]), "extends": extends, "found": time.time(), "run": run_id,
        "verify": {"status": "pending"},
    }


def cert_of(c):
    return {"id": c["id"], "names": c["names"], "claim": c["claim"], "grade": c["grade"],
            "cards": [tuple(x) for x in c["cards"]], "float": tuple(c["float"]),
            "pre": [tact(a) for a in c["pre"]], "loop": [tact(a) for a in c["loop"]],
            "delta": tuple(c["delta"]),
            "summary": (c["summary"][0], tuple(c["summary"][1])) if c["summary"] else None}


class Discovery:
    def __init__(self, bus, store):
        self.bus = bus; self.store = store
        self.thread = None; self.stop_flag = threading.Event()
        self.verifier = ThreadPoolExecutor(max_workers=3)
        self.state = {"running": False}
        self.history = []     # throughput samples for the monitor
        self.kernel = {"lean": leangen.lean_version(), "built": os.path.isdir(leangen.OLEAN_DIR), "log": ""}

    # -- kernel -------------------------------------------------------------
    def build_kernel(self):
        leangen.write_cards(DB)
        ok, log = leangen.build_kernel()
        self.kernel = {"lean": leangen.lean_version(), "built": ok, "log": log}
        self.bus.emit("log", level="ok" if ok else "err",
                      msg="Lean kernel built: theorems checked." if ok else "Lean kernel unavailable: " + log[-200:])
        return ok

    def submit_verify(self, c):
        c["verify"] = {"status": "queued"}
        self.store.put(c)
        self.verifier.submit(self._verify, c["id"])

    def _verify(self, cid):
        c = self.store.combos.get(cid)
        if not c: return
        c["verify"] = {"status": "checking"}
        self.bus.emit("verify", id=cid, status="checking")
        try:
            v = leangen.verify(cert_of(c))
        except Exception as ex:
            v = {"status": "rejected", "log": repr(ex), "tactic": "", "seconds": 0, "source": ""}
        c["verify"] = v; self.store.put(c)
        st = self.state.get("stats")
        if st is not None and c.get("run") == self.state.get("id"):
            st[v["status"]] = st.get(v["status"], 0) + 1
        self.bus.emit("verify", id=cid, status=v["status"], seconds=v.get("seconds"), tactic=v.get("tactic"),
                      names=c["names"], claim=c["claim"])
        if v["status"] == "rejected":
            self.bus.emit("log", level="err", msg=f"KERNEL REJECTED {' + '.join(c['names'])}: {v['log'][:160]}")
        self.store.save()

    def reverify_all(self):
        for c in list(self.store.combos.values()):
            self.submit_verify(c)

    # -- job ----------------------------------------------------------------
    def start(self, max_size=3, use_filter=True, include=(), max_nodes=2000, max_depth=12, workers=None):
        if self.state.get("running"): return False
        self.stop_flag.clear()
        cfg = {"max_size": max_size, "use_filter": use_filter, "include": list(include),
               "max_nodes": max_nodes, "max_depth": max_depth,
               "workers": workers or max(1, (os.cpu_count() or 2) - 1)}
        self.state = {"running": True, "id": int(time.time()), "cfg": cfg, "started": time.time(),
                      "phase": "starting", "stats": {"enumerated": 0, "passed": 0, "searched": 0, "nodes": 0,
                                                     "loops": 0, "novel": 0, "verified": 0, "rejected": 0,
                                                     "unavailable": 0, "errors": 0},
                      "sizes": {}}
        self.history = []
        self.thread = threading.Thread(target=self._run, args=(cfg,), daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.stop_flag.set()

    def _run(self, cfg):
        st = self.state["stats"]; bus = self.bus
        inc = [k for k in cfg["include"] if k in POOL]
        bus.emit("log", level="info", msg=f"Run started: sets up to {cfg['max_size']} cards from a pool of "
                 f"{len(POOL)}" + (f", containing {', '.join(DB[k].name for k in inc)}" if inc else "") +
                 f"; {cfg['workers']} workers.")
        if not self.kernel["built"]:
            self.build_kernel()
        pool = mp.get_context("fork").Pool(cfg["workers"], initializer=_winit)
        last_tick = 0; last_n = 0
        try:
            for k in range(max(2, len(inc)), cfg["max_size"] + 1):
                if self.stop_flag.is_set(): break
                rest = [x for x in POOL if x not in inc]
                all_sets = [tuple(sorted(inc + list(c))) for c in itertools.combinations(rest, k - len(inc))]
                cands = [s for s in all_sets if SYM.candidate(s)] if cfg["use_filter"] else all_sets
                sz = self.state["sizes"][str(k)] = {"enumerated": len(all_sets), "passed": len(cands),
                                                    "searched": 0, "novel": 0}
                st["enumerated"] += len(all_sets); st["passed"] += len(cands)
                self.state["phase"] = f"searching {k}-card sets"
                bus.emit("log", level="info", msg=f"{k}-card sets: {len(all_sets):,} enumerated, "
                         f"{len(cands):,} pass the symbolic filter ({100 * len(cands) / max(1, len(all_sets)):.0f}%).")
                tl = 4.0 if k <= 2 else 2.5
                jobs = ((list(s), cfg["max_nodes"], cfg["max_depth"], tl) for s in cands)
                # results are consumed in order so novelty is deterministic
                for ids, res, nodes, secs, err in pool.imap(_work, jobs, chunksize=4):
                    if self.stop_flag.is_set(): break
                    st["searched"] += 1; sz["searched"] += 1; st["nodes"] += nodes
                    if err:
                        st["errors"] += 1
                        bus.emit("log", level="err", msg=f"search error on {[DB[i].name for i in ids]}: {err}")
                    if res:
                        st["loops"] += len(res)
                        self._ingest(ids, res, sz)
                    now = time.time()
                    if now - last_tick > 0.5:
                        rate = (st["searched"] - last_n) / (now - last_tick) if last_tick else 0
                        last_tick = now; last_n = st["searched"]
                        self.history.append([round(now - self.state["started"], 1), round(rate, 1), st["novel"]])
                        self.history = self.history[-240:]
                        bus.emit("tick", state=self.snapshot())
                self.store.save()
        finally:
            pool.terminate()
            stopped = self.stop_flag.is_set()
            self.state["running"] = False
            self.state["phase"] = "stopped" if stopped else "finished"
            self.state["ended"] = time.time()
            self.store.runs.append({"id": self.state["id"], "cfg": cfg, "stats": dict(st),
                                    "seconds": round(self.state["ended"] - self.state["started"], 1),
                                    "stopped": stopped})
            self.store.runs = self.store.runs[-20:]
            self.store.save(force=True)
            bus.emit("log", level="ok", msg=f"Run {'stopped' if stopped else 'finished'}: {st['searched']:,} sets searched, "
                     f"{st['nodes']:,} states explored, {st['novel']} new combos.")
            bus.emit("tick", state=self.snapshot())

    def _ingest(self, ids, res, sz):
        known, ext = self.store.sub_outcomes(ids)
        covered = set(known)
        order = sorted(res, key=lambda r: (-len(set(r["outcomes"]) - known), r["grade"], len(r["loop"])))
        for r in order:
            new = set(r["outcomes"]) - covered
            if not new: continue
            covered |= set(r["outcomes"])
            c = make_combo(r, ext, self.state["id"])
            self.state["stats"]["novel"] += 1; sz["novel"] += 1
            self.store.put(c)
            self.bus.emit("combo", id=c["id"], names=c["names"], claim=c["claim"], grade=c["grade"], win=c["win"])
            self.bus.emit("log", level="find", msg=f"{' + '.join(c['names'])} → {c['claim']}")
            self.submit_verify(c)

    def snapshot(self):
        s = dict(self.state)
        if "started" in s:
            s["elapsed"] = round((s.get("ended") or time.time()) - s["started"], 1)
        s["history"] = self.history
        s["kernel"] = {k: v for k, v in self.kernel.items() if k != "log"}
        with self.store.lock:
            cs = list(self.store.combos.values())
        s["totals"] = {"combos": len(cs), "verified": sum(1 for c in cs if c["verify"]["status"] == "verified"),
                       "rejected": sum(1 for c in cs if c["verify"]["status"] == "rejected"),
                       "pending": sum(1 for c in cs if c["verify"]["status"] in ("pending", "queued", "checking")),
                       "wins": sum(1 for c in cs if c["win"]),
                       "inductive": sum(1 for c in cs if c["grade"] == "A")}
        return s
