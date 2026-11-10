/-
  Manaproof kernel — resource vectors.

  `Acc` holds every quantity that is only ever *added to* or *paid from*:
  the mana pool, life, and a few monotone counters.  Keeping these apart from
  the board configuration is what makes the loop-pumping theorem cheap.
-/
namespace Manaproof

structure Acc where
  w : Nat := 0
  u : Nat := 0
  b : Nat := 0
  r : Nat := 0
  g : Nat := 0
  c : Nat := 0
  life : Nat := 0
  opp : Nat := 0   -- life lost by the opponent
  draw : Nat := 0
  mill : Nat := 0
  deriving DecidableEq, Repr, Inhabited

namespace Acc

def zero : Acc := {}

def add (x y : Acc) : Acc :=
  ⟨x.w + y.w, x.u + y.u, x.b + y.b, x.r + y.r, x.g + y.g, x.c + y.c,
   x.life + y.life, x.opp + y.opp, x.draw + y.draw, x.mill + y.mill⟩

def sub (x y : Acc) : Acc :=
  ⟨x.w - y.w, x.u - y.u, x.b - y.b, x.r - y.r, x.g - y.g, x.c - y.c,
   x.life - y.life, x.opp - y.opp, x.draw - y.draw, x.mill - y.mill⟩

def smul (n : Nat) (x : Acc) : Acc :=
  ⟨n * x.w, n * x.u, n * x.b, n * x.r, n * x.g, n * x.c,
   n * x.life, n * x.opp, n * x.draw, n * x.mill⟩

def le (x y : Acc) : Prop :=
  x.w ≤ y.w ∧ x.u ≤ y.u ∧ x.b ≤ y.b ∧ x.r ≤ y.r ∧ x.g ≤ y.g ∧ x.c ≤ y.c ∧
  x.life ≤ y.life ∧ x.opp ≤ y.opp ∧ x.draw ≤ y.draw ∧ x.mill ≤ y.mill

instance : LE Acc := ⟨le⟩
instance (x y : Acc) : Decidable (x ≤ y) := by
  show Decidable (le x y); unfold le; exact inferInstance

def manaTotal (x : Acc) : Nat := x.w + x.u + x.b + x.r + x.g + x.c

/-- A payment vector may only contain mana. -/
def pureMana (x : Acc) : Bool :=
  x.life == 0 && x.opp == 0 && x.draw == 0 && x.mill == 0

theorem le_def {x y : Acc} : x ≤ y ↔ le x y := Iff.rfl

theorem le_add_right {x y : Acc} (h : x ≤ y) (d : Acc) : x ≤ y.add d := by
  rw [le_def] at *; unfold le at *; simp only [add]; omega

theorem sub_add_shift {x cost : Acc} (h : cost ≤ x) (gain d : Acc) :
    ((x.add d).sub cost).add gain = ((x.sub cost).add gain).add d := by
  rw [le_def] at h; unfold le at h
  simp only [add, sub, Acc.mk.injEq]; omega

theorem add_zero (x : Acc) : x.add (smul 0 d) = x := by
  cases x; simp [add, smul]

theorem add_sub_of_le {x y : Acc} (h : x ≤ y) : x.add (y.sub x) = y := by
  rw [le_def] at h; unfold le at h
  cases x; cases y; simp only [add, sub, Acc.mk.injEq] at *; omega

theorem smul_succ (x d : Acc) (n : Nat) :
    (x.add (smul n d)).add d = x.add (smul (n + 1) d) := by
  simp only [add, smul, Acc.mk.injEq, Nat.add_mul, Nat.one_mul]; omega

end Acc
end Manaproof
