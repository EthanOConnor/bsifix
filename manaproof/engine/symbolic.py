"""Symbolic layer: abstract each card to the resources it produces and needs.

This is a deliberately coarse abstraction (a resource hypergraph).  It is used
to prune card sets that cannot possibly feed each other before the concrete
search runs, and to draw the interaction graph in the UI.
"""
from .model import T_CREATURE, T_ARTIFACT, mana_total

RESOURCES = ["mana", "untap", "creature", "artifact", "etb", "death", "life", "opp", "ctr", "negfix",
             "draw", "mill"]


def _eff(e, db, prod, need=None):
    k = e[0]
    if k == "gain":
        a = e[1]
        if mana_total(a): prod.add("mana")
        if a[6]: prod.add("life")
        if a[7]: prod.add("opp")
        if a[8]: prod.add("draw")
        if a[9]: prod.add("mill")
    elif k == "gainCtx": prod.add("life" if e[1] else "opp")
    elif k in ("addAny", "addPer", "addPerColor"): prod.add("mana")
    elif k in ("untapSelf", "untapTarget", "untapAll"): prod.add("untap")
    elif k == "token":
        prod.update(("etb",))
        tc = db[e[1]]
        if T_CREATURE in tc.tags: prod.add("creature")
        if T_ARTIFACT in tc.tags: prod.add("artifact")
    elif k in ("copyTarget", "blink", "ret"):
        prod.update(("etb", "creature"))
        if k != "ret" and need is not None:      # needs something to copy / blink
            need.add("artifact" if T_ARTIFACT in e[1].all else "creature")
    elif k in ("ctrSelf", "ctrTarget", "ctrAll"): prod.add("ctr")
    elif k == "lifelink": prod.add("life")
    elif k == "ping": prod.add("opp")


def _ability(a, db, prod, need):
    if a[0] == "act":
        c = a[1]
        if c.tap: need.add("untap")
        if c.untap: prod.add("untap")
        if c.generic or mana_total(c.mana): need.add("mana")
        if c.sac[0] == "other":
            f = c.sac[1]
            need.add("artifact" if T_ARTIFACT in f.all else "creature")
            if T_CREATURE in f.all: prod.add("death")
        if c.sac[0] == "self": prod.add("death"); need.add("creature")   # something must bring it back
        if c.tapOther is not None: need.add("untap")
        if c.removeCtr: need.add("ctr")
        if c.putNeg: need.add("negfix"); prod.add("death")   # it can shrink itself to death
        if c.life: need.add("life")
        for e in a[2]: _eff(e, db, prod, need)
    elif a[0] == "trig":
        o = a[1][0]
        need.add({"etbSelf": "etb", "etbOther": "etb", "diesSelf": "death", "diesAny": "death",
                  "lifeGain": "life", "oppLoss": "opp", "ctrSelf": "ctr"}[o])
        if a[3]: need.add("mana")
        for e in a[4]: _eff(e, db, prod, need)
    elif a[0] == "kw":
        if a[1] == "persist":
            need.update(("death", "negfix")); prod.update(("etb", "creature"))
        elif a[1] == "undying":
            need.add("death"); prod.update(("etb", "creature"))


def signature(c, db):
    prod, need = set(), set()
    for a in c.abilities: _ability(a, db, prod, need)
    for _, a in c.grants: _ability(a, db, prod, need)
    if c.enchant is not None:        # an Aura/Equipment needs a host
        need.add("artifact" if T_ARTIFACT in c.enchant.all else "creature")
    if c.negReduce or c.noNeg: prod.add("negfix")
    if c.bonusC or c.reduceHost: prod.add("mana")
    if T_CREATURE in c.tags: prod.add("creature")
    if T_ARTIFACT in c.tags: prod.add("artifact")
    # a +1/+1 counter cancels a -1/-1 counter
    if "ctr" in prod: prod.add("negfix")
    return prod, need


class Symbolic:
    def __init__(self, db):
        self.db = db
        self.sig = [signature(c, db) for c in db]
        # "being a creature/artifact" only matters to someone else's sacrifice cost
        self.flow = {}
        n = len(db)
        for a in range(n):
            for b in range(n):
                r = self.sig[a][0] & self.sig[b][1]
                if a == b: r = r - {"creature", "artifact"}
                if r: self.flow[(a, b)] = sorted(r)

    def edges(self, ids):
        return [(a, b, self.flow[(a, b)]) for a in ids for b in ids if (a, b) in self.flow]

    def candidate(self, ids):
        """Could this set contain a resource cycle that involves every card?"""
        ids = list(ids)
        adj = {a: [b for b in ids if (a, b) in self.flow] for a in ids}
        # weakly connected
        und = {a: set() for a in ids}
        for a in ids:
            for b in adj[a]:
                und[a].add(b); und[b].add(a)
        seen = {ids[0]}; todo = [ids[0]]
        while todo:
            for y in und[todo.pop()]:
                if y not in seen: seen.add(y); todo.append(y)
        if len(seen) != len(ids): return False
        # contains a directed cycle (self-loops count)
        color = {}
        def dfs(u):
            color[u] = 1
            for v in adj[u]:
                if color.get(v) == 1: return True
                if v not in color and dfs(v): return True
            color[u] = 2
            return False
        return any(a not in color and dfs(a) for a in ids)
