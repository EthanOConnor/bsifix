/-
  Manaproof kernel — small-step operational semantics.

  `stepCfg` is a pure function of the board configuration.  It returns the new
  configuration together with the resources the action *costs* and the
  resources it *yields*; it never inspects the resource vector itself.
  `step` then pays and credits.  Every action is one transition, so the
  interpreter is trivially step-indexed: non-terminating mandatory loops are
  just infinite action sequences.
-/
import Manaproof.Model
namespace Manaproof

structure St where
  bf : List Perm
  stack : List Trig
  gain : Acc

def cardAt (db : List Card) (i : Nat) : Card := db.getD i {}

def modAt {α} : List α → Nat → (α → α) → List α
  | [], _, _ => []
  | x :: xs, 0, f => f x :: xs
  | x :: xs, n + 1, f => x :: modAt xs n f

def isCreature (db : List Card) (p : Perm) : Bool := (cardAt db p.card).tags.contains 0

def matchF (db : List Card) (bf : List Perm) (i : Nat) (self : Option Nat) (f : Filter) : Bool :=
  match bf[i]? with
  | none => false
  | some p =>
    let c := cardAt db p.card
    f.all.all (fun t => c.tags.contains t) && f.no.all (fun t => !c.tags.contains t)
    && (match f.color with | none => true | some k => c.colors.contains k)
    && (!f.nontoken || !p.tok) && (!f.other || self != some i)

/-- Abilities a permanent currently has: its own plus everything granted to it. -/
def effAbils (db : List Card) (bf : List Perm) (i : Nat) : List Ability :=
  match bf[i]? with
  | none => []
  | some p => (cardAt db p.card).abilities ++
      bf.zipIdx.flatMap fun (q, j) => (cardAt db q.card).grants.filterMap fun g =>
        match g.scope with
        | .attached => if q.att = some i then some g.ab else none
        | .all f => if matchF db bf i (some j) f then some g.ab else none

def hasKw (db : List Card) (bf : List Perm) (i : Nat) (k : Kw) : Bool :=
  (effAbils db bf i).contains (.kw k)

def collect (db : List Card) (bf : List Perm) (sel : Nat → On → Bool) (n : Nat)
    (subj : Option Subj) : List Trig :=
  bf.zipIdx.flatMap fun (_, q) => (effAbils db bf q).filterMap fun a =>
    match a with
    | .trig on opt cost e => if sel q on then some ⟨e, opt, cost, some q, n, subj⟩ else none
    | _ => none

def gainEv (db : List Card) (st : St) (a : Acc) : St :=
  let t1 := if a.life > 0 then collect db st.bf (fun _ on => on == .lifeGain) a.life none else []
  let t2 := if a.opp > 0 then collect db st.bf (fun _ on => on == .oppLoss) a.opp none else []
  { st with gain := st.gain.add a, stack := t1 ++ t2 ++ st.stack }

def fixIdx (i : Nat) : Option Nat → Option Nat
  | none => none
  | some j => if j = i then none else if j > i then some (j - 1) else some j

def removeAt (st : St) (i : Nat) : St :=
  { st with
    bf := (st.bf.eraseIdx i).map (fun p => { p with att := fixIdx i p.att })
    stack := st.stack.map (fun t => { t with self := fixIdx i t.self }) }

/-- Permanent `i` leaves the battlefield for the graveyard. -/
def die (db : List Card) (st : St) (i : Nat) : St :=
  match st.bf[i]? with
  | none => st
  | some p =>
    if isCreature db p then
      let sb : Option Subj := some ⟨p.card, p.tok⟩
      let ts := collect db st.bf (fun q on => match on with
        | .diesSelf => q == i
        | .diesAny f => matchF db st.bf i (some q) f
        | _ => false) 0 sb
      let k1 := if hasKw db st.bf i .persist && p.neg == 0
        then [Trig.mk [.ret .neg] false 0 none 0 sb] else []
      let k2 := if hasKw db st.bf i .undying && p.ctr == 0
        then [Trig.mk [.ret .ctr] false 0 none 0 sb] else []
      removeAt { st with stack := k1 ++ k2 ++ ts ++ st.stack } i
    else removeAt st i

/-- Enters-the-battlefield triggers for the permanent at position `j`. -/
def etbAt (db : List Card) (st : St) (j : Nat) : St :=
  let ts := collect db st.bf (fun q on => match on with
    | .etbSelf => q == j
    | .etbOther f => q != j && matchF db st.bf j none f
    | _ => false) 0 none
  { st with stack := ts ++ st.stack }

def addPerm (db : List Card) (st : St) (p : Perm) : St :=
  etbAt db { st with bf := st.bf ++ [p] } st.bf.length

def newPerm (db : List Card) (card : Nat) (tok haste : Bool) : Perm :=
  { card := card, sick := true, tok := tok, haste := haste, ctr := (cardAt db card).enterCtr,
    tapped := (cardAt db card).entersTapped }

def putCtr (db : List Card) (st : St) (j n : Nat) : St :=
  if n = 0 then st else
    let bf := modAt st.bf j (fun p => { p with ctr := p.ctr + n })
    let ts := collect db bf (fun q on => q == j && on == .ctrSelf) 0 none
    { st with bf := bf, stack := ts ++ st.stack }

/-- How many minus-counters actually land (`none`: they cannot be placed at all). -/
def negAmount (db : List Card) (bf : List Perm) (n : Nat) : Option Nat :=
  if bf.any (fun p => (cardAt db p.card).noNeg) then none
  else some (n - (bf.filter (fun p => (cardAt db p.card).negReduce)).length)

def colorAcc (col n : Nat) : Option Acc :=
  match col with
  | 0 => some { w := n } | 1 => some { u := n } | 2 => some { b := n }
  | 3 => some { r := n } | 4 => some { g := n } | 5 => some { c := n }
  | _ => none

def countMatch (db : List Card) (bf : List Perm) (self : Option Nat) (f : Filter) : Nat :=
  ((List.range bf.length).filter (fun j => matchF db bf j self f)).length

def hasColor (db : List Card) (bf : List Perm) (k : Nat) : Nat :=
  if bf.any (fun p => (cardAt db p.card).colors.contains k) then 1 else 0

def iter {α} : Nat → (α → α) → α → α
  | 0, _, x => x
  | n + 1, f, x => iter n f (f x)

def execEff (db : List Card) (tapFor : Bool) (n : Nat) (subj : Option Subj) (tgt col : Nat)
    (st : St) (self : Option Nat) : Effect → Option (St × Option Nat)
  | .gain a =>
    let bonus := (st.bf.filter (fun p => (cardAt db p.card).bonusC)).length
    let a' := if tapFor && a.c > 0 then { a with c := a.c + bonus } else a
    some (gainEv db st a', self)
  | .gainCtx toLife => some (gainEv db st (if toLife then { life := n } else { opp := n }), self)
  | .addAny k => (colorAcc col k).map fun a => (gainEv db st a, self)
  | .addPer f c => (colorAcc c (countMatch db st.bf self f)).map fun a => (gainEv db st a, self)
  | .addPerColor =>
    some (gainEv db st { w := hasColor db st.bf 0, u := hasColor db st.bf 1, b := hasColor db st.bf 2,
                         r := hasColor db st.bf 3, g := hasColor db st.bf 4 }, self)
  | .untapSelf =>
    match self with
    | some i => some ({ st with bf := modAt st.bf i (fun p => { p with tapped := false }) }, self)
    | none => some (st, self)
  | .untapTarget f =>
    if matchF db st.bf tgt self f
    then some ({ st with bf := modAt st.bf tgt (fun p => { p with tapped := false }) }, self)
    else none
  | .untapAll f =>
    some ({ st with bf := st.bf.zipIdx.map (fun (p, j) =>
      if matchF db st.bf j self f then { p with tapped := false } else p) }, self)
  | .token c k => some (iter k (fun s => addPerm db s (newPerm db c true false)) st, self)
  | .copyTarget f =>
    match st.bf[tgt]? with
    | some p => if matchF db st.bf tgt self f
        then some (addPerm db st (newPerm db p.card true true), self) else none
    | none => none
  | .blink f =>
    match st.bf[tgt]? with
    | some p =>
      if matchF db st.bf tgt self f then
        if p.tok then some (removeAt st tgt, fixIdx tgt self)
        else
          -- a new object in the same slot: nothing refers to it any more
          let st : St := { st with
            bf := (st.bf.set tgt (newPerm db p.card false false)).map
              (fun q => if q.att = some tgt then { q with att := none } else q)
            stack := st.stack.map (fun t => if t.self = some tgt then { t with self := none } else t) }
          some (etbAt db st tgt, if self = some tgt then none else self)
      else none
    | none => none
  | .ctrSelf k =>
    match self with
    | some i => some (putCtr db st i k, self)
    | none => some (st, self)
  | .ctrTarget f k => if matchF db st.bf tgt self f then some (putCtr db st tgt k, self) else none
  | .ctrAll f k =>
    some ((List.range st.bf.length).foldl
      (fun s j => if matchF db s.bf j self f then putCtr db s j k else s) st, self)
  | .ret m =>
    match subj with
    | none => some (st, self)
    | some sb =>
      if sb.tok then some (st, self) else
        let base := newPerm db sb.card false false
        let negAmt := match negAmount db st.bf 1 with | none => 0 | some v => v
        let p : Perm := match m with
          | .neg => { base with neg := negAmt }
          | .ctr => { base with ctr := base.ctr + 1 }
          | _ => base
        let j := st.bf.length
        -- the card has left the graveyard: any other trigger trying to return it finds nothing
        let stack' := st.stack.map (fun t => if t.subj = some sb then { t with subj := none } else t)
        let st : St := { st with stack := stack' }
        let st := addPerm db st p
        let st := match m, self with
          | .attach, some e => { st with bf := modAt st.bf e (fun q => { q with att := some j }) }
          | _, _ => st
        some (st, self)
  | .lifelink f =>
    if matchF db st.bf tgt self f
    then some ({ st with bf := modAt st.bf tgt (fun p => { p with link := true }) }, self)
    else none
  | .ping k =>
    let linked := match self with
      | some i => (match st.bf[i]? with | some p => p.link | none => false)
      | none => false
    some (gainEv db st { opp := k, life := if linked then k else 0 }, self)

def execEffs (db : List Card) (tapFor : Bool) (n : Nat) (subj : Option Subj) (tgt col : Nat) :
    St → Option Nat → List Effect → Option (St × Option Nat)
  | st, self, [] => some (st, self)
  | st, self, e :: es =>
    match execEff db tapFor n subj tgt col st self e with
    | some (st', self') => execEffs db tapFor n subj tgt col st' self' es
    | none => none

/-! ### State-based actions -/

def toughEff (db : List Card) (bf : List Perm) (i : Nat) : Nat :=
  match bf[i]? with
  | none => 0
  | some p => (cardAt db p.card).tough + p.ctr +
      ((effAbils db bf i).map (fun a => match a with | .tough n => n | _ => 0)).sum

/-- Legend rule: is there an earlier copy of this legendary permanent? -/
def legendDup (db : List Card) (bf : List Perm) (i : Nat) : Bool :=
  match bf[i]? with
  | some p => (cardAt db p.card).tags.contains 3 && (bf.take i).any (fun q => q.card == p.card)
  | none => false

def sbaStep (db : List Card) (st : St) : Option St :=
  match (List.range st.bf.length).find? (fun i => legendDup db st.bf i) with
  | some i => some (die db st i)
  | none =>
  match (List.range st.bf.length).find? (fun i => match st.bf[i]? with
      | some p => isCreature db p && decide (toughEff db st.bf i ≤ p.neg)
      | none => false) with
  | some i => some (die db st i)
  | none =>
    match (List.range st.bf.length).find? (fun i => match st.bf[i]? with
        | some p => (cardAt db p.card).tags.contains 4 && p.att.isNone
        | none => false) with
    | some i => some (removeAt st i)
    | none => none

def sba (db : List Card) : Nat → St → St
  | 0, st => st
  | n + 1, st => match sbaStep db st with
    | some st' => sba db n st'
    | none => st

def annihilate (st : St) : St :=
  { st with bf := st.bf.map fun p =>
      let m := min p.ctr p.neg; { p with ctr := p.ctr - m, neg := p.neg - m } }

def runSba (db : List Card) (st : St) : St :=
  let st := annihilate st
  sba db (st.bf.length + 1) st

/-! ### Costs -/

def canTap (db : List Card) (bf : List Perm) (i : Nat) (p : Perm) : Bool :=
  !isCreature db p || !p.sick || p.haste || hasKw db bf i .haste

def payCost (db : List Card) (st : St) (i : Nat) (c : Cost) (pay : Acc) (pick : Nat) :
    Option (St × Option Nat × Acc) := do
  let p ← st.bf[i]?
  guard (!c.tap || (!p.tapped && canTap db st.bf i p))
  guard (!c.untap || (p.tapped && canTap db st.bf i p))
  guard (!(c.tap && c.untap))
  guard (!c.loyal || !p.used)
  guard (c.removeCtr ≤ p.ctr)
  let negAmt ← if c.putNeg = 0 then some 0 else negAmount db st.bf c.putNeg
  let red := ((st.bf.filter (fun q => q.att == some i)).map
    (fun q => (cardAt db q.card).reduceHost)).sum
  let col := c.mana.manaTotal
  let gen := if red = 0 then c.generic
    else if col = 0 then max (c.generic - red) (min c.generic 1)
    else c.generic - red
  guard (pay.pureMana && decide (c.mana ≤ pay) && pay.manaTotal == col + gen)
  let p' : Perm := { p with
    tapped := if c.tap then true else if c.untap then false else p.tapped
    used := p.used || c.loyal
    ctr := p.ctr - c.removeCtr
    neg := p.neg + negAmt }
  let st : St := { st with bf := st.bf.set i p' }
  let st ← match c.tapOther with
    | none => some st
    | some f =>
      match st.bf[pick]? with
      | some q =>
        if matchF db st.bf pick (some i) f && !q.tapped
        then some { st with bf := st.bf.set pick { q with tapped := true } }
        else none
      | none => none
  let costAcc : Acc := { pay with life := c.life }
  match c.sac with
  | .none => some (st, some i, costAcc)
  | .self => some (die db st i, none, costAcc)
  | .other f =>
    if matchF db st.bf pick (some i) f
    then some (die db st pick, fixIdx pick (some i), costAcc)
    else none

/-! ### Transitions -/

/-- One transition on the configuration: `(cfg', cost, gain)`. -/
def stepCfg (db : List Card) (cfg : Cfg) : Action → Option (Cfg × Acc × Acc)
  | .act i k pay pick tgt col =>
    match (effAbils db cfg.bf i)[k]? with
    | some (.act c effs) =>
      match payCost db ⟨cfg.bf, cfg.stack, Acc.zero⟩ i c pay pick with
      | some (st, self, costAcc) =>
        match execEffs db c.tap 0 none tgt col st self effs with
        | some (st, _) =>
          let st := runSba db st
          some (⟨st.bf, st.stack⟩, costAcc, st.gain)
        | none => none
      | none => none
    | _ => none
  | .resolve pay tgt col =>
    match cfg.stack with
    | [] => none
    | t :: rest =>
      if pay.pureMana && pay.manaTotal == t.cost then
        match execEffs db false t.n t.subj tgt col ⟨cfg.bf, rest, Acc.zero⟩ t.self t.eff with
        | some (st, _) =>
          let st := runSba db st
          some (⟨st.bf, st.stack⟩, pay, st.gain)
        | none => none
      else none
  | .skip =>
    match cfg.stack with
    | t :: rest => if t.optional then some (⟨cfg.bf, rest⟩, Acc.zero, Acc.zero) else none
    | [] => none

def step (db : List Card) (s : State) (a : Action) : Option State :=
  match stepCfg db s.cfg a with
  | none => none
  | some (c, cost, gain) =>
    if cost ≤ s.acc then some ⟨c, (s.acc.sub cost).add gain⟩ else none

def run (db : List Card) (s : State) : List Action → Option State
  | [] => some s
  | a :: as => match step db s a with
    | some s' => run db s' as
    | none => none

end Manaproof
