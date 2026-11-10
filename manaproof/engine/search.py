"""Concrete loop search (untrusted).

Breadth-first exploration of the goldfish game tree for a small set of cards,
looking for a path that revisits a board configuration with more resources.
Borrowing from Karp–Miller coverability trees, once a resource loop is found
the search *accelerates*: it jumps to a state where that loop has been run
several times and keeps going, which is how mana engines get connected to the
payoffs that consume the mana.
"""
import itertools, time
from collections import deque
from .model import (Engine, State, ZERO, acc, acc_add, acc_le, mana_total, T_AURA)
from .leangen import K_BOUNDED

F0 = acc(w=1, u=1, b=1, r=1, g=1, c=4, life=20)
BASE = acc(life=20)
N_ACCEL = 6
TARGETED = ("untapTarget", "copyTarget", "blink", "ctrTarget", "lifelink")


def needs_tgt(effs): return any(e[0] in TARGETED for e in effs)
def needs_col(effs): return any(e[0] == "addAny" for e in effs)


def useful_colors(E, ids):
    need = set()
    def scan(a):
        if a[0] == "act":
            for i in range(5):
                if a[1].mana[i]: need.add(i)
    for k in ids:
        c = E.card(k)
        for a in c.abilities: scan(a)
        for _, a in c.grants: scan(a)
    return sorted(need) or [0]


def payments(pool, need, generic):
    rem = [pool[i] - need[i] for i in range(6)]
    if min(rem) < 0 or generic > sum(rem): return ()
    if generic == 0: return (tuple(need[:6]) + (0, 0, 0, 0),)
    cols = sorted(range(5), key=lambda i: -rem[i])
    opts = []
    for order in ([5] + cols, cols + [5]):
        pay = list(need[:6]); g = generic
        for i in order:
            t = min(g, rem[i]); pay[i] += t; g -= t
        p = tuple(pay) + (0, 0, 0, 0)
        if p not in opts: opts.append(p)
    # balanced: always draw from the largest pile, which keeps colour ratios stable across iterations
    pay = list(need[:6]); r = rem[:]
    for _ in range(generic):
        i = max(range(6), key=lambda j: r[j]); pay[i] += 1; r[i] -= 1
    p = tuple(pay) + (0, 0, 0, 0)
    if p not in opts: opts.append(p)
    return opts


def legal_actions(E, s, cols):
    """Candidate actions (a superset; `Engine.step` is the judge)."""
    out = []
    bf = s.bf; n = len(bf)
    if s.stack:
        t = s.stack[0]
        tg = range(n) if needs_tgt(t.eff) else (0,)
        cl = cols if needs_col(t.eff) else (0,)
        for pay in payments(s.acc, ZERO, t.cost):
            for a in tg:
                for c in cl: out.append(("resolve", pay, a, c))
        if t.optional: out.append(("skip",))
    for i in range(n):
        p = bf[i]
        for k, ab in enumerate(E.eff_abils(bf, i)):
            if ab[0] != "act": continue
            c = ab[1]
            if (c.tap and p.tapped) or (c.untap and not p.tapped) or c.removeCtr > p.ctr: continue
            _, gen = E.reduced_generic(bf, i, c)
            pays = payments(s.acc, c.mana, gen)
            if not pays: continue
            picks = range(n) if (c.tapOther is not None or c.sac[0] == "other") else (0,)
            tg = range(n) if needs_tgt(ab[2]) else (0,)
            cl = cols if needs_col(ab[2]) else (0,)
            for pay in pays:
                for pk in picks:
                    for a in tg:
                        for cc in cl: out.append(("act", i, k, pay, pk, a, cc))
    return out


def perm_grow(p, q): return q._replace(ctr=p.ctr) == p and p.ctr <= q.ctr


def bf_grow(a, b):
    return len(a) <= len(b) and all(perm_grow(p, q) for p, q in zip(a, b))


def grows(s, t):
    return s.stack == t.stack and bf_grow(s.bf, t.bf) and acc_le(s.acc, t.acc) and s != t


def outcome(s, t):
    """Which quantities does one loop iteration s -> t increase?"""
    out = []
    if any(t.acc[i] > s.acc[i] for i in range(6)): out.append("mana")
    for i, name in ((6, "life"), (7, "damage"), (8, "draw"), (9, "mill")):
        if t.acc[i] > s.acc[i]: out.append(name)
    if len(t.bf) > len(s.bf): out.append("tokens")
    if any(q.ctr > p.ctr for p, q in zip(s.bf, t.bf)): out.append("counters")
    return out


def check_cert(E, cards, float_acc, pre, loop, grade):
    """Re-execute a certificate.  Returns dict(delta|summary, outcomes) or None."""
    s0 = E.init_state(cards, float_acc)
    if not E.init_ok(s0.bf): return None
    s = E.run(s0, pre)
    if s is None: return None
    t = E.run(s, loop)
    if t is None: return None
    if grade == "A":
        if not (t.bf == s.bf and t.stack == s.stack and acc_le(s.acc, t.acc) and t.acc != s.acc): return None
        return {"delta": tuple(b - a for a, b in zip(s.acc, t.acc)), "outcomes": outcome(s, t)}
    cur = s
    for _ in range(K_BOUNDED):
        nxt = E.run(cur, loop)
        if nxt is None or not grows(cur, nxt): return None
        cur = nxt
    return {"summary": (len(cur.bf), cur.acc), "outcomes": outcome(s, t),
            "delta": tuple(b - a for a, b in zip(s.acc, t.acc))}


class _Node:
    __slots__ = ("parent", "seg", "depth", "bases", "naccel")

    def __init__(self, parent, seg, depth, bases, naccel):
        self.parent = parent; self.seg = seg; self.depth = depth; self.bases = bases; self.naccel = naccel


def _search_setup(E, cards, cols, max_nodes, max_depth, deadline, found, f0):
    s0 = E.init_state(cards, f0)
    if not E.init_ok(s0.bf): return 0
    nodes = {s0: _Node(None, (), 0, (), 0)}
    queue = deque([s0])

    def path(st):
        segs = []
        while st is not None:
            nd = nodes[st]; segs.append(nd.seg); st = nd.parent
        return [a for seg in reversed(segs) for a in seg]

    def record(anc, loop, grade):
        pre = path(anc)
        res = check_cert(E, cards, f0, pre, loop, grade)
        if res is None: return False
        sig = tuple(res["outcomes"])
        rank = (grade, len(loop), len(pre))
        if sig not in found or rank < found[sig]["rank"]:
            found[sig] = {"rank": rank, "cards": list(cards), "pre": pre, "loop": list(loop), "grade": grade, "f0": f0}
        return True

    while queue and len(nodes) < max_nodes:
        if time.time() > deadline: break
        s = queue.popleft(); nd = nodes[s]
        if nd.depth >= max_depth: continue
        for a in legal_actions(E, s, cols):
            t = E.step(s, a)
            if t is None or t in nodes: continue
            nodes[t] = node = _Node(s, (a,), nd.depth + 1, nd.bases, nd.naccel)
            # compare with ancestors, nearest first
            trace = [a]; anc = s; pruned = False; seen_b = False
            while anc is not None:
                an = nodes[anc]
                if anc.bf == t.bf and anc.stack == t.stack:
                    d = [y - x for x, y in zip(anc.acc, t.acc)]
                    if min(d) >= 0 and max(d) > 0:
                        loop = trace_fwd(trace)
                        if record(anc, loop, "A"):
                            pruned = True
                            covered = {j for _, bd in an.bases for j in range(10) if bd[j] > 0}
                            if any(d[i] > 0 and i not in covered for i in range(7)) and an.naccel < 3:
                                boost = State(anc.bf, anc.stack, tuple(x + N_ACCEL * y for x, y in zip(anc.acc, d)))
                                if boost not in nodes:
                                    nodes[boost] = _Node(anc, tuple(loop) * N_ACCEL, an.depth,
                                                         an.bases + ((tuple(loop), tuple(d)),), an.naccel + 1)
                                    queue.appendleft(boost)
                            break
                    elif an.bases and max(d) > 0:
                        # deficits may be covered by loops we already know how to pump
                        mult = {}
                        ok = True
                        for j in range(10):
                            if d[j] < 0:
                                b = next((bi for bi, (_, bd) in enumerate(an.bases) if bd[j] > 0), None)
                                if b is None: ok = False; break
                                bd = an.bases[b][1]
                                mult[b] = max(mult.get(b, 0), -(-(-d[j]) // bd[j]))
                        if ok and mult and max(mult.values()) <= N_ACCEL:
                            loop = []
                            for b, m in mult.items(): loop += list(an.bases[b][0]) * m
                            loop += trace_fwd(trace)
                            if record(anc, loop, "A"):
                                pruned = True
                                break
                elif not seen_b and grows(anc, t):
                    seen_b = True
                    record(anc, trace_fwd(trace), "B")
                if len(an.seg) != 1: break      # never look past an acceleration point
                trace.append(an.seg[0]); anc = an.parent
            if not pruned: queue.append(t)
    return len(nodes)


def trace_fwd(trace):
    return list(reversed(trace))


def setups(E, ids):
    """Every legal way to attach the auras/equipment in the set."""
    opts = []
    for pos, k in enumerate(ids):
        c = E.card(k)
        if c.enchant is None:
            opts.append([-1]); continue
        bf = tuple(E.init_state([(x, -1) for x in ids], ZERO).bf)
        hosts = [h for h in range(len(ids)) if h != pos and E.match(bf, h, -1, c.enchant)]
        if T_AURA not in c.tags: hosts.append(-1)
        if not hosts: return []
        opts.append(hosts)
    return [list(zip(ids, combo)) for combo in itertools.islice(itertools.product(*opts), 8)]


def repay(E, r):
    """Re-pay every generic cost with colourless mana where possible."""
    big = acc(w=1, u=1, b=1, r=1, g=1, c=12, life=20)
    s = E.init_state(r["cards"], big)
    out = []
    for a in r["pre"] + r["loop"] + r["loop"]:
        if a[0] == "skip":
            b = a
        else:
            if a[0] == "resolve":
                need, gen = ZERO, s.stack[0].cost if s.stack else 0
            else:
                ab = E.eff_abils(s.bf, a[1])
                if a[2] >= len(ab) or ab[a[2]][0] != "act": return None
                need = ab[a[2]][1].mana; gen = E.reduced_generic(s.bf, a[1], ab[a[2]][1])[1]
            pays = payments(s.acc, need, gen)
            if not pays: return None
            b = (a[0], pays[0]) + a[2:] if a[0] == "resolve" else a[:3] + (pays[0],) + a[4:]
        s = E.step(s, b)
        if s is None: return None
        out.append(b)
    n, m = len(r["pre"]), len(r["loop"])
    if out[n:n + m] != out[n + m:]: return None
    return out[:n], out[n:n + m]


def minimise_float(E, r, start=F0):
    fl = list(start)
    for i in range(6):
        while fl[i] > 0:
            fl[i] -= 1
            if check_cert(E, r["cards"], tuple(fl), r["pre"], r["loop"], r["grade"]) is None:
                fl[i] += 1; break
    return tuple(fl)


def search_set(E, ids, max_nodes=2500, max_depth=12, time_limit=6.0):
    """Find loops for one set of cards.  Returns (results, nodes_expanded)."""
    cols = useful_colors(E, ids)
    total = 0; best = {}
    deadline = time.time() + time_limit
    # first with an empty mana pool, then with some mana floating (for loops that need a kick-start)
    for f0 in (BASE, F0):
        found = {}
        for cards in setups(E, ids):
            total += _search_setup(E, cards, cols, max_nodes, max_depth, deadline, found, f0)
        for sig, r in found.items():
            if f0 == BASE:
                fl = BASE
            else:
                fl = minimise_float(E, r)
                alt = repay(E, r)
                if alt:
                    big = acc(w=1, u=1, b=1, r=1, g=1, c=12, life=20)
                    r2 = dict(r, pre=alt[0], loop=alt[1])
                    if check_cert(E, r["cards"], big, alt[0], alt[1], r["grade"]) is not None:
                        f2 = minimise_float(E, r2, big)
                        if mana_total(f2) <= mana_total(fl): r, fl = r2, f2
            res = check_cert(E, r["cards"], fl, r["pre"], r["loop"], r["grade"])
            if res is None: continue
            rank = (r["grade"], mana_total(fl), len(r["loop"]) + len(r["pre"]))
            if sig not in best or rank < best[sig][0]:
                best[sig] = (rank, {"ids": list(ids), "cards": r["cards"], "float": fl, "pre": r["pre"],
                                    "loop": r["loop"], "grade": r["grade"], "outcomes": res["outcomes"],
                                    "delta": res["delta"], "summary": res.get("summary")})
    return [v[1] for v in best.values()], total
