# Formal Verification and CRT Decoupling for 14-Runner Lonely Runner Problem in Lean 4

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
<!-- Zenodo DOI badge placeholder: replace XXXXXXX after the first Zenodo deposit -->

## 🎉 World's First 0-sorry Lean 4 Formal Verification of the Universal Weak Lonely Runner Bound (∀k ≥ 1, gap ≥ 1/(2(k+1)))

`outputs/proved_weak_lonely_runner_universal.lean` — the **fully machine-verified universal weak bound** for all runner counts:

```lean
theorem weak_lonely_runner_universal (k : ℕ) (hk : 1 ≤ k)
    (v : Fin k → ℕ+) (h_inj : Function.Injective v) :
    ∃ (t : ℝ), ∀ (i : Fin k), torus_dist ((v i : ℝ) * t) ≥ (1 : ℝ) / (2 * ((k : ℝ) + 1))
```

**Core proof architecture (Measure Subadditivity / non-covering principle):**

1. Forbidden arc of runner *i*: `Forbiddenᵢ = {t ∈ [0,1) : torus_dist(vᵢ·t) < δ}` with `δ = 1/(2(k+1))`;
2. Key lemma `forbidden_measure_le`: `volume(Forbiddenᵢ) ≤ 2δ = 1/(k+1)` — proven by a one-directional containment into the `vᵢ` raw intervals (m = 0 … vᵢ) intersected with `[0,1)`, with exact endpoint-truncation accounting (δ/v + (v−1)·2δ/v + δ/v = 2δ via `sum_range_succ`/`sum_range_succ'` and `Real.volume_Ico`);
3. Finite subadditivity `measure_iUnion_fintype_le` ⟹ `volume(⋃ᵢ Forbiddenᵢ) ≤ k/(k+1) < 1 = volume([0,1))` ⟹ the union cannot cover the unit interval ⟹ a lonely time `t*` exists for **every** k simultaneously.

The proof is fully 0-`sorry`, machine-checked by Lean 4.33.0 / mathlib.

## Abstract

This repository contains machine-checked formal artifacts and computational infrastructure targeting the **14-runner Lonely Runner Conjecture** (LRC, the current global frontier after 13 runners were settled in 2026 via sieving and the polynomial method).

**Core results:**

1. **Composite-barrier diagnosis.** The 2026 polynomial-method lemma requires *k+1* to be an odd prime. For 14 runners, *k+1 = 14* is composite, so the lemma's hypotheses fail — the algebraic root of the current literature gap. Empirically, the principal residue class *v ≡ (1..13) (mod 191)* passes 300/300 sampled instances (tightest gap 5.3e-11), i.e., the lemma's *conclusion* still holds numerically in the composite case — first-hand evidence for a generalized sieve.

2. **660k-point bidirectional verification.** The CRT decoupling engine (`research/lrc14_crt_decoupling.py`) decomposes the certificate-1 legality interval *I = [25506, 331578]* (mod 357084 = 4 × 89271, coprime) into AP-window boxes over *Z₄ × Z₈₉₂₇₁* and verifies the equivalence in both directions by exhaustive enumeration (306,073 + 357,084 points).

3. **0-sorry Lean 4 closure.** The universal decoupling lemma
   `∀ r, (r % 357084 ∈ [25506, 331578]) ↔ (four AP-window branches with bounded ∃t)`
   is formally proved in Lean 4 (`outputs/proved_lrc14_crt_interval_decoupling.lean`), machine-verified with zero `sorry`/`admit`. The proof combines CRT projection lemmas (`Nat.mod_mod_of_dvd`), `wlog` symmetrization, a divisibility chain (`Nat.Coprime.mul_dvd_of_dvd_of_dvd`, `Nat.eq_zero_of_dvd_of_lt`), and `interval_cases`/`omega` branch elimination.

4. **Five exact lonely-time certificates** (zero floating-point error, `Fraction`-verified) for near-degenerate 14-runner speed tuples (tightest covering gap 7.96e-9), produced by an unattended red-blue adversarial siege (simulated annealing + SOS/Farkas/spectral/entropy probes). Certificate 1 is formalized in Lean with a one-shot `norm_num` proof (`outputs/proved_lonely_runner_k13_14runners.lean`).

## Extremal Boundary Certificates (Certificates 1 to 5 Fully Verified in Lean 4)

All five machine-generated lonely-time certificates are now **fully formalized in Lean 4 with zero `sorry`**:

| Certificate | Lonely time `t*` | Speed tuple (first entries) | Lean proof |
|---|---|---|---|
| 1 | 113/357084 | [234, 363, 537, 655, 880, ...] | `outputs/proved_lonely_runner_certificate_1_20260817_012210.lean` |
| 2 | 1496/2320899 | [111, 372, 1008, 1156, 1162, ...] | `outputs/proved_lrc14_cert2.lean` |
| 3 | 603/2680832 | [512, 1064, 1196, 1701, 1826, ...] | `outputs/proved_lrc14_cert3.lean` |
| 4 | 5483/3049760 | [40, 1198, 1294, 1308, 1518, ...] | `outputs/proved_lrc14_cert4.lean` |
| 5 | 71161/181780592 | [184, 633, 1070, 1820, 1888, ...] | `outputs/proved_lrc14_cert5.lean` |

Each proof consists of 26 rational inequalities `(v·t* − ⌊v·t*⌋) ∈ [1/14, 13/14]` closed by a single `norm_num` — zero floating-point error, machine-checked. The **combined bundle** `outputs/LRC14_FULL_5_CERTIFICATES_BUNDLE.lean` compiles all five theorems in one file (verified as a whole).

## Composite Coprime Span Lower Bound Theorem (0-sorry)

`outputs/proved_coprime_composite_gap_lower_bound.lean` — the pigeonhole lower bound behind the *f(k) = 2k−4* conjecture:

```lean
theorem coprime_composite_gap_lower_bound (k : ℕ) (hk : 3 ≤ k)
    (a : Fin k → ℕ) (h_mono : StrictMono a)
    (ha_ge : ∀ i : Fin k, 4 ≤ a i)
    (h_comp : ∀ i : Fin k, ¬ Nat.Prime (a i))
    (h_coprime : ∀ i j : Fin k, i ≠ j → Nat.Coprime (a i) (a j)) :
    2 * k - 4 ≤ a ⟨k - 1, by omega⟩ - a ⟨0, by omega⟩
```

Any *k* pairwise-coprime composites (≥ 4, strictly increasing) span at least `2k − 4`. Proof: at most one can be even (evens share the factor 2) ⟹ at least `k−1` are odd; but a window of `2k−4` consecutive integers contains exactly `k−2` odds (inductive lemma `card_odd_Icc`) — a counting contradiction via injectivity forced by coprimality. Fully machine-verified, zero `sorry`.

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
