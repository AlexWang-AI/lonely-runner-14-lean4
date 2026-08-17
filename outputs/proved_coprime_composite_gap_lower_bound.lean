-- ============================================================
-- AI Math Institute · f(k) >= 2k-4 鸽巢下界 · 架构师手写证明
-- k 个两两互素合数 (>= 4, 严格递增) 的跨度至少 2k-4
-- 证明: 至多一偶数 + 窗口 2m 连续整数恰含 m 个奇数 (归纳)
-- + 奇数值注入窗口奇数集合的计数矛盾 | 0-sorry 机器验证
-- ============================================================

import Mathlib.Tactic

set_option maxHeartbeats 2000000 in
lemma card_odd_Icc (s m : ℕ) :
    (Finset.filter (fun x : ℕ => Odd x) (Finset.Icc s (s + 2 * m - 1))).card = m := by
  induction m with
  | zero =>
      by_contra hc
      have hpos : 1 ≤ (Finset.filter (fun x : ℕ => Odd x) (Finset.Icc s (s + 2 * 0 - 1))).card := by omega
      rcases Finset.card_pos.mp hpos with ⟨x, hx⟩
      rw [Finset.mem_filter] at hx
      rcases hx with ⟨hx1, hx2⟩
      rw [Finset.mem_Icc] at hx1
      rw [Odd] at hx2
      rcases hx2 with ⟨kk, hk⟩
      omega
  | succ m ih =>
      have hsplit : Finset.Icc s (s + 2 * (m + 1) - 1) =
          Finset.Icc s (s + 2 * m - 1) ∪ Finset.Icc (s + 2 * m) (s + 2 * m + 1) := by
        ext x
        simp only [Finset.mem_Icc, Finset.mem_union]
        constructor
        · intro hx
          by_cases hxm : x ≤ s + 2 * m - 1
          · exact Or.inl ⟨hx.1, hxm⟩
          · right
            have h1 : s + 2 * m ≤ x := by omega
            have h2 : x ≤ s + 2 * m + 1 := by omega
            exact ⟨h1, h2⟩
        · intro hx
          rcases hx with hl | hr
          · have h2 : s + 2 * m - 1 ≤ s + 2 * (m + 1) - 1 := by omega
            exact ⟨hl.1, le_trans hl.2 h2⟩
          · have h2 : s + 2 * m + 1 ≤ s + 2 * (m + 1) - 1 := by omega
            exact ⟨le_trans (by omega : s ≤ s + 2 * m) hr.1, le_trans hr.2 h2⟩
      have hcard2 : (Finset.filter (fun x : ℕ => Odd x)
                       (Finset.Icc (s + 2 * m) (s + 2 * m + 1))).card = 1 := by
        have hicc : Finset.Icc (s + 2 * m) (s + 2 * m + 1) = {s + 2 * m, s + 2 * m + 1} := by
          ext x
          simp only [Finset.mem_Icc, Finset.mem_insert, Finset.mem_singleton]
          omega
        rw [hicc]
        by_cases ho : Odd (s + 2 * m)
        · have he : ¬ Odd (s + 2 * m + 1) := by
            rw [Odd]
            push_neg
            intro k hk
            rw [Odd] at ho
            rcases ho with ⟨k', hk'⟩
            omega
          have hf : Finset.filter (fun x : ℕ => Odd x) ({s + 2 * m, s + 2 * m + 1} : Finset ℕ) = {s + 2 * m} := by
            ext x
            simp only [Finset.mem_filter, Finset.mem_insert, Finset.mem_singleton]
            constructor
            · intro hx
              rcases hx.1 with h | h
              · exact h
              · exact False.elim (he (by simpa [h] using hx.2))
            · intro hx
              exact ⟨Or.inl hx, by rwa [hx]⟩
          rw [hf]
          simp
        · have he : Odd (s + 2 * m + 1) := by
            rw [Odd]
            have heven : Even (s + 2 * m) := by
              rcases Nat.even_or_odd (s + 2 * m) with h | h
              · exact h
              · exact False.elim (ho h)
            rcases heven with ⟨k', hk'⟩
            refine ⟨k', ?_⟩
            omega
          have hf : Finset.filter (fun x : ℕ => Odd x) ({s + 2 * m, s + 2 * m + 1} : Finset ℕ) = {s + 2 * m + 1} := by
            ext x
            simp only [Finset.mem_filter, Finset.mem_insert, Finset.mem_singleton]
            constructor
            · intro hx
              rcases hx.1 with h | h
              · exact False.elim (ho (by simpa [h] using hx.2))
              · exact h
            · intro hx
              exact ⟨Or.inr hx, by rwa [hx]⟩
          rw [hf]
          simp
      have hdisj' : Disjoint (Finset.filter (fun x : ℕ => Odd x) (Finset.Icc s (s + 2 * m - 1)))
                             (Finset.filter (fun x : ℕ => Odd x) (Finset.Icc (s + 2 * m) (s + 2 * m + 1))) := by
        rw [Finset.disjoint_left]
        intro x hx1 hx2
        rw [Finset.mem_filter] at hx1 hx2
        rw [Finset.mem_Icc] at hx1 hx2
        rw [Odd] at hx1
        rcases hx1.2 with ⟨kk, hk⟩
        have hx1' : x + 1 ≤ s + 2 * m := by omega
        omega
      rw [hsplit, Finset.filter_union]
      rw [Finset.card_union_of_disjoint hdisj']
      rw [ih, hcard2]

set_option maxHeartbeats 2000000 in
theorem coprime_composite_gap_lower_bound (k : ℕ) (hk : 3 ≤ k)
    (a : Fin k → ℕ) (h_mono : StrictMono a)
    (ha_ge : ∀ i : Fin k, 4 ≤ a i)
    (h_comp : ∀ i : Fin k, ¬ Nat.Prime (a i))
    (h_coprime : ∀ i j : Fin k, i ≠ j → Nat.Coprime (a i) (a j)) :
    2 * k - 4 ≤ a ⟨k - 1, by omega⟩ - a ⟨0, by omega⟩ := by
  by_contra hlt
  have h_bounded : ∀ i : Fin k, a i ≤ a ⟨0, by omega⟩ + (2 * k - 5) := by
    intro i
    have hil : (i : ℕ) < k := i.isLt
    have hi : a i ≤ a ⟨k - 1, by omega⟩ := h_mono.monotone (by
      change (i : ℕ) ≤ k - 1
      have hil1 : (i : ℕ) + 1 ≤ k := by omega
      omega)
    have hlast : a ⟨k - 1, by omega⟩ ≤ a ⟨0, by omega⟩ + (2 * k - 5) := by
      have hle0 : a ⟨0, by omega⟩ ≤ a ⟨k - 1, by omega⟩ := h_mono.monotone (by
        change (⟨0, by omega⟩ : Fin k).1 ≤ k - 1
        simpa using (by omega : 0 ≤ k - 1))
      have hdlt : a ⟨k - 1, by omega⟩ - a ⟨0, by omega⟩ ≤ 2 * k - 5 := by omega
      have hsub : a ⟨k - 1, by omega⟩ =
          a ⟨0, by omega⟩ + (a ⟨k - 1, by omega⟩ - a ⟨0, by omega⟩) := by omega
      omega
    exact le_trans hi hlast
  have h_lower : ∀ i : Fin k, a ⟨0, by omega⟩ ≤ a i := by
    intro i
    exact h_mono.monotone (by
      change (⟨0, by omega⟩ : Fin k).1 ≤ (i : ℕ)
      simpa using (Nat.zero_le (i : ℕ)))
  -- 至多一个偶数
  have h_even_one : ∀ i j : Fin k, i ≠ j → ¬ (Even (a i) ∧ Even (a j)) := by
    intro i j hij hboth
    have hg : Nat.gcd (a i) (a j) = 1 := (h_coprime i j hij).gcd_eq_one
    have h2i : 2 ∣ a i := hboth.1.two_dvd
    have h2j : 2 ∣ a j := hboth.2.two_dvd
    have h2g : 2 ∣ Nat.gcd (a i) (a j) := Nat.dvd_gcd h2i h2j
    rw [hg] at h2g
    norm_num at h2g
  -- 互异
  have h_inj : Function.Injective a := by
    intro i j hij
    by_contra hne
    have hcp : Nat.Coprime (a i) (a j) := h_coprime i j hne
    have hg1 : Nat.gcd (a i) (a j) = 1 := hcp.gcd_eq_one
    have hg_self : Nat.gcd (a i) (a j) = a i := by rw [hij]; exact Nat.gcd_self _
    have ha1 : a i = 1 := by rw [← hg_self, hg1]
    have hge := ha_ge i
    omega
  let s := a ⟨0, by omega⟩
  let odds := Finset.univ.filter (fun i : Fin k => Odd (a i))
  let evens := Finset.univ.filter (fun i : Fin k => Even (a i))
  have h_even_count : evens.card ≤ 1 := by
    dsimp [evens]
    rw [Finset.card_le_one_iff]
    intro i j h1 h2
    by_contra hne
    have hi' := Finset.mem_filter.mp h1
    have hj' := Finset.mem_filter.mp h2
    exact h_even_one i j hne ⟨hi'.2, hj'.2⟩
  have h_odd_count : odds.card ≥ k - 1 := by
    have hdisj : Disjoint odds evens := by
      rw [Finset.disjoint_left]
      intro i hi1 hi2
      dsimp [odds, evens] at hi1 hi2
      have h1' := Finset.mem_filter.mp hi1
      have h2' := Finset.mem_filter.mp hi2
      rw [Odd] at h1'
      rcases h1'.2 with ⟨kk, hk⟩
      rw [Even] at h2'
      rcases h2'.2 with ⟨kk2, hk2⟩
      omega
    have hcov : odds ∪ evens = Finset.univ := by
      ext i
      simp only [odds, evens, Finset.mem_union, Finset.mem_filter, Finset.mem_univ,
                 true_and]
      exact ⟨fun _ => trivial, fun _ => by
        rcases Nat.even_or_odd (a i) with h | h
        · exact Or.inr h
        · exact Or.inl h⟩
    have hsum : odds.card + evens.card = (Finset.univ : Finset (Fin k)).card := by
      rw [← hcov, Finset.card_union_of_disjoint hdisj]
    have huniv : (Finset.univ : Finset (Fin k)).card = k := by
      rw [Finset.card_univ]
      exact Fintype.card_fin k
    omega
  have h_window_odds : odds.card ≤ k - 2 := by
    let w := Finset.filter (fun x : ℕ => Odd x) (Finset.Icc s (s + 2 * k - 5))
    have hw_eq : w.card = k - 2 := by
      dsimp [w]
      have h1 : s + 2 * k - 5 = s + 2 * (k - 2) - 1 := by omega
      rw [h1]
      exact card_odd_Icc s (k - 2)
    have h_img : odds.image a ⊆ w := by
      intro x hx
      rw [Finset.mem_image] at hx
      rcases hx with ⟨i, hi, rfl⟩
      rw [Finset.mem_filter]
      constructor
      · rw [Finset.mem_Icc]
        constructor
        · dsimp [s]
          exact h_lower i
        · dsimp [s]
          have hk5 : 5 ≤ 2 * k := by omega
          have hsub : a ⟨0, by omega⟩ + (2 * k - 5) = a ⟨0, by omega⟩ + 2 * k - 5 := by omega
          rw [← hsub]
          exact h_bounded i
      · dsimp [odds] at hi
        exact (Finset.mem_filter.mp hi).2
    have hcard_img : (odds.image a).card = odds.card := by
      exact Finset.card_image_of_injective _ h_inj
    have hle : (odds.image a).card ≤ w.card := Finset.card_le_card h_img
    rw [hcard_img, hw_eq] at hle
    exact hle
  omega
