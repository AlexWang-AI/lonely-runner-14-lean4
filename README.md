
# Lean 4 Formal Verification for Lonely Runner Conjecture (LRC-14)

![Lean 4](https://img.shields.io/badge/Lean_4-v4.3.0-blue)
![Mathlib](https://img.shields.io/badge/Mathlib4-verified-green)
![Status](https://img.shields.io/badge/Finite_Core-0--sorry-brightgreen)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

Formal verification pipeline and machine-checked proof certificates for the **14-Runner Lonely Runner Conjecture (LRC-14)** in Lean 4.

---

## Key Formal Deliverables

1. **Universal Weak Bound (`0-sorry`)**  
   Machine-checked proof of the classical measure-theoretic subadditivity bound ($\delta = 1 / (2k)$).  
   * Artifact: `outputs/proved_weak_lonely_runner_universal.lean`

2. **Extremal Boundary Certificates ($M \le 30$)**  
   Zero-counterexample certificates verified for finite discrete bounds ($>2.3 \times 10^7$ instances verified).  
   * Artifact: `outputs/LRC14_FULL_5_CERTIFICATES_BUNDLE.lean`

3. **Composite Gap Lower Bound**  
   Formal verification of coprime interval containment.  
   * Artifact: `outputs/proved_coprime_composite_gap_lower_bound.lean`

---

## Repository Structure

```text
.
├── agent_core/       # Search loop orchestration and proof generation
├── outputs/          # Verified Lean 4 artifacts (0-sorry declarations)
├── research/         # Python verification engines and boundary probes
└── requirements.txt  # Python environment dependencies
```

---

## Reproduction & Verification Guide

### 1. Verify Lean 4 Proofs
Requires `elan`, `Lean 4` (`v4.3.0+`), and `mathlib4`:

```bash
# Verify individual formal proofs
lean outputs/proved_weak_lonely_runner_universal.lean
lean outputs/proved_coprime_composite_gap_lower_bound.lean
lean outputs/LRC14_FULL_5_CERTIFICATES_BUNDLE.lean

# Expected output: Clean compilation, 0 errors, 0 sorry
```

### 2. Run Verification Engine (Python)
```bash
python -m pip install -r requirements.txt
python research/lrc14_crt_decoupling.py
# Expected output: Bidirectional verification: PASS
```

---

## Companion Research

Degeneration analysis, safe-zone collapse logs, and RLVR feedback trajectories are documented in the companion diagnostics repository:  
👉 [ai-math-institute](https://github.com/AlexWang-AI/ai-math-institute)
```

---
