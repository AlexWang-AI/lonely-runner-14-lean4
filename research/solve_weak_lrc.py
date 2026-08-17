"""
solve_weak_lrc.py — N1 攻坚驱动: 通用弱孤独跑者界 (∀k) 0-sorry 闭环

测度蓝图 (修正常数 1/(2(k+1))):
  禁区 Forbidden_i = {t ∈ [0,1) : torus_dist(v_i·t) < δ}, δ = 1/(2(k+1))
  μ(Forbidden_i) ≤ 2δ = 1/(k+1)  (单方向包含 + 截断区间精确计账)
  ⟹ μ(⋃ Forbidden_i) ≤ k/(k+1) < 1 = μ([0,1)) ⟹ 覆盖不可能 ⟹ ∃t* 全孤独

驱动: 架构师手写证明草稿 → LeanValidator 迭代验证 → 0-sorry 落盘。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DRAFT = r"""import Mathlib.MeasureTheory.Measure.Lebesgue.Basic
import Mathlib.Tactic

noncomputable section
open MeasureTheory

def torus_dist (x : ℝ) : ℝ := |x - round x|

set_option maxHeartbeats 400000 in
lemma forbidden_measure_le (v : ℕ) (hv : 1 ≤ v) (δ : ℝ) (hδ0 : 0 ≤ δ) (hδ1 : 2 * δ ≤ 1) :
    volume {t | t ∈ Set.Ico (0 : ℝ) 1 ∧ torus_dist ((v : ℝ) * t) < δ} ≤ ENNReal.ofReal (2 * δ) := by
  let U := ⋃ m ∈ Finset.range (v + 1),
    Set.Ico (((m : ℝ) - δ) / v) (((m : ℝ) + δ) / v) ∩ Set.Ico (0 : ℝ) 1
  have hsub : {t | t ∈ Set.Ico (0 : ℝ) 1 ∧ torus_dist ((v : ℝ) * t) < δ} ⊆ U := by
    intro t ht
    rcases ht with ⟨ht0, htd⟩
    let m := (round ((v : ℝ) * t)).toNat
    have hm0 : 0 ≤ (round ((v : ℝ) * t) : ℤ) := by
      exact_mod_cast (round_nonneg (by positivity : 0 ≤ (v : ℝ) * t))
    have hmv : (round ((v : ℝ) * t) : ℤ) ≤ (v : ℤ) := by
      have ht1 : t < 1 := ht0.2
      have hvt : (v : ℝ) * t < v := by
        have hvpos : 0 < (v : ℝ) := by positivity
        nlinarith [mul_lt_mul_of_pos_left ht1 hvpos]
      have hr : round ((v : ℝ) * t) ≤ ((v : ℝ) * t) + 1 / 2 := round_le ((v : ℝ) * t)
      have hz : (round ((v : ℝ) * t) : ℝ) < v + 1 / 2 := by linarith
      have hzz : (round ((v : ℝ) * t) : ℤ) < (v : ℤ) + 1 := by
        norm_num at hz ⊢
        exact_mod_cast hz
      omega
    have hm_range : m < v + 1 := by
      dsimp [m]
      rw [Int.toNat_lt_toNat]
      omega
    have hmeq : ((m : ℝ)) = (round ((v : ℝ) * t) : ℤ) := by
      dsimp [m]
      exact_mod_cast (Int.toNat_of_nonneg hm0)
    have hmIcc : m ∈ Finset.range (v + 1) := by
      rw [Finset.mem_range]
      exact hm_range
    rw [Set.mem_iUnion₂]
    refine ⟨m, hmIcc, ?_⟩
    constructor
    · rw [Set.mem_Ico]
      constructor
      · rw [div_le_iff₀ (by positivity : 0 < (v : ℝ))]
        have habs : |(v : ℝ) * t - (m : ℝ)| < δ := by
          dsimp [torus_dist] at htd
          rw [hmeq] at htd
          exact htd
        have h1 : (m : ℝ) - δ ≤ (v : ℝ) * t := by
          nlinarith [(abs_lt.mp habs).1]
        nlinarith [h1, mul_comm]
      · rw [div_lt_iff₀ (by positivity : 0 < (v : ℝ))]
        have habs : |(v : ℝ) * t - (m : ℝ)| < δ := by
          dsimp [torus_dist] at htd
          rw [hmeq] at htd
          exact htd
        have h2 : (v : ℝ) * t < (m : ℝ) + δ := by
          nlinarith [(abs_lt.mp habs).2]
        nlinarith [h2, mul_comm]
    · exact ht0
  have h_meas : ∀ m ∈ Finset.range (v + 1),
      MeasurableSet (Set.Ico (((m : ℝ) - δ) / v) (((m : ℝ) + δ) / v) ∩ Set.Ico (0 : ℝ) 1) := by
    intro m hm
    exact measurableSet_Ico.inter measurableSet_Ico
  have h_disj : Set.PairwiseDisjoint (Finset.range (v + 1))
      (fun m => Set.Ico (((m : ℝ) - δ) / v) (((m : ℝ) + δ) / v) ∩ Set.Ico (0 : ℝ) 1) := by
    intro m hm n hn hmn
    rw [Set.disjoint_left]
    intro t ht1 ht2
    rw [Set.mem_inter_iff] at ht1 ht2
    rcases ht1 with ⟨ht1a, ht1b⟩
    rcases ht2 with ⟨ht2a, ht2b⟩
    rw [Set.mem_Ico] at ht1a ht2a
    have hord : m < n ∨ n < m := by omega
    rcases hord with hlt | hgt
    · have hz : (m : ℝ) + δ ≤ (n : ℝ) - δ := by
        have hm1 : m + 1 ≤ n := by omega
        have hm1r : (m : ℝ) + 1 ≤ (n : ℝ) := by exact_mod_cast hm1
        nlinarith [hδ1]
      nlinarith [ht1a.2, ht2a.1, hz]
    · have hz : (n : ℝ) + δ ≤ (m : ℝ) - δ := by
        have hn1 : n + 1 ≤ m := by omega
        have hn1r : (n : ℝ) + 1 ≤ (m : ℝ) := by exact_mod_cast hn1
        nlinarith [hδ1]
      nlinarith [ht2a.2, ht1a.1, hz]
  have hU : volume U ≤ ENNReal.ofReal (2 * δ) := by
    dsimp [U]
    calc
      volume (⋃ m ∈ Finset.range (v + 1), Set.Ico (((m : ℝ) - δ) / v) (((m : ℝ) + δ) / v) ∩ Set.Ico (0 : ℝ) 1)
          ≤ ∑ m ∈ Finset.range (v + 1), volume (Set.Ico (((m : ℝ) - δ) / v) (((m : ℝ) + δ) / v) ∩ Set.Ico (0 : ℝ) 1) :=
              measure_biUnion_finset_le h_disj h_meas
      _ ≤ ENNReal.ofReal (δ / v) + ENNReal.ofReal (((v - 1 : ℕ) : ℝ) * (2 * δ / v)) + ENNReal.ofReal (δ / v) := by
          have hsplit : ∑ m ∈ Finset.range (v + 1), volume (Set.Ico (((m : ℝ) - δ) / v) (((m : ℝ) + δ) / v) ∩ Set.Ico (0 : ℝ) 1)
              = ENNReal.ofReal (δ / v) + ENNReal.ofReal (((v - 1 : ℕ) : ℝ) * (2 * δ / v)) + ENNReal.ofReal (δ / v) := by
            let f := fun m : ℕ => volume (Set.Ico (((m : ℝ) - δ) / v) (((m : ℝ) + δ) / v) ∩ Set.Ico (0 : ℝ) 1)
            have hvpos : 0 < (v : ℝ) := by positivity
            have hδle1 : δ ≤ 1 := by nlinarith
            have hlast : f v = ENNReal.ofReal (δ / v) := by
              dsimp [f]
              have heq : Set.Ico (((v : ℝ) - δ) / v) (((v : ℝ) + δ) / v) ∩ Set.Ico (0 : ℝ) 1 = Set.Ico (((v : ℝ) - δ) / v) 1 := by
                ext x
                simp only [Set.mem_inter_iff, Set.mem_Ico]
                constructor
                · intro hx
                  exact ⟨hx.1.1, hx.2⟩
                · intro hx
                  have hδv : δ ≤ (v : ℝ) := by nlinarith [hδle1, (show (1 : ℝ) ≤ v by exact_mod_cast hv)]
                  constructor
                  · constructor
                    · exact hx.1
                    · nlinarith [hδv]
                  · exact hx.2
              rw [heq, Real.volume_Ico]
              norm_num
              congr 1
              field_simp [show (v : ℝ) ≠ 0 by positivity]
              ring
            have hfirst : f 0 = ENNReal.ofReal (δ / v) := by
              dsimp [f]
              have heq : Set.Ico (((0 : ℝ) - δ) / v) (((0 : ℝ) + δ) / v) ∩ Set.Ico (0 : ℝ) 1 = Set.Ico (0 : ℝ) (δ / v) := by
                ext x
                simp only [Set.mem_inter_iff, Set.mem_Ico]
                constructor
                · intro hx
                  constructor
                  · linarith [hx.2.1]
                  · exact hx.1.2
                · intro hx
                  have hδv : δ / v ≤ 1 := by
                    rw [div_le_one hvpos]
                    exact hδle1
                  constructor
                  · constructor
                    · linarith [hδ0]
                    · exact hx.2
                  · exact hx.1
              rw [heq, Real.volume_Ico]
              norm_num
              congr 1
              field_simp [show (v : ℝ) ≠ 0 by positivity]
              ring
            have hmid : ∀ m ∈ Finset.range (v - 1), f (m + 1) = ENNReal.ofReal (2 * δ / v) := by
              intro m hm
              rw [Finset.mem_range] at hm
              dsimp [f]
              have heq : Set.Ico ((((m + 1 : ℕ) : ℝ) - δ) / v) ((((m + 1 : ℕ) : ℝ) + δ) / v) ∩ Set.Ico (0 : ℝ) 1 = Set.Ico ((((m + 1 : ℕ) : ℝ) - δ) / v) ((((m + 1 : ℕ) : ℝ) + δ) / v) := by
                ext x
                simp only [Set.mem_inter_iff, Set.mem_Ico]
                constructor
                · intro hx
                  exact hx.1
                · intro hx
                  have hm1 : 1 ≤ m + 1 := by omega
                  have hmm : m + 1 ≤ v - 1 := by omega
                  have hlo : 0 ≤ ((m + 1 : ℕ) : ℝ) - δ := by
                    have hmr : (1 : ℝ) ≤ ((m + 1 : ℕ) : ℝ) := by exact_mod_cast hm1
                    nlinarith [hmr, hδle1]
                  have hhi : ((m + 1 : ℕ) : ℝ) + δ ≤ (v : ℝ) := by
                    have hmr : ((m + 1 : ℕ) : ℝ) ≤ (v : ℝ) - 1 := by
                      have hmmr : (m + 1 : ℕ) ≤ v - 1 := by omega
                      exact_mod_cast hmmr
                    nlinarith [hmr, hδle1]
                  constructor
                  · constructor
                    · nlinarith [hlo]
                    · nlinarith [hhi]
                  · exact hx.2
              rw [heq, Real.volume_Ico]
              norm_num
              congr 1
              field_simp [show (v : ℝ) ≠ 0 by positivity]
              ring
            have hsummid : ∑ m ∈ Finset.range (v - 1), f (m + 1) = ENNReal.ofReal (((v - 1 : ℕ) : ℝ) * (2 * δ / v)) := by
              calc
                ∑ m ∈ Finset.range (v - 1), f (m + 1)
                    = ∑ m ∈ Finset.range (v - 1), ENNReal.ofReal (2 * δ / v) := by
                        exact Finset.sum_congr rfl (by intro m hm; exact hmid m hm)
                _ = ENNReal.ofReal (((v - 1 : ℕ) : ℝ) * (2 * δ / v)) := by
                    simp [Finset.sum_const, Finset.card_range, nsmul_eq_mul,
                          ENNReal.ofReal_nsmul, ENNReal.ofReal_mul]
            dsimp [f]
            rw [Finset.sum_range_succ', Finset.sum_range_succ]
            rw [hfirst, hsummid, hlast]
          rw [hsplit]
      _ = ENNReal.ofReal (2 * δ) := by
          rw [← ENNReal.ofReal_add, ← ENNReal.ofReal_add]
          congr 1
          have hδle : δ ≤ 1 := by nlinarith
          have h1pos : 0 ≤ (v : ℝ) - 1 := by exact_mod_cast (Nat.sub_pos_of_lt (lt_of_le_of_lt hv (Nat.lt_succ_self v)))
          field_simp [show (v : ℝ) ≠ 0 by positivity]
          ring
  exact (measure_mono hsub).trans hU

set_option maxHeartbeats 400000 in
theorem weak_lonely_runner_universal (k : ℕ) (hk : 1 ≤ k)
    (v : Fin k → ℕ+) (h_inj : Function.Injective v) :
    ∃ (t : ℝ), ∀ (i : Fin k), torus_dist ((v i : ℝ) * t) ≥ (1 : ℝ) / (2 * ((k : ℝ) + 1)) := by
  let δ : ℝ := 1 / (2 * ((k : ℝ) + 1))
  have hδ0 : 0 ≤ δ := by dsimp [δ]; positivity
  have hδ1 : 2 * δ ≤ 1 := by
    dsimp [δ]
    have hk' : 0 < (k : ℝ) + 1 := by positivity
    field_simp
    nlinarith
  by_contra h
  push_neg at h
  have hcover : Set.Ico (0 : ℝ) 1 ⊆ ⋃ i : Fin k, {t | t ∈ Set.Ico (0 : ℝ) 1 ∧ torus_dist ((v i : ℝ) * t) < δ} := by
    intro t ht
    rcases h t with ⟨i, hi⟩
    exact Set.mem_iUnion.mpr ⟨i, ⟨ht, hi⟩⟩
  have hmu : volume (⋃ i : Fin k, {t | t ∈ Set.Ico (0 : ℝ) 1 ∧ torus_dist ((v i : ℝ) * t) < δ}) ≤ ENNReal.ofReal (k * (1 / ((k : ℝ) + 1))) := by
    calc
      volume (⋃ i : Fin k, {t | t ∈ Set.Ico (0 : ℝ) 1 ∧ torus_dist ((v i : ℝ) * t) < δ})
          ≤ ∑ i : Fin k, volume {t | t ∈ Set.Ico (0 : ℝ) 1 ∧ torus_dist ((v i : ℝ) * t) < δ} := by
              exact measure_iUnion_fintype_le
                (fun i => {t | t ∈ Set.Ico (0 : ℝ) 1 ∧ torus_dist ((v i : ℝ) * t) < δ})
      _ ≤ ∑ i : Fin k, ENNReal.ofReal (2 * δ) := by
          apply Finset.sum_le_sum
          intro i hi
          exact forbidden_measure_le (v i) (by exact PNat.one_le (v i)) δ hδ0 hδ1
      _ = ENNReal.ofReal (k * (1 / ((k : ℝ) + 1))) := by
          simp [δ, Finset.sum_const, Finset.card_fin, nsmul_eq_mul, ENNReal.ofReal_mul]
  have hvol : volume (Set.Ico (0 : ℝ) 1) = ENNReal.ofReal (1 : ℝ) := by
    rw [Real.volume_Ico]
    norm_num
  have hmono : volume (Set.Ico (0 : ℝ) 1) ≤ volume (⋃ i : Fin k, {t | t ∈ Set.Ico (0 : ℝ) 1 ∧ torus_dist ((v i : ℝ) * t) < δ}) :=
    measure_mono hcover
  have hbad : ENNReal.ofReal (1 : ℝ) ≤ ENNReal.ofReal (k * (1 / ((k : ℝ) + 1))) := by
    rw [hvol] at hmono
    exact hmono.trans hmu
  have hreal : (1 : ℝ) ≤ k * (1 / ((k : ℝ) + 1)) := by
    exact_mod_cast (ENNReal.ofReal_le_ofReal_iff.mpr ?_ ▸ hbad)
  have hlt : k * (1 / ((k : ℝ) + 1)) < 1 := by
    have hkpos : 0 < (k : ℝ) + 1 := by positivity
    rw [mul_div_assoc]
    have : (k : ℝ) / ((k : ℝ) + 1) < 1 := by
      rw [div_lt_one hkpos]
      linarith
    simpa using this
  nlinarith
"""


def main() -> None:
    import os
    os.system("")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from agent_core.lean_verifier import LeanValidator
    v = LeanValidator(worker_id="weaklrc", use_server=True,
                      server_prelude=(
                          "import Mathlib.MeasureTheory.Measure.Lebesgue.Basic\n"
                          "import Mathlib.Tactic"),
                      prelude_ladder=())
    v.warmup()
    r = v.verify_code(DRAFT, 400)
    print("验证:", r["status"])
    print((r["message"] or "")[:800])
    if r["status"] == "success":
        dst = _ROOT / "outputs" / "proved_weak_lonely_runner_universal.lean"
        dst.write_text(
            "-- ============================================================\n"
            "-- AI Math Institute · 通用弱孤独跑者界 (∀k) · 0-sorry 机器验证\n"
            "-- 测度非满覆盖原理: μ(∪Forbidden) ≤ k/(k+1) < 1 = μ([0,1))\n"
            "-- ============================================================\n\n"
            + DRAFT, encoding="utf-8")
        print("✅ 已落盘:", dst)


if __name__ == "__main__":
    main()
