# 系统架构梳理 · 系统论批判 · V4 升级方案 · Lonely Runner 重定向

日期：2026-08-16 | 起草：首席架构师 | 呈总指挥/PM

---

## 第一部分：当前系统自上而下全景（节点协作地图）

```
┌─ L0 使命层 ──────────────────────────────────────────────┐
│ 总指挥/PM（目标选择、战略法令、独创铁律）→ 架构师会话      │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─ L1 决策闸口层 ──────────────────────────────────────────┐
│ ScoutAgent（查新防撞车）: 检索式生成→arXiv/OpenAlex→独创性 │
│   裁决; DUPLICATE_KNOWN 熔断（铁律, 不可绕过）             │
│ [人工纪律] 30秒命题真伪体检（反例搜索）← 非系统组件!       │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─ L2 猎物发现层 ──────────────────────────────────────────┐
│ ProblemHunter: arXiv 雷达(7分类+6关键词,分层轮转) → Filter │
│   Agent 初筛(SOS/迹恒等式可降维才放行) → SymPy 算力体检    │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─ L3 攻坚引擎层 ─────────────────────────────────────────┐
│ main_loop.py (串行): Prover→Lean→Critic→错题本 状态机      │
│ parallel_loop.py (V3 并行): Explorer-A[代数]/B[几何]/C[组合]│
│   asyncio.gather 并发 → 独立 Worker 沙箱 → FIRST_COMPLETED │
│   斩获清场 → 全溃败则黑石碑唤醒                           │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─ L4 裁判层 ─────────────────────────────────────────────┐
│ LeanValidator: lean --server 常驻 LSP (0.2~2s 验证) /     │
│   CLI 隔离文件降级 / Worker_ID 沙箱隔离 / prelude 阶梯     │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─ L5 记忆反馈层 ─────────────────────────────────────────┐
│ 错题本(支线禁手) → Fingerprint 墙(系统级禁忌) → 黑石碑     │
│ 会诊(3路全灭才唤醒, 只产拓扑阻碍图谱, 禁修局部)           │
│ auto-memory(跨会话: 铁律/事故/资产档案)                   │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─ L6 研究工具层 ─────────────────────────────────────────┐
│ research/lenz_scan.py (SymPy CM 证书) · 猎杀脚本 · 冒烟测试│
└─────────────────────────────────────────────────────────┘
基础设施: venv · .env(DeepSeek 双模型) · MathWorkspace(mathlib
  8704 olean) · 网络层(arXiv 证书降级/OpenAlex 备用/flash 重试)
```

**信息流主环**：目标 → 闸口(查新+真伪) → 引擎(推导) → 裁判(Lean) → 反馈(错题本/Fingerprint) → 下一轮 → 斩获落盘 outputs/。

## 第二部分：系统论与控制反馈批判

以控制论视角（参考输入 → 执行器 → 被控对象 → 传感器 → 反馈）审视，当前系统存在七个结构性问题：

1. **【最致命】开环的真伪环节**：命题真伪检查是架构师的人工纪律（30 秒反例搜索），不是系统组件。三次证伪事故全部靠人工拦截——若换一个不执行该纪律的执行者，系统会直接烧假命题。**必须内化为 Probe 0（自动反例猎人）**。

2. **反馈环粒度单一**：唯一的硬反馈是 Lean 编译结果（布尔值+报错）。数值/连续信号（能量值、谱间隙、间隙函数）完全无法进入证明流。对开放问题，证明搜索没有"目标函数"——LLM 的 next-token 分布是隐式梯度，不可观测、不可控制。

3. **搜索结构是局部搜索**：LLM 证明器=局部探索（沿语言分布采样），无全局最优性判据、无分支定界、无下界证书。对"证明 k=14"这类超长链目标，单步采样率再高也够不到。

4. **黑石碑诊断是文本级**：Fingerprint 是自然语言规则，不是 V3 原规格设想的"合并状态矩阵"——多轮阻碍之间没有结构化的相关性分析（哪些禁忌组合导致空间被堵死）。

5. **算力配置未用满**：多核主机只跑了 3 路 LLM + 1 路 Lean；SymPy 计算、数值搜索与证明流完全串行。统计物理退火/谱计算/线性规划这些"秒出极值"的算力资产闲置。

6. **数值→符号→Lean 的桥缺失**：探针 2（物理退火）发现的高对称极值构型无法自动 PSLQ 精确化、无法自动 SOS 固化、无法自动成为 Lean 证书——每一环都要人工搬运。这是 V4 的核心增量所在。

7. **目标函数缺失（开放问题专用病）**：闭环系统需要一个可计算的"进展度量"（如：当前已证界与猜想界的 gap、被排除的反例空间体积、Fingerprint 覆盖度）。没有它，多轮探索退化为随机游走。

## 第三部分：V4.0 升级方案（五探针 → 具体组件）

| 探针 | 组件 | 依赖 | 价值 |
|---|---|---|---|
| **0. 反例猎人（新增,最高优先级）** | `research/probe0_counterexample.py` | 纯 Python/SymPy | 把 30 秒真伪纪律自动化：结构化+随机反例搜索、区间算术、SMT 式分支；点火前强制运行 |
| **1. SOS 代数引擎** | `research/probe1_sos_engine.py` | pip: cvxpy+clarabel（真 SDP 求解器） | Positivstellensatz/SOS 证书研磨：多项式 f≥0 的 Putinar 表示 → 系数匹配 → SDP → 显式平方和 → Lean 的 `nlinarith`/`ring` 证书 |
| **2. 统计物理势能流** | `research/probe2_potential_flow.py` | mpmath.pslq（sympy 内置） | 退火/梯度流找基态构型 → PSLQ 浮点→代数数精确重构 → 写入黑板 |
| **3. 谱图算子流** | `research/probe3_spectral.py` | 纯 Python 特征值 | Rayleigh 商/谱间隙/Expander Mixing → 迹不等式交付 Lean |
| **4. 信息论熵流** | `research/probe4_entropy.py` | 纯 Python | Shearer/次模性证书：覆盖计数与禁止子图的指数上界 |
| **5. 多面体 Farkas 流** | `research/probe5_farkas.py` | pip: scipy(linprog/HiGHS) | 不等式系统不可行性证书（Farkas 乘子）→ 直接生成 `linarith` 击杀脚本 |
| **黑板与调度** | `shared_blackboard.json` + V5 协调器 | — | 探针 2/3 写数值发现 → 探针 1/5 读并符号化 → FIRST_COMPLETED 熔断 → 黑石碑升级为结构化状态矩阵 |

**实施顺序建议**：Probe 0（当天）→ Probe 1+5（证书双雄, 当周）→ 黑板+协调器 → Probe 2/3/4（按目标需求）。

## 第四部分：Lonely Runner 重定向（重要事实修正）

**任务前提修正**（联网调研, 来源见文末）：
- **k=7 已于 2007-08 解决**（Barajas & Serra, 距离图正则色数方法）——"k=7 卡死 30 年"的命题前提不成立。
- 真实卡点曾是 k≥8（约 20 年）；**2025-26 连环突破**：Rosenfeld 证 8 跑者（计算机辅助, arXiv:2509.14111）→ Trakulthongchai 证 9、10 跑者 → Sungkawichai–Trakulthongchai 证 11~13 跑者（arXiv:2604.23906, 筛法+多项式方法+Tao 阈值理论）。
- **当前真前线 = k=14 跑者**（及一般 k）。附带方向：shifted LRC（Alcántara, zonotope 覆盖半径 + LLL）。

**Motzkin-Straus 思路的真实落点**（用户直觉的严谨映射）：
- 用户提出的 Motzkin-Straus/Ising 映射针对"团搜索"——在 LRC 文献里，团结构恰恰出现在 **Barajas-Serra 的 k=7 证明**（距离图的正则色数 ⟺ 距离图团覆盖）。该谱系停滞 17 年未再推进，是 Motzkin-Straus 连续松弛真正可能发力的位置。
- 但对 k=14 的主线攻击，主流路线是 Rosenfeld 式计算筛法（Tao 阈值理论 + 极小反例素因子筛 + 上界矛盾）。诚实评估：直接"秒杀"k=14 不现实；可行的差异化贡献是：

**候选攻击方案（按可行性排序）**：
1. **复现与优化计算管线**（推荐第一步）：Python 重实现 Rosenfeld k=8 管线精简版 → 以 k=9~13 为基准校验 → 注入我们的并行/筛选启发式 → 冲 k=14。产出=计算证明数据 + 管线资产。
2. **Lean 形式化 2026 突破的关键引理**（注意铁律：须以"为 k=14 冲刺自建机器检查片段"为包装，非翻译）：多项式方法引理（k+1 与 p 为奇素数、速度 ≡ (1..k) mod p 情形）与筛法引理——我们推 k=14 时自行使用并形式化，即为原创贡献。
3. **距离图色数 + Motzkin-Straus 谱系复兴**：以 Barajas-Serra 框架为基础，用连续松弛探针搜索 k≥8 的距离图结构——高风险高回报的差异化路线。
4. **Zonotope 覆盖半径方向**（shifted LRC）：LLL+覆盖半径计算，Alcántara 路线的延伸。

---

## 参考来源

- Quanta Magazine: New Strides Made on Deceptively Simple 'Lonely Runner' Problem (2026-03-06)
- Rosenfeld, The lonely runner conjecture holds for nine runners (arXiv:2512.01912); k=8 计算机辅助证明 (arXiv:2509.14111)
- Sungkawichai & Trakulthongchai, Eleven, twelve, and thirteen lonely runners (arXiv:2604.23906)
- Alcántara, Covering Radii of 3-Zonotopes and the Shifted Lonely Runner Conjecture (Experimental Mathematics, 2026)
- Barajas & Serra, The Lonely Runner with Seven Runners (2008)
