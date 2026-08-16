# Formal Verification and CRT Decoupling for 14-Runner Lonely Runner Problem in Lean 4

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
<!-- Zenodo DOI badge placeholder: replace XXXXXXX after the first Zenodo deposit -->

## Abstract

This repository contains machine-checked formal artifacts and computational infrastructure targeting the **14-runner Lonely Runner Conjecture** (LRC, the current global frontier after 13 runners were settled in 2026 via sieving and the polynomial method).

**Core results:**

1. **Composite-barrier diagnosis.** The 2026 polynomial-method lemma requires *k+1* to be an odd prime. For 14 runners, *k+1 = 14* is composite, so the lemma's hypotheses fail — the algebraic root of the current literature gap. Empirically, the principal residue class *v ≡ (1..13) (mod 191)* passes 300/300 sampled instances (tightest gap 5.3e-11), i.e., the lemma's *conclusion* still holds numerically in the composite case — first-hand evidence for a generalized sieve.

2. **660k-point bidirectional verification.** The CRT decoupling engine (`research/lrc14_crt_decoupling.py`) decomposes the certificate-1 legality interval *I = [25506, 331578]* (mod 357084 = 4 × 89271, coprime) into AP-window boxes over *Z₄ × Z₈₉₂₇₁* and verifies the equivalence in both directions by exhaustive enumeration (306,073 + 357,084 points).

3. **0-sorry Lean 4 closure.** The universal decoupling lemma
   `∀ r, (r % 357084 ∈ [25506, 331578]) ↔ (four AP-window branches with bounded ∃t)`
   is formally proved in Lean 4 (`outputs/proved_lrc14_crt_interval_decoupling.lean`), machine-verified with zero `sorry`/`admit`. The proof combines CRT projection lemmas (`Nat.mod_mod_of_dvd`), `wlog` symmetrization, a divisibility chain (`Nat.Coprime.mul_dvd_of_dvd_of_dvd`, `Nat.eq_zero_of_dvd_of_lt`), and `interval_cases`/`omega` branch elimination.

4. **Five exact lonely-time certificates** (zero floating-point error, `Fraction`-verified) for near-degenerate 14-runner speed tuples (tightest covering gap 7.96e-9), produced by an unattended red-blue adversarial siege (simulated annealing + SOS/Farkas/spectral/entropy probes). Certificate 1 is formalized in Lean with a one-shot `norm_num` proof (`outputs/proved_lonely_runner_k13_14runners.lean`).

## Repository Index

| Path | Content |
|---|---|
| `outputs/proved_lrc14_crt_interval_decoupling.lean` | **Main theorem** — CRT interval decoupling, 0-sorry Lean proof |
| `outputs/proved_lonely_runner_k13_14runners.lean` | Certificate-1 boundary witness (26 rational inequalities, `norm_num` closure) |
| `outputs/proved_erdos_coprime_even_gap_*.lean` | Earlier milestones (Erdős coprime gap theorem) |
| `research/lrc14_crt_decoupling.py` | CRT decoupling engine (box decomposition + 660k-point verification) |
| `research/lrc14_space_partition.py` | Mod-p symmetry partition + principal-class sampling |
| `research/lrc_core.py` | Exact LRC verifier (`Fraction` arithmetic) + fast float channel |
| `research/LRC_14_RUNNERS_FRONTIER_REPORT.md` | Full frontier report (falsification records, coverage tables, LaTeX skeleton) |
| `research/lenz_scan.py`, `research/probes_v4.py` | V4 five-probe toolchain (SOS / annealing+PSLQ / spectral / Shearer / Farkas) |
| `MathWorkspace/crt_decoupling_proof.lean` | Source of the main proof (compiles against mathlib 4.33.0) |

## Reproduction Guide

### Lean 4 proof (main theorem)

```bash
# Requires: elan + Lean 4.33.0 toolchain, mathlib 4.33.0 cache
cd MathWorkspace
cp crt_decoupling_proof.lean temp_verify.lean
lake env lean temp_verify.lean        # expect: no errors, 0 sorry
```

The proof needs `import Mathlib.Tactic` and `set_option maxHeartbeats 2000000` (scoped per declaration).

### CRT decoupling verification (Python)

```bash
python -X utf8 research/lrc14_crt_decoupling.py
# Expect: bidirectional verification 306073 + 357084 points: 通过 ✓
```

Dependencies: `sympy`, `mpmath` (bundled with sympy), `cvxpy` + `clarabel` + `scipy` (optional, for the SOS/Farkas probes).

### Exact LRC certificates

```bash
python -X utf8 -c "from research.lrc_core import lrc_holds; print(lrc_holds([234, 363, 537, 655, 880, 1029, 1630, 1689, 2264, 2291, 2372, 2737, 2834], 14))"
# Expect: True (lonely time exists at t = 113/357084)
```

## Status & Honesty Statement

The **full 14-runner Lonely Runner Conjecture remains open**. This repository provides the boundary certificates, the CRT decoupling lemma (formally proved), the composite-barrier analysis, and the computational infrastructure — the stepping stones toward a generalized sieve for composite *k+1*.

## Citation

```bibtex
@misc{lonelyRunner14Lean4,
  title  = {Formal Verification and CRT Decoupling for 14-Runner Lonely Runner Problem in Lean 4},
  author = {AI Math Institute},
  year   = {2026},
  note   = {Machine-checked Lean 4 proofs and computational certificates},
  doi    = {10.5281/zenodo.XXXXXXX} % replace after Zenodo deposit
}
```
