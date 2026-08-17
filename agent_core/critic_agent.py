"""
critic_agent.py — 审阅者智能体 (Critic Agent)

职责 (Phase 2 实现):
1. 审阅 Prover Agent 生成的 Lean 4 证明
2. 解析 LeanVerifier 的错误输出, 将其翻译为可操作的数学反馈
   (类型错误/作用域错误/缺失引理/策略失败 → 分类与定位)
3. 调用 DeepSeek Chat API (deepseek-chat) 评估证明的:
   - 正确性 (与命题语义是否一致)
   - 优雅度 (是否引入多余假设 / 强定理套弱结论)
4. 为 Prover Agent 生成结构化修正建议, 或给出「验收通过」判定

接口约定 (待实现):
    critique(candidate, verification_result) -> Feedback
"""

# Phase 2 代码写在这里
