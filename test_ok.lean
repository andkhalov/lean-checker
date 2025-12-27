import Mathlib

open Function
open scoped Function AddConstEquiv AddConstMap

variable {G H K : Type*}
variable [Add G]
variable [Add H]
variable [Add K]
variable {a : G}
variable {b : H}
variable {c : K}

instance instInv : Inv (G ≃+c[a, a] G) :=
  ⟨.symm⟩
