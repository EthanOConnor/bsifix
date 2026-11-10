"""Human-readable rendering of DSL programs, states and actions."""
from .model import ACC_NAMES, mana_total, T_CREATURE
from .dsl import TAGS

TAG_NAME = {}
SYM = ["W", "U", "B", "R", "G", "C"]


def _tagname(t):
    if not TAG_NAME or len(TAG_NAME) != len(TAGS):
        TAG_NAME.update({v: k for k, v in TAGS.items()})
    return TAG_NAME.get(t, f"tag{t}")


def mana_str(a, generic=0):
    s = ("{%d}" % generic) if generic else ""
    for i in range(6):
        s += ("{%s}" % SYM[i]) * a[i]
    return s


def acc_str(a):
    parts = []
    m = mana_str(a)
    if m: parts.append(m)
    for i, label in ((6, "life"), (7, "opponent life lost"), (8, "cards drawn"), (9, "cards milled")):
        if a[i]: parts.append(f"{a[i]} {label}")
    return ", ".join(parts) or "nothing"


def filt(f):
    if f is None: return ""
    words = []
    if f.other: words.append("another")
    if f.nontoken: words.append("nontoken")
    if f.color >= 0: words.append(["white", "blue", "black", "red", "green"][f.color])
    words += ["non-" + _tagname(t) for t in f.no]
    words += [_tagname(t) for t in f.all]
    if not f.all: words.append("permanent")
    return " ".join(words)


def effect(e, db=None):
    k = e[0]
    if k == "gain":
        a = e[1]; parts = []
        if mana_total(a): parts.append("add " + mana_str(a))
        if a[6]: parts.append(f"gain {a[6]} life")
        if a[7]: parts.append(f"opponent loses {a[7]} life")
        if a[8]: parts.append(f"draw {a[8]}")
        if a[9]: parts.append(f"opponent mills {a[9]}")
        return ", ".join(parts) or "no modelled effect"
    if k == "gainCtx": return "gain that much life" if e[1] else "opponent loses that much life"
    if k == "addAny": return f"add {e[1]} mana of one colour"
    if k == "addPer": return f"add {{{SYM[e[2]]}}} for each {filt(e[1])}"
    if k == "addPerColor": return "add one mana of each colour among your permanents"
    if k == "untapSelf": return "untap this"
    if k == "untapTarget": return f"untap target {filt(e[1])}"
    if k == "untapAll": return f"untap each {filt(e[1])}"
    if k == "token":
        name = db[e[1]].name if db and isinstance(e[1], int) else str(e[1])
        return f"create {e[2]} {name} token" + ("s" if e[2] > 1 else "")
    if k == "copyTarget": return f"create a hasty token copy of target {filt(e[1])}"
    if k == "blink": return f"exile target {filt(e[1])}, then return it"
    if k == "ctrSelf": return f"put {e[1]} counter on this"
    if k == "ctrTarget": return f"put {e[2]} +1/+1 counter on target {filt(e[1])}"
    if k == "ctrAll": return f"put {e[2]} +1/+1 counter on each {filt(e[1])}"
    if k == "ret": return {"plain": "return it to the battlefield", "attach": "return it and attach this",
                           "neg": "return it with a -1/-1 counter (persist)",
                           "ctr": "return it with a +1/+1 counter (undying)"}[e[1]]
    if k == "lifelink": return f"target {filt(e[1])} gains lifelink"
    if k == "ping": return f"deal {e[1]} damage to the opponent"
    return k


def effects(es, db=None):
    return "; ".join(effect(e, db) for e in es) or "no modelled effect"


def cost(c):
    parts = []
    m = mana_str(c.mana, c.generic)
    if m: parts.append(m)
    if c.tap: parts.append("{T}")
    if c.untap: parts.append("{Q}")
    if c.loyal: parts.append("loyalty" + (f" −{c.removeCtr}" if c.removeCtr else " +"))
    elif c.removeCtr: parts.append(f"remove {c.removeCtr} counter")
    if c.putNeg: parts.append(f"put {c.putNeg} -1/-1 counter on this")
    if c.life: parts.append(f"pay {c.life} life")
    if c.tapOther is not None: parts.append(f"tap an untapped {filt(c.tapOther)}")
    if c.sac[0] == "self": parts.append("sacrifice this")
    elif c.sac[0] == "other": parts.append(f"sacrifice a {filt(c.sac[1])}")
    return ", ".join(parts) or "{0}"


ON = {"etbSelf": "When this enters", "diesSelf": "When this dies", "lifeGain": "Whenever you gain life",
      "oppLoss": "Whenever the opponent loses life", "ctrSelf": "Whenever counters are put on this"}


def on(o):
    if o[0] == "etbOther": return f"Whenever another {filt(o[1])} enters"
    if o[0] == "diesAny": return f"Whenever a {filt(o[1])} dies"
    return ON[o[0]]


def ability(a, db=None):
    if a[0] == "act": return f"{cost(a[1])}: {effects(a[2], db)}"
    if a[0] == "trig":
        may = "you may " if a[2] and not a[3] else ""
        pay = f"you may pay {{{a[3]}}}; if you do, " if a[3] else ""
        return f"{on(a[1])}, {pay}{may}{effects(a[4], db)}"
    if a[0] == "kw": return a[1].capitalize()
    return f"+0/+{a[1]}"


def card_dsl(c, db):
    """Structured view of a card's program."""
    out = [{"kind": a[0], "text": ability(a, db)} for a in c.abilities]
    for scope, a in c.grants:
        who = "attached permanent" if scope[0] == "attached" else "each " + filt(scope[1])
        out.append({"kind": "grant", "text": f"Grants {who}: {ability(a, db)}"})
    for flag, text in (("negReduce", "Static: -1/-1 counters placed are reduced by one"),
                       ("noNeg", "Static: -1/-1 counters can't be placed"),
                       ("bonusC", "Static: tapping for {C} adds one extra {C}")):
        if getattr(c, flag): out.append({"kind": "static", "text": text})
    if c.entersTapped: out.append({"kind": "static", "text": "Enters tapped"})
    if c.reduceHost: out.append({"kind": "static", "text": f"Static: attached permanent's abilities cost {{{c.reduceHost}}} less"})
    if c.enchant is not None: out.append({"kind": "static", "text": f"Attaches to: {filt(c.enchant)}"})
    if c.setupCtr or c.enterCtr:
        out.append({"kind": "static", "text": f"Counters: {c.setupCtr} at setup, {c.enterCtr} on entering"})
    return out


def perm_view(E, bf, i):
    p = bf[i]; c = E.card(p.card)
    return {"i": i, "card": p.card, "name": c.name, "tapped": p.tapped, "sick": p.sick, "token": p.tok,
            "haste": p.haste, "link": p.link, "used": p.used, "ctr": p.ctr, "neg": p.neg, "att": p.att,
            "colors": list(c.colors), "types": c.types, "creature": T_CREATURE in c.tags}


def state_view(E, s):
    return {"bf": [perm_view(E, s.bf, i) for i in range(len(s.bf))],
            "stack": [{"text": effects(t.eff, E.db), "optional": t.optional, "cost": t.cost,
                       "source": (E.card(s.bf[t.self].card).name if 0 <= t.self < len(s.bf)
                                  else (E.card(t.subj[0]).name if t.subj else "—")),
                       "n": t.n} for t in s.stack],
            "acc": dict(zip(ACC_NAMES, s.acc))}


def action(E, s, a):
    """Describe action `a` taken in state `s`."""
    def nm(i):
        return E.card(s.bf[i].card).name + (" token" if s.bf[i].tok else "") if 0 <= i < len(s.bf) else "?"
    if a[0] == "skip": return "Decline the optional trigger"
    if a[0] == "resolve":
        t = s.stack[0]
        src = nm(t.self) if t.self >= 0 else (E.card(t.subj[0]).name if t.subj else "trigger")
        txt = f"Resolve {src}'s trigger: {effects(t.eff, E.db)}"
        if t.cost: txt += f" (pay {mana_str(a[1])})"
        return txt + _choices(E, s, t.eff, a[2], a[3], nm)
    _, i, k, pay, pick, tgt, col = a
    ab = E.eff_abils(s.bf, i)[k]
    c = ab[1]
    txt = f"{nm(i)} — {cost(c)}: {effects(ab[2], E.db)}"
    extra = []
    if mana_total(pay) and (c.generic or mana_total(c.mana)): extra.append("pay " + mana_str(pay))
    if c.tapOther is not None: extra.append("tapping " + nm(pick))
    if c.sac[0] == "other": extra.append("sacrificing " + nm(pick))
    if extra: txt += " (" + ", ".join(extra) + ")"
    return txt + _choices(E, s, ab[2], tgt, col, nm)


def _choices(E, s, effs, tgt, col, nm):
    out = ""
    if any(e[0] in ("untapTarget", "copyTarget", "blink", "ctrTarget", "lifelink") for e in effs):
        out += f" → target #{tgt}" + (f" {nm(tgt)}" if tgt < len(s.bf) else "")
    if any(e[0] == "addAny" for e in effs):
        out += f" → {{{SYM[col]}}}"
    return out
