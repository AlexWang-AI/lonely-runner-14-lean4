import Lake
open Lake DSL

package LonelyRunner14

@[default_target]
lean_lib LonelyRunner14 where
  globs := #[Glob.submodules `outputs]

require mathlib from git
  "https://github.com/leanprover-community/mathlib4" @ "v4.33.0"
