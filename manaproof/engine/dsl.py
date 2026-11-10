"""Tiny builder DSL for writing cards as programs."""
from .model import (Card, Filter, Cost, ZERO, ACC_NAMES, T_CREATURE, T_AURA, T_EQUIPMENT)

TAGS = {"creature": 0, "artifact": 1, "enchantment": 2, "legendary": 3, "aura": 4,
        "equipment": 5, "planeswalker": 6}
COLORS = "WUBRG"
_pending = []   # cards in definition order


def tag(name):
    if name not in TAGS:
        TAGS[name] = max(10, max(TAGS.values()) + 1)
    return TAGS[name]


def tags(s):
    return tuple(tag(x) for x in s.split())


def F(all="", no="", color=None, nontoken=False, other=False):
    return Filter(tags(all), tags(no), COLORS.index(color) if color else -1, nontoken, other)


ANY = F()
CREATURE = F("creature")


def parse_mana(s):
    """'2UU' -> (acc, generic). 'C' is specifically colourless."""
    a = [0] * 10; generic = 0; num = ""
    for ch in str(s):
        if ch.isdigit():
            num += ch
        else:
            a["WUBRGC".index(ch)] += 1
    if num: generic = int(num)
    return tuple(a), generic


def cost(mana="", tap=False, untap=False, sac=None, tapOther=None, removeCtr=0, putNeg=0, life=0, loyal=False):
    m, g = parse_mana(mana)
    if sac is None: sk = ("none",)
    elif sac == "self": sk = ("self",)
    else: sk = ("other", sac)
    return Cost(tap, untap, m, g, sk, tapOther, removeCtr, putNeg, life, loyal)


def act(c, *effs):
    return ("act", c, tuple(effs))


def trig(on, *effs, optional=False, pay=0):
    return ("trig", on, optional, pay, tuple(effs))


def kw(k): return ("kw", k)
def tough(n): return ("tough", n)

# events
ETB = ("etbSelf",)
def etb_other(f=CREATURE): return ("etbOther", f)
DIES = ("diesSelf",)
def dies_any(f=CREATURE): return ("diesAny", f)
LIFEGAIN = ("lifeGain",)
OPPLOSS = ("oppLoss",)
CTR_SELF = ("ctrSelf",)


# effects
def mana(s):
    m, g = parse_mana(s)
    assert g == 0
    return ("gain", m)


def gain(**kw_):
    a = [0] * 10
    for k, v in kw_.items(): a[ACC_NAMES.index(k)] = v
    return ("gain", tuple(a))


def any_color(n=1): return ("addAny", n)
def mana_per(f, color): return ("addPer", f, "WUBRGC".index(color))
MANA_PER_COLOR = ("addPerColor",)
UNTAP_SELF = ("untapSelf",)
def untap(f=ANY): return ("untapTarget", f)
def untap_all(f=CREATURE): return ("untapAll", f)
def token(name, n=1): return ("token", name, n)
def copy(f): return ("copyTarget", f)
def blink(f): return ("blink", f)
def ctr_self(n=1): return ("ctrSelf", n)
def ctr_target(f=CREATURE, n=1): return ("ctrTarget", f, n)
def ctr_all(f=CREATURE, n=1): return ("ctrAll", f, n)
def ret(mode="plain"): return ("ret", mode)
def lifelink(f): return ("lifelink", f)
def ping(n=1): return ("ping", n)
GAIN_THAT = ("gainCtx", True)
LOSE_THAT = ("gainCtx", False)

ATTACHED = ("attached",)
def grant(ab, to=None): return (ATTACHED if to is None else ("all", to), ab)


def card(name, types, colors="", mv=0, pt=None, subs="", ab=(), grants=(), text="", token_def=False,
         enchant=None, **kw_):
    c = Card(name=name, tags=tags(types) + tags(subs), colors=tuple(COLORS.index(x) for x in colors),
             abilities=tuple(ab), grants=tuple(grants), mv=mv, text=text, is_token=token_def,
             types=(types + (" — " + subs if subs else "")), enchant=enchant, **kw_)
    if pt:
        c.power, c.tough = pt
    _pending.append(c)
    return c


def finalize():
    """Resolve token names to indices; returns the card database."""
    db = list(_pending)
    idx = {c.name: i for i, c in enumerate(db)}
    def fix_eff(e):
        return ("token", idx[e[1]], e[2]) if e[0] == "token" and isinstance(e[1], str) else e
    def fix_ab(a):
        if a[0] == "act": return ("act", a[1], tuple(fix_eff(e) for e in a[2]))
        if a[0] == "trig": return a[:4] + (tuple(fix_eff(e) for e in a[4]),)
        return a
    for i, c in enumerate(db):
        c.idx = i
        c.abilities = tuple(fix_ab(a) for a in c.abilities)
        c.grants = tuple((s, fix_ab(a)) for s, a in c.grants)
    return db
