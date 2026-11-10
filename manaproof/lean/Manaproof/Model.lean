/-
  Manaproof kernel — the card language.

  Cards are *programs* in a small typed DSL; nothing in the interpreter knows
  any card by name.  Tags (types, supertypes, subtypes) are plain numbers:
  0 creature · 1 artifact · 2 enchantment · 3 legendary · 4 aura
  5 equipment · 6 planeswalker · 10+ subtypes.   Colours: 0..4 = WUBRG, 5 = C.
-/
import Manaproof.Basic
namespace Manaproof

structure Filter where
  all : List Nat := []          -- must carry every one of these tags
  no : List Nat := []           -- must carry none of these
  color : Option Nat := none
  nontoken : Bool := false
  other : Bool := false         -- "another": not the ability's source
  deriving DecidableEq, Repr

inductive RetMode | plain | attach | neg | ctr
  deriving DecidableEq, Repr

inductive Effect
  | gain (a : Acc)                      -- add mana / gain life / opponent loses life / draw / mill
  | gainCtx (toLife : Bool)             -- "that much": amount comes from the triggering event
  | addAny (n : Nat)                    -- n mana of one chosen colour
  | addPer (f : Filter) (col : Nat)     -- one mana of `col` per matching permanent
  | addPerColor                         -- one mana of each colour among your permanents
  | untapSelf
  | untapTarget (f : Filter)
  | untapAll (f : Filter)
  | token (card : Nat) (n : Nat)
  | copyTarget (f : Filter)             -- hasty token copy of target
  | blink (f : Filter)                  -- exile target, return it to the battlefield
  | ctrSelf (n : Nat)
  | ctrTarget (f : Filter) (n : Nat)
  | ctrAll (f : Filter) (n : Nat)
  | ret (m : RetMode)                   -- return the card that died
  | lifelink (f : Filter)
  | ping (n : Nat)                      -- damage to the opponent (lifelink-aware)
  deriving DecidableEq, Repr

inductive SacKind | none | self | other (f : Filter)
  deriving DecidableEq, Repr

structure Cost where
  tap : Bool := false
  untap : Bool := false               -- the untap symbol {Q}
  mana : Acc := {}                    -- coloured / specific requirement
  generic : Nat := 0
  sac : SacKind := .none
  tapOther : Option Filter := none    -- "tap an untapped … you control"
  removeCtr : Nat := 0
  putNeg : Nat := 0                   -- put -1/-1 counters on itself
  life : Nat := 0
  loyal : Bool := false               -- loyalty ability: once per permanent
  deriving DecidableEq, Repr

inductive On
  | etbSelf | etbOther (f : Filter) | diesSelf | diesAny (f : Filter)
  | lifeGain | oppLoss | ctrSelf
  deriving DecidableEq, Repr

inductive Kw | haste | persist | undying
  deriving DecidableEq, Repr

inductive Ability
  | act (c : Cost) (e : List Effect)
  | trig (on : On) (optional : Bool) (cost : Nat) (e : List Effect)
  | kw (k : Kw)
  | tough (n : Nat)
  deriving DecidableEq, Repr

inductive Scope | attached | all (f : Filter)
  deriving DecidableEq, Repr

structure Grant where
  scope : Scope
  ab : Ability
  deriving DecidableEq, Repr

structure Card where
  name : String := "?"
  tags : List Nat := []
  colors : List Nat := []
  tough : Nat := 0
  abilities : List Ability := []
  grants : List Grant := []
  enterCtr : Nat := 0       -- counters it enters with
  setupCtr : Nat := 0       -- counters in the starting position (e.g. X chosen on cast)
  negReduce : Bool := false -- -1/-1 counters placed are reduced by one
  noNeg : Bool := false     -- -1/-1 counters can't be placed
  bonusC : Bool := false    -- tapping for {C} yields one extra {C}
  reduceHost : Nat := 0     -- attached permanent's abilities cost this much less
  enchant : Option Filter := none
  entersTapped : Bool := false
  deriving Repr

structure Perm where
  card : Nat
  tapped : Bool := false
  sick : Bool := false
  tok : Bool := false
  haste : Bool := false
  link : Bool := false
  used : Bool := false
  ctr : Nat := 0
  neg : Nat := 0
  att : Option Nat := none
  deriving DecidableEq, Repr

structure Subj where
  card : Nat
  tok : Bool
  deriving DecidableEq, Repr

/-- A triggered ability waiting on the stack. -/
structure Trig where
  eff : List Effect
  optional : Bool
  cost : Nat
  self : Option Nat
  n : Nat
  subj : Option Subj
  deriving DecidableEq, Repr

structure Cfg where
  bf : List Perm
  stack : List Trig
  deriving DecidableEq, Repr

structure State where
  cfg : Cfg
  acc : Acc
  deriving DecidableEq, Repr

inductive Action
  | act (i k : Nat) (pay : Acc) (pick tgt col : Nat)
  | resolve (pay : Acc) (tgt col : Nat)
  | skip
  deriving DecidableEq, Repr

end Manaproof
