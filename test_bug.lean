import Mathlib

open Nat
open Function
open scoped Function List Nat

variable {ι : Type*}
variable {α : Type u}
variable {β : Type v}
variable {γ : Type w}
variable {l₁ l₂ : List α}
variable (a : α)
variable (as : List α)
variable (b : β)
variable (bs : List β)

@[simp]
theorem zipLeft'_cons_cons :
    zipLeft' (a :: as) (b :: bs) =
      let r := zipLeft' as bs
      ((a, some b) :: r.fst, r.snd) :=
  rfl
