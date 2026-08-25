-- ============================================================
-- AI Math Institute · 自动生成证明脚本
-- 目标: theorem demo_sqrt2_irrational : Irrational (Real.sqrt 2)
-- 推导步数: 1 | 微调次数: 0
-- 耗时: 238.08 秒
-- 错题本 (本次探索中封存的禁手规则):
-- ============================================================

import Mathlib

theorem demo_sqrt2_irrational : Irrational (Real.sqrt 2) := by
  simpa using irrational_sqrt_two