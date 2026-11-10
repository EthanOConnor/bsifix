"""Manaproof web server: JSON API + server-sent events + static UI.  Stdlib only."""
import argparse, json, mimetypes, os, queue, re, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .model import ZERO, ACC_NAMES, State, acc_le
from .pool import DB, POOL, BY_NAME
from . import describe, leangen, search
from .discover import Bus, Store, Discovery, E, SYM, ROOT, tact, jact, cert_of, OUTCOME_LABEL

WEB = os.path.join(ROOT, "web")
bus = Bus(); store = Store(); disco = Discovery(bus, store)


def card_view(c):
    prod, need = SYM.sig[c.idx]
    return {"id": c.idx, "name": c.name, "types": c.types, "colors": list(c.colors), "mv": c.mv,
            "pt": [c.power, c.tough] if 0 in c.tags else None, "text": c.text, "token": c.is_token,
            "dsl": describe.card_dsl(c, DB), "lean": leangen.card(c),
            "produces": sorted(prod), "needs": sorted(need),
            "attach": c.enchant is not None}


def combo_light(c):
    return {k: c[k] for k in ("id", "names", "ids", "size", "mv", "grade", "outcomes", "win", "claim",
                              "per_iter", "setup_mana", "extends", "found")} | {
        "status": c["verify"]["status"], "steps": len(c["loop"]), "tactic": c["verify"].get("tactic", "")}


def frames(cards, float_acc, actions):
    """Replay actions; returns list of {state, action text} (stops at the first illegal action)."""
    s = E.init_state(cards, float_acc)
    out = [{"state": describe.state_view(E, s), "action": None}]
    states = [s]
    for a in actions:
        try:
            txt = describe.action(E, s, a)
        except Exception:
            txt = "?"
        t = E.step(s, a)
        if t is None:
            out.append({"state": None, "action": txt, "illegal": True}); break
        s = t; states.append(s)
        out.append({"state": describe.state_view(E, s), "action": txt})
    return out, states


def combo_full(c):
    pre = [tact(a) for a in c["pre"]]; loop = [tact(a) for a in c["loop"]]
    reps = 2 if c["grade"] == "A" else 3
    fr, _ = frames([tuple(x) for x in c["cards"]], tuple(c["float"]), pre + loop * reps)
    for i, f in enumerate(fr[1:], 1):
        f["phase"] = "setup" if i <= len(pre) else "loop"
        f["iter"] = 0 if i <= len(pre) else (i - len(pre) - 1) // max(1, len(loop)) + 1
    v = c["verify"]
    src = v.get("source") or leangen.cert_source(cert_of(c))
    return dict(c, frames=fr, lean=src,
                requires=describe.acc_str(tuple(c["float"][:6]) + (0, 0, 0, 0)),
                delta_text=describe.acc_str(tuple(c["delta"])),
                extends_full=[combo_light(store.combos[x]) for x in c["extends"] if x in store.combos])


def sandbox(body):
    names = body.get("cards", [])
    cards = []
    for x in names:
        k = BY_NAME.get(x["name"])
        if k is None: return {"error": f"unknown card {x['name']}"}
        cards.append((k, int(x.get("att", -1))))
    fl = [0] * 10
    for k, v in (body.get("float") or {}).items():
        if k in ACC_NAMES: fl[ACC_NAMES.index(k)] = int(v)
    if not fl[6]: fl[6] = 20
    s0 = E.init_state(cards, tuple(fl))
    if not E.init_ok(s0.bf):
        return {"error": "Illegal setup: every Aura needs a legal host (set its “attached to”)."}
    actions = [tact(a) for a in body.get("actions", [])]
    fr, states = frames(cards, tuple(fl), actions)
    s = states[-1]
    cols = list(range(5))
    legal = []
    for a in search.legal_actions(E, s, cols):
        if E.step(s, a) is not None:
            legal.append({"a": jact(a), "text": describe.action(E, s, a)})
    loop = None
    for i in range(len(states) - 2, -1, -1):
        p = states[i]
        if p.bf == s.bf and p.stack == s.stack and acc_le(p.acc, s.acc) and p.acc != s.acc:
            loop = {"from": i, "grade": "A", "gain": describe.acc_str(tuple(b - a for a, b in zip(p.acc, s.acc)))}
            break
        if search.grows(p, s):
            loop = {"from": i, "grade": "B", "gain": ", ".join(search.outcome(p, s)) or "board"}
            break
    return {"frames": fr, "legal": legal, "loop": loop}


def sandbox_search(body):
    ids = [BY_NAME[x["name"]] for x in body.get("cards", []) if x["name"] in BY_NAME]
    if not (1 <= len(ids) <= 5): return {"error": "pick 1–5 cards"}
    t = time.time()
    res, nodes = search.search_set(E, ids, 6000, 14, 10.0)
    out = []
    for r in res:
        out.append({"grade": r["grade"], "outcomes": r["outcomes"],
                    "claim": " + ".join(OUTCOME_LABEL[o] for o in r["outcomes"]),
                    "cards": [{"name": DB[k].name, "att": a} for k, a in r["cards"]],
                    "float": dict(zip(ACC_NAMES, r["float"])),
                    "pre": [jact(a) for a in r["pre"]], "loop": [jact(a) for a in r["loop"]],
                    "gain": describe.acc_str(r["delta"])})
    return {"results": out, "nodes": nodes, "seconds": round(time.time() - t, 2)}


def kernel_view():
    files = []
    for name in ("Basic", "Model", "Step", "Theorems", "Cards"):
        p = os.path.join(leangen.LEAN_DIR, "Manaproof", name + ".lean")
        if os.path.exists(p):
            src = open(p).read()
            files.append({"name": name + ".lean", "source": src if name != "Cards" else src[:6000] + "\n-- … (generated; truncated)",
                          "lines": src.count("\n")})
    thms = []
    for f in files:
        for m in re.finditer(r"(?:^/--((?:(?!-/).)*)-/\s*)?^theorem (\w+)", f["source"], re.S | re.M):
            thms.append({"name": m.group(2), "file": f["name"], "doc": " ".join((m.group(1) or "").split())})
    return {"files": files, "theorems": thms, "kernel": disco.kernel}


def graph_view():
    with store.lock:
        cs = list(store.combos.values())
    deg = {}
    for c in cs:
        for k in c["ids"]: deg[k] = deg.get(k, 0) + 1
    pair = {}
    for c in cs:
        ids = c["ids"]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                key = (ids[i], ids[j])
                e = pair.setdefault(key, {"a": ids[i], "b": ids[j], "n": 0, "win": False, "pair": False})
                e["n"] += 1; e["win"] = e["win"] or c["win"]; e["pair"] = e["pair"] or c["size"] == 2
    flows = [{"a": a, "b": b, "r": r} for (a, b), r in SYM.flow.items()
             if a != b and not DB[a].is_token and not DB[b].is_token]
    return {"nodes": [{"id": k, "name": DB[k].name, "colors": list(DB[k].colors), "combos": deg.get(k, 0)} for k in POOL],
            "combo_edges": list(pair.values()), "flows": flows}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a): pass

    def send_json(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(data)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        p = self.path.split("?")[0]
        try:
            if p == "/api/status": return self.send_json(disco.snapshot())
            if p == "/api/cards": return self.send_json([card_view(c) for c in DB])
            if p == "/api/combos":
                with store.lock:
                    return self.send_json([combo_light(c) for c in store.combos.values()])
            if p.startswith("/api/combo/"):
                c = store.combos.get(p.rsplit("/", 1)[1])
                return self.send_json(combo_full(c)) if c else self.send_json({"error": "not found"}, 404)
            if p == "/api/graph": return self.send_json(graph_view())
            if p == "/api/kernel": return self.send_json(kernel_view())
            if p == "/api/runs": return self.send_json(store.runs)
            if p == "/api/events": return self.sse()
        except BrokenPipeError:
            return
        except Exception as ex:
            return self.send_json({"error": repr(ex)}, 500)
        f = os.path.normpath(os.path.join(WEB, "index.html" if p == "/" else p.lstrip("/")))
        if not f.startswith(WEB) or not os.path.isfile(f):
            return self.send_json({"error": "not found"}, 404)
        data = open(f, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(f)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(data)

    def do_POST(self):
        p = self.path
        try:
            b = self.body()
            if p == "/api/job/start":
                inc = [BY_NAME[n] for n in b.get("include", []) if n in BY_NAME]
                ok = disco.start(max_size=max(2, min(4, int(b.get("max_size", 3)))),
                                 use_filter=bool(b.get("use_filter", True)), include=inc,
                                 max_nodes=max(200, min(20000, int(b.get("max_nodes", 2000)))),
                                 max_depth=max(4, min(20, int(b.get("max_depth", 12)))))
                return self.send_json({"ok": ok})
            if p == "/api/job/stop":
                disco.stop(); return self.send_json({"ok": True})
            if p == "/api/kernel/build":
                threading.Thread(target=disco.build_kernel, daemon=True).start()
                return self.send_json({"ok": True})
            if p == "/api/verify/all":
                disco.reverify_all(); return self.send_json({"ok": True})
            if p.startswith("/api/verify/"):
                c = store.combos.get(p.rsplit("/", 1)[1])
                if c: disco.submit_verify(c)
                return self.send_json({"ok": bool(c)})
            if p == "/api/sandbox": return self.send_json(sandbox(b))
            if p == "/api/sandbox/search": return self.send_json(sandbox_search(b))
            if p == "/api/clear":
                if disco.state.get("running"): return self.send_json({"ok": False})
                with store.lock:
                    store.combos.clear(); store._dirty = True
                store.save(); return self.send_json({"ok": True})
        except Exception as ex:
            return self.send_json({"error": repr(ex)}, 500)
        self.send_json({"error": "not found"}, 404)

    def sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        q = bus.subscribe()
        try:
            for ev in list(bus.recent)[-150:]:
                self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode())
            self.wfile.flush()
            while True:
                try:
                    ev = q.get(timeout=10)
                    self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            bus.unsubscribe(q)
            self.close_connection = True


def main():
    ap = argparse.ArgumentParser(description="Manaproof — verified combo discovery")
    ap.add_argument("--port", type=int, default=8642)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--discover", type=int, metavar="N", help="start a discovery run up to N-card sets on launch")
    args = ap.parse_args()
    if leangen.write_cards(DB) or not disco.kernel["built"]:
        threading.Thread(target=disco.build_kernel, daemon=True).start()
    if args.discover: disco.start(max_size=args.discover)
    srv = ThreadingHTTPServer((args.host, args.port), H)
    srv.daemon_threads = True
    print(f"Manaproof: http://{args.host}:{args.port}  (Lean: {disco.kernel['lean'] or 'not found'})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        store.save(force=True)


if __name__ == "__main__":
    main()
