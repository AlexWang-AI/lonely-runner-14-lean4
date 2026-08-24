
```markdown
# Formal Verification & Computational Infrastructure for the 14-Runner Lonely Runner Problem in Lean 4

![Lean 4](https://img.shields.io/badge/Lean_4-v4.33.0-blue.svg)
![Mathlib](https://img.shields.io/badge/Mathlib-4.33.0-green.svg)
![Status](https://img.shields.io/badge/Finite_Core-0--sorry-brightgreen.svg)
![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)

## Overview

This repository provides a machine-checked formal verification pipeline and computational infrastructure targeting the **Lonely Runner Conjecture (LRC)** for $K = 14$ runners ($|V| = 13$ non-zero velocities). 

Combining high-throughput Python-based falsification engines with interactive theorem proving in **Lean 4**, this repository provides exact machine-checkable certificates for extremal discrete configurations and serves as an empirical testbed for automated mathematical reasoning.

---

## Core Technical Deliverables

### 1. Formal Baseline: Universal Weak Bound (0-sorry)
Formally verified the classical measure-theoretic subadditivity weak bound $\delta = \frac{1}{2(k+1)}$ for arbitrary $k \ge 1$ runners in Lean 4 without axioms:
* **Theorem:** `outputs/proved_weak_lonely_runner_universal.lean`
* **Proof Method:** One-directional interval containment accounting via `sum_range_succ` and non-covering finite subadditivity (`measure_biUnion_finset_le`). Fully machine-checked.

### 2. Extremal Boundary Certificates ($M \le 30$ Finite Core)
For highly structured covering configurations where heuristic searches fail, the repository implements certified integer/fractional certificates:
* **Zero Floating-Point Error:** Verified lonely-time instances $t^* = p/q$ satisfying $\forall v_i \in V, \{v_i t^*\} \in [1/14, 13/14]$.
* **Lean 4 Proofs:** 5 critical extremal certificates compiled and machine-checked in a single unified bundle (`outputs/LRC14_FULL_5_CERTIFICATES_BUNDLE.lean`) using exact kernel tactics (`norm_num`).

### 3. Sieve & Decoupling Infrastructure (Active Frontier: $M > 30$)
* **660k-Point Bidirectional Verification:** Exhaustive grid verification for discrete modular equivalence over $\mathbb{Z}_4 \times \mathbb{Z}_{89271}$.
* **Structural Bounds:** Proved the `coprime_composite_gap_lower_bound` theorem in Lean 4 (`outputs/proved_coprime_composite_gap_lower_bound.lean`) via `omega` tactics to bound worst-case prime collisions.
* **Open Exploration:** The general CRT decoupling and asymptotic bridge for $M > 30$ is maintained as an active benchmark for multi-agent formal synthesis.

---

## Repository Structure

```text
.
├── MathWorkspace/               # Lean 4 workspace (lakefile, toolchain)
│   ├── crt_decoupling_proof.lean
│   └── temp_verify.lean
├── outputs/                     # Machine-checked Lean 4 theorem artifacts
│   ├── proved_weak_lonely_runner_universal.lean
│   ├── proved_coprime_composite_gap_lower_bound.lean
│   └── proved_lrc14_cert*.lean
├── research/                    # Python solvers, Sieve engines, & Probes
│   ├── lrc14_crt_decoupling.py
│   ├── lrc_core.py              # Exact rational verifier
│   └── probes_v4.py             # Spectral & Farkas heuristic probes
└── README.md
```

---

## Reproduction & Verification Guide

### 1. Verify Lean 4 Proofs (Main Core)
Requires `elan`, `Lean 4.33.0`, and compiled `mathlib`:

```bash
cd MathWorkspace
lake env lean ../outputs/proved_weak_lonely_runner_universal.lean
lake env lean ../outputs/proved_coprime_composite_gap_lower_bound.lean
lake env lean ../outputs/LRC14_FULL_5_CERTIFICATES_BUNDLE.lean
# Expected: Clean compilation, 0 errors, 0 sorry
```

### 2. Run High-Throughput Decoupling Engine (Python)

```bash
python -X utf8 research/lrc14_crt_decoupling.py
# Expected: Bidirectional verification over search grids: PASS
```

---

## Companion Project

This formalization repository is evaluated alongside the multi-agent reasoning traces documented in [ai-math-institute](https://github.com/AlexWang-AI/ai-math-institute), analyzing model failure modes, reward hacking, and tree search degeneration during long-chain formal math generation.
```
