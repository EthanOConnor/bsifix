"""Executable semantics (fast, untrusted mirror of lean/Manaproof/Step.lean).

Everything here is a line-by-line transliteration of the Lean kernel so that
the two can be differentially tested: every certificate the search emits is
re-executed by Lean, and any divergence shows up as a rejected certificate.
"""
from collections import namedtuple

W, U, B, R, G, C, LIFE, OPP, DRAW, MILL = range(10)
ACC_NAMES = ["w", "u", "b", "r", "g", "c", "life", "opp", "draw", "mill"]
ZERO = (0,) * 10

T_CREATURE, T_ARTIFACT, T_ENCHANTMENT, T_LEGENDARY, T_AURA, T_EQUIPMENT, T_PLANESWALKER = range(7)

Filter = namedtuple("Filter", "all no color nontoken other", defaults=((), (), -1, False, False))
Cost = namedtuple("Cost", "tap untap mana generic sac tapOther removeCtr putNeg life loyal",
                  defaults=(False, False, ZERO, 0, ("none",), None, 0, 0, 0, False))
Perm = namedtuple("Perm", "card tapped sick tok haste link used ctr neg att",
                  defaults=(False, False, False, False, False, False, 0, 0, -1))
Trig = namedtuple("Trig", "eff optional cost self n subj")
State = namedtuple("State", "bf stack acc")


class Card:
    __slots__ = ("name", "tags", "colors", "tough", "abilities", "grants", "enterCtr", "setupCtr",
                 "negReduce", "noNeg", "bonusC", "reduceHost", "enchant", "entersTapped", "mv", "text", "types",
                 "is_token", "power", "idx")

    def __init__(self, **kw):
        self.name = "?"; self.tags = (); self.colors = (); self.tough = 0
        self.abilities = (); self.grants = (); self.enterCtr = 0; self.setupCtr = 0
        self.negReduce = False; self.noNeg = False; self.bonusC = False; self.reduceHost = 0
        self.enchant = None; self.entersTapped = False; self.mv = 0; self.text = ""; self.types = ""; self.is_token = False
        self.power = 0; self.idx = -1
        for k, v in kw.items():
            setattr(self, k, v)


DUMMY = Card()


def acc(**kw):
    a = [0] * 10
    for k, v in kw.items():
        a[ACC_NAMES.index(k)] = v
    return tuple(a)


def acc_add(x, y): return tuple(a + b for a, b in zip(x, y))
def acc_sub(x, y): return tuple(max(a - b, 0) for a, b in zip(x, y))
def acc_le(x, y): return all(a <= b for a, b in zip(x, y))
def mana_total(x): return x[0] + x[1] + x[2] + x[3] + x[4] + x[5]
def pure_mana(x): return x[6] == 0 and x[7] == 0 and x[8] == 0 and x[9] == 0


def fix_idx(i, j):
    if j < 0: return -1
    if j == i: return -1
    return j - 1 if j > i else j


class Engine:
    def __init__(self, db):
        self.db = db
        self._abil = {}

    def card(self, i):
        return self.db[i] if 0 <= i < len(self.db) else DUMMY

    def is_creature(self, p):
        return T_CREATURE in self.card(p.card).tags

    def match(self, bf, i, self_i, f):
        if not (0 <= i < len(bf)): return False
        p = bf[i]; c = self.card(p.card)
        for t in f.all:
            if t not in c.tags: return False
        for t in f.no:
            if t in c.tags: return False
        if f.color >= 0 and f.color not in c.colors: return False
        if f.nontoken and p.tok: return False
        if f.other and self_i == i: return False
        return True

    def eff_abils(self, bf, i):
        key = (bf, i)
        r = self._abil.get(key)
        if r is not None: return r
        if not (0 <= i < len(bf)):
            r = ()
        else:
            out = list(self.card(bf[i].card).abilities)
            for j, q in enumerate(bf):
                for scope, ab in self.card(q.card).grants:
                    if scope[0] == "attached":
                        if q.att == i: out.append(ab)
                    elif self.match(bf, i, j, scope[1]):
                        out.append(ab)
            r = tuple(out)
        if len(self._abil) > 400000: self._abil.clear()
        self._abil[key] = r
        return r

    def has_kw(self, bf, i, k):
        return ("kw", k) in self.eff_abils(bf, i)

    def collect(self, bf, sel, n, subj):
        out = []
        for q in range(len(bf)):
            for a in self.eff_abils(bf, q):
                if a[0] == "trig" and sel(q, a[1]):
                    out.append(Trig(a[4], a[2], a[3], q, n, subj))
        return out

    # working state: [bf(list), stack(list), gain(tuple)]
    def gain_ev(self, st, a):
        bf = tuple(st[0])
        t1 = self.collect(bf, lambda q, on: on[0] == "lifeGain", a[LIFE], None) if a[LIFE] > 0 else []
        t2 = self.collect(bf, lambda q, on: on[0] == "oppLoss", a[OPP], None) if a[OPP] > 0 else []
        st[2] = acc_add(st[2], a)
        st[1] = t1 + t2 + st[1]

    def remove_at(self, st, i):
        bf = st[0]
        del bf[i]
        st[0] = [p._replace(att=fix_idx(i, p.att)) if p.att >= 0 else p for p in bf]
        st[1] = [t._replace(self=fix_idx(i, t.self)) if t.self >= 0 else t for t in st[1]]

    def die(self, st, i):
        bf = st[0]
        if not (0 <= i < len(bf)): return
        p = bf[i]
        if self.is_creature(p):
            tb = tuple(bf)
            sb = (p.card, p.tok)

            def sel(q, on):
                if on[0] == "diesSelf": return q == i
                if on[0] == "diesAny": return self.match(tb, i, q, on[1])
                return False
            ts = self.collect(tb, sel, 0, sb)
            k1 = [Trig((("ret", "neg"),), False, 0, -1, 0, sb)] if self.has_kw(tb, i, "persist") and p.neg == 0 else []
            k2 = [Trig((("ret", "ctr"),), False, 0, -1, 0, sb)] if self.has_kw(tb, i, "undying") and p.ctr == 0 else []
            st[1] = k1 + k2 + ts + st[1]
        self.remove_at(st, i)

    def etb_at(self, st, j):
        bf = tuple(st[0])

        def sel(q, on):
            if on[0] == "etbSelf": return q == j
            if on[0] == "etbOther": return q != j and self.match(bf, j, -1, on[1])
            return False
        st[1] = self.collect(bf, sel, 0, None) + st[1]

    def add_perm(self, st, p):
        st[0] = st[0] + [p]
        self.etb_at(st, len(st[0]) - 1)

    def new_perm(self, card, tok, haste):
        c = self.card(card)
        return Perm(card=card, tapped=c.entersTapped, sick=True, tok=tok, haste=haste, ctr=c.enterCtr)

    def put_ctr(self, st, j, n):
        if n == 0 or not (0 <= j < len(st[0])): return
        bf = st[0] = list(st[0])
        bf[j] = bf[j]._replace(ctr=bf[j].ctr + n)
        st[1] = self.collect(tuple(bf), lambda q, on: q == j and on[0] == "ctrSelf", 0, None) + st[1]

    def neg_amount(self, bf, n):
        if any(self.card(p.card).noNeg for p in bf): return None
        return max(n - sum(1 for p in bf if self.card(p.card).negReduce), 0)

    @staticmethod
    def color_acc(col, n):
        if not (0 <= col <= 5): return None
        a = [0] * 10; a[col] = n
        return tuple(a)

    def exec_eff(self, tap_for, n, subj, tgt, col, st, self_i, e):
        """Returns (ok, self_i)."""
        k = e[0]
        bf = st[0]
        if k == "gain":
            a = e[1]
            if tap_for and a[C] > 0:
                bonus = sum(1 for p in bf if self.card(p.card).bonusC)
                a = a[:C] + (a[C] + bonus,) + a[C + 1:]
            self.gain_ev(st, a); return True, self_i
        if k == "gainCtx":
            self.gain_ev(st, acc(life=n) if e[1] else acc(opp=n)); return True, self_i
        if k == "addAny":
            a = self.color_acc(col, e[1])
            if a is None: return False, self_i
            self.gain_ev(st, a); return True, self_i
        if k == "addPer":
            tb = tuple(bf)
            cnt = sum(1 for j in range(len(tb)) if self.match(tb, j, self_i, e[1]))
            a = self.color_acc(e[2], cnt)
            if a is None: return False, self_i
            self.gain_ev(st, a); return True, self_i
        if k == "addPerColor":
            a = [0] * 10
            for c in range(5):
                if any(c in self.card(p.card).colors for p in bf): a[c] = 1
            self.gain_ev(st, tuple(a)); return True, self_i
        if k == "untapSelf":
            if self_i >= 0 and self_i < len(bf):
                bf[self_i] = bf[self_i]._replace(tapped=False)
            return True, self_i
        if k == "untapTarget":
            if not self.match(tuple(bf), tgt, self_i, e[1]): return False, self_i
            bf[tgt] = bf[tgt]._replace(tapped=False); return True, self_i
        if k == "untapAll":
            tb = tuple(bf)
            st[0] = [p._replace(tapped=False) if self.match(tb, j, self_i, e[1]) else p for j, p in enumerate(tb)]
            return True, self_i
        if k == "token":
            for _ in range(e[2]):
                self.add_perm(st, self.new_perm(e[1], True, False))
            return True, self_i
        if k == "copyTarget":
            if not (0 <= tgt < len(bf)) or not self.match(tuple(bf), tgt, self_i, e[1]): return False, self_i
            self.add_perm(st, self.new_perm(bf[tgt].card, True, True)); return True, self_i
        if k == "blink":
            if not (0 <= tgt < len(bf)) or not self.match(tuple(bf), tgt, self_i, e[1]): return False, self_i
            p = bf[tgt]
            if p.tok:
                self.remove_at(st, tgt)
                return True, fix_idx(tgt, self_i)
            # a new object in the same slot: nothing refers to it any more
            bf[tgt] = self.new_perm(p.card, False, False)
            st[0] = [q._replace(att=-1) if q.att == tgt else q for q in bf]
            st[1] = [t._replace(self=-1) if t.self == tgt else t for t in st[1]]
            self.etb_at(st, tgt)
            return True, (-1 if self_i == tgt else self_i)
        if k == "ctrSelf":
            if self_i >= 0: self.put_ctr(st, self_i, e[1])
            return True, self_i
        if k == "ctrTarget":
            if not self.match(tuple(bf), tgt, self_i, e[1]): return False, self_i
            self.put_ctr(st, tgt, e[2]); return True, self_i
        if k == "ctrAll":
            for j in range(len(bf)):
                if self.match(tuple(st[0]), j, self_i, e[1]): self.put_ctr(st, j, e[2])
            return True, self_i
        if k == "ret":
            if subj is None or subj[1]: return True, self_i
            base = self.new_perm(subj[0], False, False)
            na = self.neg_amount(bf, 1)
            if e[1] == "neg": base = base._replace(neg=na or 0)
            elif e[1] == "ctr": base = base._replace(ctr=base.ctr + 1)
            j = len(bf)
            st[1] = [t._replace(subj=None) if t.subj == subj else t for t in st[1]]
            self.add_perm(st, base)
            if e[1] == "attach" and self_i >= 0 and self_i < len(st[0]):
                st[0][self_i] = st[0][self_i]._replace(att=j)
            return True, self_i
        if k == "lifelink":
            if not self.match(tuple(bf), tgt, self_i, e[1]): return False, self_i
            bf[tgt] = bf[tgt]._replace(link=True); return True, self_i
        if k == "ping":
            linked = 0 <= self_i < len(bf) and bf[self_i].link
            self.gain_ev(st, acc(opp=e[1], life=e[1] if linked else 0)); return True, self_i
        raise ValueError(k)

    def exec_effs(self, tap_for, n, subj, tgt, col, st, self_i, effs):
        for e in effs:
            ok, self_i = self.exec_eff(tap_for, n, subj, tgt, col, st, self_i, e)
            if not ok: return False
        return True

    def tough_eff(self, bf, i):
        p = bf[i]
        return self.card(p.card).tough + p.ctr + sum(a[1] for a in self.eff_abils(bf, i) if a[0] == "tough")

    def run_sba(self, st):
        bf = []
        for p in st[0]:
            m = min(p.ctr, p.neg)
            bf.append(p._replace(ctr=p.ctr - m, neg=p.neg - m) if m else p)
        st[0] = bf
        for _ in range(len(bf) + 1):
            tb = tuple(st[0]); hit = None
            for i, p in enumerate(tb):      # legend rule
                if T_LEGENDARY in self.card(p.card).tags and any(q.card == p.card for q in tb[:i]):
                    hit = i; break
            if hit is not None:
                self.die(st, hit); continue
            for i, p in enumerate(tb):
                if self.is_creature(p) and self.tough_eff(tb, i) <= p.neg:
                    hit = i; break
            if hit is not None:
                self.die(st, hit); continue
            for i, p in enumerate(tb):
                if T_AURA in self.card(p.card).tags and p.att < 0:
                    hit = i; break
            if hit is None: return
            self.remove_at(st, hit)

    def can_tap(self, bf, i, p):
        return (not self.is_creature(p)) or (not p.sick) or p.haste or self.has_kw(bf, i, "haste")

    def reduced_generic(self, bf, i, c):
        red = sum(self.card(q.card).reduceHost for q in bf if q.att == i)
        col = mana_total(c.mana)
        if red == 0: return col, c.generic
        if col == 0: return col, max(c.generic - red, min(c.generic, 1))
        return col, max(c.generic - red, 0)

    def pay_cost(self, st, i, c, pay, pick):
        bf = st[0]
        if not (0 <= i < len(bf)): return None
        p = bf[i]; tb = tuple(bf)
        if c.tap and (p.tapped or not self.can_tap(tb, i, p)): return None
        if c.untap and (not p.tapped or not self.can_tap(tb, i, p)): return None
        if c.tap and c.untap: return None
        if c.loyal and p.used: return None
        if c.removeCtr > p.ctr: return None
        neg_amt = 0
        if c.putNeg:
            neg_amt = self.neg_amount(bf, c.putNeg)
            if neg_amt is None: return None
        col, gen = self.reduced_generic(bf, i, c)
        if not (pure_mana(pay) and acc_le(c.mana, pay) and mana_total(pay) == col + gen): return None
        bf[i] = p._replace(tapped=True if c.tap else (False if c.untap else p.tapped),
                           used=p.used or c.loyal, ctr=p.ctr - c.removeCtr, neg=p.neg + neg_amt)
        if c.tapOther is not None:
            if not (0 <= pick < len(bf)): return None
            if not self.match(tuple(bf), pick, i, c.tapOther) or bf[pick].tapped: return None
            bf[pick] = bf[pick]._replace(tapped=True)
        cost_acc = pay[:LIFE] + (c.life,) + pay[LIFE + 1:]
        if c.sac[0] == "none": return i, cost_acc
        if c.sac[0] == "self":
            self.die(st, i); return -1, cost_acc
        if not self.match(tuple(bf), pick, i, c.sac[1]): return None
        self.die(st, pick)
        return fix_idx(pick, i), cost_acc

    def step(self, s, a):
        """a = ('act', i, k, pay, pick, tgt, col) | ('resolve', pay, tgt, col) | ('skip',)"""
        if a[0] == "act":
            _, i, k, pay, pick, tgt, col = a
            ab = self.eff_abils(s.bf, i)
            if not (0 <= k < len(ab)) or ab[k][0] != "act": return None
            c, effs = ab[k][1], ab[k][2]
            st = [list(s.bf), list(s.stack), ZERO]
            r = self.pay_cost(st, i, c, pay, pick)
            if r is None: return None
            self_i, cost_acc = r
            if not self.exec_effs(c.tap, 0, None, tgt, col, st, self_i, effs): return None
        elif a[0] == "resolve":
            _, pay, tgt, col = a
            if not s.stack: return None
            t = s.stack[0]
            if not (pure_mana(pay) and mana_total(pay) == t.cost): return None
            st = [list(s.bf), list(s.stack[1:]), ZERO]
            if not self.exec_effs(False, t.n, t.subj, tgt, col, st, t.self, t.eff): return None
            cost_acc = pay
        else:
            if not s.stack or not s.stack[0].optional: return None
            return State(s.bf, s.stack[1:], s.acc)
        self.run_sba(st)
        if not acc_le(cost_acc, s.acc): return None
        return State(tuple(st[0]), tuple(st[1]), acc_add(acc_sub(s.acc, cost_acc), st[2]))

    def run(self, s, actions):
        for a in actions:
            s = self.step(s, a)
            if s is None: return None
        return s

    def init_state(self, cards, float_acc):
        """cards: list of (card idx, att position or -1)."""
        bf = tuple(Perm(card=k, ctr=self.card(k).setupCtr, att=a) for k, a in cards)
        return State(bf, (), float_acc)

    def init_ok(self, bf):
        for p in bf:
            c = self.card(p.card)
            if c.enchant is None:
                if p.att >= 0: return False
            elif p.att >= 0:
                if not self.match(bf, p.att, -1, c.enchant): return False
            elif T_AURA in c.tags:
                return False
        return True
