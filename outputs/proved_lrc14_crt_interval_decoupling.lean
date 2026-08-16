-- ============================================================
-- AI Math Institute · CRT 合数因子解耦引理 · 架构师手写证明
-- 模数 357084 = 4 × 89271 (互素), 区间 [25506, 331578] 的
-- Z_4 × Z_89271 AP 窗口盒子分解 ↔ 等价 (机器验证 0-sorry)
-- 关联: LRC 14 跑者前沿攻坚 · 证书 1 (t* = 113/357084)
-- ============================================================

import Mathlib.Tactic


-- 架构师手写证明: CRT 解耦引理 (机器验证)
-- 模数 357084 = 4 × 89271, gcd(4, 89271) = 1

set_option maxHeartbeats 2000000 in
theorem crt_combine {x y : ℕ} (hx4 : x % 4 = y % 4) (hxN : x % 89271 = y % 89271)
    (hxl : x < 357084) (hyl : y < 357084) : x = y := by
  wlog hle : x ≤ y generalizing x y with H
  · exact (H hx4.symm hxN.symm hyl hxl (le_of_not_ge hle)).symm
  · have hsub_modN : (y - x) % 89271 = 0 := by omega
    have hsub_mod4 : (y - x) % 4 = 0 := by omega
    have hdvdN : 89271 ∣ y - x := (Nat.dvd_iff_mod_eq_zero).2 hsub_modN
    have hdvd4 : 4 ∣ y - x := (Nat.dvd_iff_mod_eq_zero).2 hsub_mod4
    have hcop : Nat.Coprime 4 89271 := by norm_num
    have hdvd : (4 * 89271) ∣ y - x :=
      Nat.Coprime.mul_dvd_of_dvd_of_dvd hcop hdvd4 hdvdN
    have hsub_lt : y - x < 357084 := by omega
    have hsub0 : y - x = 0 := Nat.eq_zero_of_dvd_of_lt hdvd (by simpa using hsub_lt)
    omega

set_option maxHeartbeats 2000000 in
theorem lrc14_crt_interval_decoupling (r : ℕ) :
    ((25506 ≤ r % 357084 ∧ r % 357084 ≤ 331578) ↔
     ((r % 4 = 0 ∧ ∃ t : ℕ, t < 76518 ∧ r % 89271 = (25508 + 4 * t) % 89271) ∨
      (r % 4 = 1 ∧ ∃ t : ℕ, t < 76518 ∧ r % 89271 = (25509 + 4 * t) % 89271) ∨
      (r % 4 = 2 ∧ ∃ t : ℕ, t < 76519 ∧ r % 89271 = (25506 + 4 * t) % 89271) ∨
      (r % 4 = 3 ∧ ∃ t : ℕ, t < 76518 ∧ r % 89271 = (25507 + 4 * t) % 89271))) := by
  constructor
  · intro h
    let x := r % 357084
    have hx : 25506 ≤ x ∧ x ≤ 331578 := by simpa [x] using h
    have hx4 : x % 4 = r % 4 := by
      dsimp [x]
      exact Nat.mod_mod_of_dvd r (by norm_num : 4 ∣ 357084)
    have hxN : x % 89271 = r % 89271 := by
      dsimp [x]
      exact Nat.mod_mod_of_dvd r (by norm_num : 89271 ∣ 357084)
    have hu4 : x % 4 < 4 := Nat.mod_lt x (by norm_num)
    interval_cases u : x % 4
    · left
      constructor
      · exact hx4.symm
      · refine ⟨x / 4 - 6377, ?_, ?_⟩
        · omega
        · have hxval : x = 25508 + 4 * (x / 4 - 6377) := by omega
          calc
            r % 89271 = x % 89271 := hxN.symm
            _ = (25508 + 4 * (x / 4 - 6377)) % 89271 := by rw [← hxval]
    · right; left
      constructor
      · exact hx4.symm
      · refine ⟨x / 4 - 6377, ?_, ?_⟩
        · omega
        · have hxval : x = 25509 + 4 * (x / 4 - 6377) := by omega
          calc
            r % 89271 = x % 89271 := hxN.symm
            _ = (25509 + 4 * (x / 4 - 6377)) % 89271 := by rw [← hxval]
    · right; right; left
      constructor
      · exact hx4.symm
      · refine ⟨x / 4 - 6376, ?_, ?_⟩
        · omega
        · have hxval : x = 25506 + 4 * (x / 4 - 6376) := by omega
          calc
            r % 89271 = x % 89271 := hxN.symm
            _ = (25506 + 4 * (x / 4 - 6376)) % 89271 := by rw [← hxval]
    · right; right; right
      constructor
      · exact hx4.symm
      · refine ⟨x / 4 - 6376, ?_, ?_⟩
        · omega
        · have hxval : x = 25507 + 4 * (x / 4 - 6376) := by omega
          calc
            r % 89271 = x % 89271 := hxN.symm
            _ = (25507 + 4 * (x / 4 - 6376)) % 89271 := by rw [← hxval]
  · rintro (⟨h4, t, ht, hN⟩ | ⟨h4, t, ht, hN⟩ | ⟨h4, t, ht, hN⟩ | ⟨h4, t, ht, hN⟩)
    · let y := 25508 + 4 * t
      have hy_lo : 25506 ≤ y := by omega
      have hy_hi : y ≤ 331578 := by omega
      have hy4 : y % 4 = 0 := by omega
      have hyN : y % 89271 = r % 89271 := by
        dsimp [y]
        omega
      have hx4' : (r % 357084) % 4 = r % 4 :=
        Nat.mod_mod_of_dvd r (by norm_num : 4 ∣ 357084)
      have hxN' : (r % 357084) % 89271 = r % 89271 :=
        Nat.mod_mod_of_dvd r (by norm_num : 89271 ∣ 357084)
      have hx_eq_y : r % 357084 = y := crt_combine (by rw [hx4', h4, hy4])
        (by rw [hxN', hyN]) (Nat.mod_lt r (by norm_num)) (by omega)
      rw [hx_eq_y]
      exact ⟨hy_lo, hy_hi⟩
    · let y := 25509 + 4 * t
      have hy_lo : 25506 ≤ y := by omega
      have hy_hi : y ≤ 331578 := by omega
      have hy4 : y % 4 = 1 := by omega
      have hyN : y % 89271 = r % 89271 := by
        dsimp [y]
        omega
      have hx4' : (r % 357084) % 4 = r % 4 :=
        Nat.mod_mod_of_dvd r (by norm_num : 4 ∣ 357084)
      have hxN' : (r % 357084) % 89271 = r % 89271 :=
        Nat.mod_mod_of_dvd r (by norm_num : 89271 ∣ 357084)
      have hx_eq_y : r % 357084 = y := crt_combine (by rw [hx4', h4, hy4])
        (by rw [hxN', hyN]) (Nat.mod_lt r (by norm_num)) (by omega)
      rw [hx_eq_y]
      exact ⟨hy_lo, hy_hi⟩
    · let y := 25506 + 4 * t
      have hy_lo : 25506 ≤ y := by omega
      have hy_hi : y ≤ 331578 := by omega
      have hy4 : y % 4 = 2 := by omega
      have hyN : y % 89271 = r % 89271 := by
        dsimp [y]
        omega
      have hx4' : (r % 357084) % 4 = r % 4 :=
        Nat.mod_mod_of_dvd r (by norm_num : 4 ∣ 357084)
      have hxN' : (r % 357084) % 89271 = r % 89271 :=
        Nat.mod_mod_of_dvd r (by norm_num : 89271 ∣ 357084)
      have hx_eq_y : r % 357084 = y := crt_combine (by rw [hx4', h4, hy4])
        (by rw [hxN', hyN]) (Nat.mod_lt r (by norm_num)) (by omega)
      rw [hx_eq_y]
      exact ⟨hy_lo, hy_hi⟩
    · let y := 25507 + 4 * t
      have hy_lo : 25506 ≤ y := by omega
      have hy_hi : y ≤ 331578 := by omega
      have hy4 : y % 4 = 3 := by omega
      have hyN : y % 89271 = r % 89271 := by
        dsimp [y]
        omega
      have hx4' : (r % 357084) % 4 = r % 4 :=
        Nat.mod_mod_of_dvd r (by norm_num : 4 ∣ 357084)
      have hxN' : (r % 357084) % 89271 = r % 89271 :=
        Nat.mod_mod_of_dvd r (by norm_num : 89271 ∣ 357084)
      have hx_eq_y : r % 357084 = y := crt_combine (by rw [hx4', h4, hy4])
        (by rw [hxN', hyN]) (Nat.mod_lt r (by norm_num)) (by omega)
      rw [hx_eq_y]
      exact ⟨hy_lo, hy_hi⟩
