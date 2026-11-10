/-
  Manaproof kernel — metatheory and certificate checkers.

  Search is untrusted.  It hands us a *certificate*: a starting position, a
  prefix of actions and a loop of actions.  The checkers below re-execute the
  certificate inside the kernel, and `checkA_sound` turns a successful check
  into a statement about every natural number of iterations.
-/
import Manaproof.Step
namespace Manaproof

/-- Resources are a frame: extra resources never disable a transition and
    are carried through unchanged. -/
theorem step_shift {db : List Card} {s s' : State} {a : Action}
    (h : step db s a = some s') (d : Acc) :
    step db ⟨s.cfg, s.acc.add d⟩ a = some ⟨s'.cfg, s'.acc.add d⟩ := by
  unfold step at *
  cases hc : stepCfg db s.cfg a with
  | none => simp [hc] at h
  | some r =>
    obtain ⟨c, cost, gain⟩ := r
    simp only [hc] at h ⊢
    by_cases hle : cost ≤ s.acc
    · rw [if_pos hle] at h
      rw [if_pos (Acc.le_add_right hle d)]
      cases h
      simp [Acc.sub_add_shift hle]
    · rw [if_neg hle] at h; cases h

/-- The frame property lifted from single steps to whole traces. -/
theorem run_shift {db : List Card} {tr : List Action} : ∀ {s s' : State},
    run db s tr = some s' → ∀ d : Acc,
    run db ⟨s.cfg, s.acc.add d⟩ tr = some ⟨s'.cfg, s'.acc.add d⟩ := by
  induction tr with
  | nil => intro s s' h d; simp [run] at h ⊢; subst h; exact ⟨rfl, rfl⟩
  | cons a as ih =>
    intro s s' h d
    simp only [run] at h ⊢
    cases hs : step db s a with
    | none => simp [hs] at h
    | some s1 =>
      simp only [hs] at h
      rw [step_shift hs d]
      exact ih h d

/-- Running a concatenation is running the pieces in sequence. -/
theorem run_append {db : List Card} {t1 t2 : List Action} : ∀ {s s1 : State},
    run db s t1 = some s1 → run db s (t1 ++ t2) = run db s1 t2 := by
  induction t1 with
  | nil => intro s s1 h; simp [run] at h; subst h; rfl
  | cons a as ih =>
    intro s s1 h
    simp only [run, List.cons_append] at h ⊢
    cases hs : step db s a with
    | none => simp [hs] at h
    | some s' => simp only [hs] at h ⊢; exact ih h

def rep {α} : Nat → List α → List α
  | 0, _ => []
  | n + 1, l => rep n l ++ l

/-- **Pumping theorem.**  A trace that returns to the same configuration with
    no resource lower can be repeated any number of times, and the n-th
    repetition has gained exactly n times the loop's net yield. -/
theorem pump {db : List Card} {s s' : State} {tr : List Action}
    (h : run db s tr = some s') (hc : s'.cfg = s.cfg) (hle : s.acc ≤ s'.acc) :
    ∀ n, run db s (rep n tr) = some ⟨s.cfg, s.acc.add (Acc.smul n (s'.acc.sub s.acc))⟩ := by
  intro n
  induction n with
  | zero => simp [rep, run, Acc.add_zero]
  | succ n ih =>
    simp only [rep]
    rw [run_append ih]
    have h2 := run_shift (s := s) h (Acc.smul n (s'.acc.sub s.acc))
    rw [h2, hc]
    congr 2
    have e : s'.acc = s.acc.add (s'.acc.sub s.acc) := (Acc.add_sub_of_le hle).symm
    calc s'.acc.add (Acc.smul n (s'.acc.sub s.acc))
        = (s.acc.add (s'.acc.sub s.acc)).add (Acc.smul n (s'.acc.sub s.acc)) := by rw [← e]
      _ = (s.acc.add (Acc.smul n (s'.acc.sub s.acc))).add (s'.acc.sub s.acc) := by
          simp only [Acc.add, Acc.mk.injEq]; omega
      _ = s.acc.add (Acc.smul (n + 1) (s'.acc.sub s.acc)) := Acc.smul_succ _ _ _

/-! ### Certificates -/

structure Cert where
  cards : List (Nat × Option Nat)   -- card id, attached-to position
  float : Acc                        -- resources available at the start
  pre : List Action
  loop : List Action

def mkPerm (db : List Card) (x : Nat × Option Nat) : Perm :=
  { card := x.1, ctr := (cardAt db x.1).setupCtr, att := x.2 }

/-- Attachments in the starting position must be legal. -/
def initOk (db : List Card) (bf : List Perm) : Bool :=
  bf.all fun p => match (cardAt db p.card).enchant, p.att with
    | none, none => true
    | some f, some h => matchF db bf h none f
    | some _, none => !(cardAt db p.card).tags.contains 4
    | none, some _ => false

def Cert.init (db : List Card) (c : Cert) : State :=
  ⟨⟨c.cards.map (mkPerm db), []⟩, c.float⟩

/-- Grade A: the loop returns to the *identical* configuration, no resource
    decreases and at least one increases. -/
def checkA (db : List Card) (c : Cert) : Bool :=
  initOk db (c.init db).cfg.bf &&
  match run db (c.init db) c.pre with
  | none => false
  | some s => match run db s c.loop with
    | none => false
    | some s' => decide (s'.cfg = s.cfg) && decide (s.acc ≤ s'.acc) && decide (s'.acc ≠ s.acc)

/-- The loop's net yield per iteration. -/
def loopDelta (db : List Card) (c : Cert) : Option Acc :=
  match run db (c.init db) c.pre with
  | none => none
  | some s => match run db s c.loop with
    | none => none
    | some s' => some (s'.acc.sub s.acc)

/-- **Soundness of the checker.**  If `checkA` evaluates to `true`, the
    certificate's loop can be iterated any number of times, each iteration
    adding the same non-zero yield `δ`. -/
theorem checkA_sound (db : List Card) (c : Cert) (h : checkA db c = true) :
    ∃ (s : State) (δ : Acc), δ ≠ Acc.zero ∧ run db (c.init db) c.pre = some s ∧
      ∀ n, run db (c.init db) (c.pre ++ rep n c.loop)
        = some ⟨s.cfg, s.acc.add (Acc.smul n δ)⟩ := by
  unfold checkA at h
  simp only [Bool.and_eq_true] at h
  obtain ⟨_, h⟩ := h
  cases h1 : run db (c.init db) c.pre with
  | none => simp [h1] at h
  | some s =>
    simp only [h1] at h
    cases h2 : run db s c.loop with
    | none => simp [h2] at h
    | some s' =>
      simp only [h2, Bool.and_eq_true, decide_eq_true_eq] at h
      obtain ⟨⟨hc, hle⟩, hne⟩ := h
      refine ⟨s, s'.acc.sub s.acc, ?_, rfl, ?_⟩
      · intro hz
        apply hne
        have := Acc.add_sub_of_le hle
        rw [hz] at this
        rw [← this]; cases s.acc; simp [Acc.add, Acc.zero]
      · intro n
        rw [run_append h1]
        exact pump h2 hc hle n

/-! Grade B: the board itself grows (tokens, counters), so the configuration
    never repeats.  We check `k` consecutive iterations by evaluation. -/

def permGrow (p q : Perm) : Bool := decide ({ q with ctr := p.ctr } = p) && decide (p.ctr ≤ q.ctr)

def bfGrow : List Perm → List Perm → Bool
  | [], _ => true
  | _ :: _, [] => false
  | p :: ps, q :: qs => permGrow p q && bfGrow ps qs

def grows (s s' : State) : Bool :=
  decide (s.cfg.stack = s'.cfg.stack) && bfGrow s.cfg.bf s'.cfg.bf &&
  decide (s.acc ≤ s'.acc) && decide (s ≠ s')

def iterB (db : List Card) (loop : List Action) : Nat → State → Bool
  | 0, _ => true
  | k + 1, s => match run db s loop with
    | some s' => grows s s' && iterB db loop k s'
    | none => false

def checkB (db : List Card) (c : Cert) (k : Nat) : Bool :=
  initOk db (c.init db).cfg.bf &&
  match run db (c.init db) c.pre with
  | none => false
  | some s => iterB db c.loop k s

/-- Board size and resources after the prefix and `k` loop iterations. -/
def summary (db : List Card) (c : Cert) (k : Nat) : Option (Nat × Acc) :=
  match run db (c.init db) (c.pre ++ rep k c.loop) with
  | none => none
  | some s => some (s.cfg.bf.length, s.acc)

end Manaproof
