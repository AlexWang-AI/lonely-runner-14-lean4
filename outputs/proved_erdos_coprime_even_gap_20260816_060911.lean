-- ============================================================
-- AI Math Institute · 自动生成证明脚本
-- 目标: theorem erdos_coprime_even_gap (a b c : ℕ) (h1 : a < b) (h2 : b < c) (hab : Nat.Coprime a b) (hbc : Nat.Coprime b c) (hac : Nat.Coprime a c) (ha : a ≥ 2) (heven : Even a) : c - a ≥ 3
-- 推导步数: 1 | 微调次数: 3
-- 耗时: 560.16 秒
-- 错题本 (本次探索中封存的禁手规则):
-- ============================================================

import Mathlib

theorem erdos_coprime_even_gap (a b c : ℕ) (h1 : a < b) (h2 : b < c)
    (hab : Nat.Coprime a b) (hbc : Nat.Coprime b c) (hac : Nat.Coprime a c) 
    (ha : a ≥ 2) (heven : Even a) : c - a ≥ 3 := by
  by_contra hnot
  have hac_lt : a < c := by omega
  have hlt : c - a < 3 := by omega
  have hc_le : c ≤ a + 2 := by omega
  have hb_eq : b = a + 1 := by omega
  have hc_eq : c = a + 2 := by omega
  rcases heven with ⟨k, hk⟩
  have h2a : 2 ∣ a := by
    use k
    omega
  have h2c : 2 ∣ c := by
    rw [hc_eq]
    use k + 1
    omega
  have hgcd_not : Nat.gcd a c ≠ 1 := by
    intro hgcd_eq
    have hd : 2 ∣ Nat.gcd a c := Nat.dvd_gcd h2a h2c
    rw [hgcd_eq] at hd
    norm_num at hd
  exact hgcd_not hac