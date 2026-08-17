"""
scout_agent.py — 学术查新哨兵 (LiteratureScoutAgent) · 防撞车闸口

战略定位【杜绝重复造轮子】:
  在唤醒 Prover (deepseek-v4-pro) 烧算力之前, 先回答一个问题:
  「这个命题是不是已经被前人做完了?」
  - DUPLICATE_KNOWN        → 红色熔断: 输出前人论文清单, 零算力燃烧;
  - PARTIALLY_KNOWN_OPEN  → 绿色放行, 但携带前人文献边界进入状态机;
  - COMPLETELY_OPEN       → 绿色放行, 放心开荒。

三段式流水线:
  1. generate_search_queries — deepseek-v4-flash 提炼 3~5 组专业学术检索式
     (核心术语 / 猜想提出者 / 中英文名称 / 关键渐近上下界 / arXiv 检索式 / MO 关键词);
  2. search_academic_sources — arXiv 官方 Atom API 为主检索源 (https→http 双协议),
     本机(中国大陆)直连被墙时自动降级到 OpenAlex API (type:preprint, 索引含 arXiv
     预印本), 数学分类白名单过滤 (math.NT / math.CO / math.CA ...);
  3. evaluate_novelty — flash 将命题与命中文献摘要交叉分析, 强制输出结构化裁决 JSON。

设计原则:
  - 查新闸口必须「失败关闭 (fail-closed)」: 检索全灭或裁决解析失败时抛异常,
    由 main_loop 决策 (红色告警 + 提示 --skip-scout 人工放行), 绝不静默漏检;
  - 仅新增标准库依赖 (urllib + xml.etree), 与 agents.py 共享 AsyncOpenAI 客户端;
  - 对检索源保持礼貌: User-Agent 标识 + 查询间 3 秒间隔。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Sequence

from dotenv import load_dotenv

# 复用 agents.py 的共享异步客户端 (同一 .env 与连接配置, 避免双份密钥逻辑)
from agent_core.agents import _get_client

# ---------------------------------------------------------------------------
# 环境配置 (从项目根目录 .env 读取, 带默认值兜底)
# ---------------------------------------------------------------------------

_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

# 哨兵用轻量快模型: 查新不需要深度推理, flash 秒级出结果且便宜
SCOUT_MODEL: Final[str] = os.getenv("DEEPSEEK_CHAT_MODEL", "deepseek-v4-flash")
# 预算含思考 token (推理模型思考与正文共享 max_tokens), 需留足余量
SCOUT_QUERY_MAX_TOKENS: Final[int] = 2048   # 检索式 JSON 很小, 但思考可能吃掉预算
SCOUT_EVAL_MAX_TOKENS: Final[int] = 3072    # 裁决 JSON + 对比分析

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 数学分类白名单 (arXiv 一级分类; 检索结果仅保留命中者)
DEFAULT_CATEGORIES: Final[tuple[str, ...]] = ("math.NT", "math.CO", "math.CA")

# arXiv 官方开放 API (规范指定 http; 优先尝试 https, 失败降级 http)
_ARXIV_ENDPOINTS: Final[tuple[str, ...]] = (
    "https://export.arxiv.org/api/query",
    "http://export.arxiv.org/api/query",
)
# OpenAlex 降级源: 索引含 arXiv 预印本 (type:preprint), 本机实测可达
_OPENALEX_ENDPOINT: Final[str] = "https://api.openalex.org/works"
_OPENALEX_MAILTO: Final[str] = "scout@ai-math-institute.local"

_HTTP_TIMEOUT: Final[float] = 20.0      # 单请求超时 (秒)
_POLITE_DELAY: Final[float] = 3.0       # 查询间礼貌间隔 (arXiv 官方建议 ≥3s)
_MAX_PAPERS_FOR_JUDGE: Final[int] = 20  # 喂给裁决模型的文献上限 (按最新排序)
_SUMMARY_CAP: Final[int] = 500          # 单篇摘要截断长度

_USER_AGENT: Final[str] = "AI-Math-Institute-Scout/0.1 (academic novelty check)"

_ATOM_NS: Final[dict[str, str]] = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# 裁决枚举 (与规范 JSON schema 严格一致)
_Verdict = Literal["DUPLICATE_KNOWN", "PARTIALLY_KNOWN_OPEN", "COMPLETELY_OPEN"]
_VERDICTS: Final[tuple[str, ...]] = ("DUPLICATE_KNOWN", "PARTIALLY_KNOWN_OPEN", "COMPLETELY_OPEN")

# OpenAlex 端数学主题白名单 (arXiv 端走分类白名单, 此端用主题名近似过滤)
_MATH_TOPIC_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"number\s*theory|combinatoric|graph\s*theory|mathematical\s*analysis|"
    r"harmonic\s*analysis|diophantine|primes?|prime\s*numbers|additive|"
    r"analytic\s*number|algebraic\s*number|arithmetic|discrete\s*math|"
    r"order\s*theory|set\s*theory|sequences?|integer|modular|geometry|"
    r"algebra|topology|logic|probability|dynamical|ergodic|fourier|calculus|"
    r"optimization",
    re.IGNORECASE,
)

# arXiv 检索式 → OpenAlex 检索式转换用的停用词 (仅裸词路径)
_STOPWORDS: Final[frozenset[str]] = frozenset({
    "the", "a", "an", "of", "on", "in", "for", "and", "or", "is", "are",
    "be", "to", "with", "by", "about", "every", "any", "all", "some",
    "not", "that", "this", "these", "those", "from", "using", "new",
})

_JSON_BLOCK_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{.*\}", re.DOTALL)
_JSON_ARRAY_PATTERN: Final[re.Pattern[str]] = re.compile(r"\[.*\]", re.DOTALL)


class ScoutSearchError(RuntimeError):
    """学术检索源故障 (网络不可达 / 全部查询失败)。"""


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchQueryGroup:
    """一组专业学术检索式 (由 flash 提炼, 覆盖一个检索维度)。"""

    facet: str                     # 检索维度名 (如 核心术语 / 猜想提出者 / 渐近界)
    arxiv_query: str               # 可直接进 arXiv search_query 的检索式 (支持字段前缀与布尔)
    mo_keywords: tuple[str, ...]   # MathOverflow 检索关键词 (供人工跟进, 本阶段不自动检索)


@dataclass(frozen=True)
class ScoutPaper:
    """一篇命中的学术文献 (跨检索源归一化表示)。"""

    entry_id: str
    title: str
    summary: str
    authors: tuple[str, ...]
    published: str                # ISO 日期字符串
    primary_category: str         # 主分类 (arXiv 分类号或 OpenAlex 主题名)
    url: str


@dataclass(frozen=True)
class NoveltyVerdict:
    """独创性裁决 (JSON schema 与规范逐字对齐)。"""

    verdict: _Verdict
    novelty_score: int            # 1(教科书级已知) ~ 10(完全无人触及)
    known_prior_work: tuple[str, ...]
    analysis: str
    recommended_generalization: str


@dataclass(frozen=True)
class ScoutReport:
    """一次完整查新的结构化报告。"""

    statement_nl: str
    lean_statement: str
    queries: tuple[SearchQueryGroup, ...]
    papers: tuple[ScoutPaper, ...]
    verdict: NoveltyVerdict
    warnings: tuple[str, ...]
    query_seconds: float
    search_seconds: float
    evaluate_seconds: float

    @property
    def blocked(self) -> bool:
        """是否触发查新熔断 (完全重复, 不得烧算力)。"""
        return self.verdict.verdict == "DUPLICATE_KNOWN"

    def literature_boundary(self) -> str:
        """压缩为一段文本, 注入 Prover 提示词作为「前人文献边界」。"""
        prior = "；".join(self.verdict.known_prior_work) or "（无明确前人文献命中）"
        return (
            f"裁决={self.verdict.verdict} (独创性 {self.verdict.novelty_score}/10)\n"
            f"前人边界: {prior}\n"
            f"分析摘要: {self.verdict.analysis[:300] or '（无）'}\n"
            f"推广建议: {self.verdict.recommended_generalization[:300] or '（无）'}"
        )

    def to_markdown(self) -> str:
        """结构化 Markdown 报告 (供控制台输出 / 归档)。"""
        lines = [
            "════════════════════════════════════════════════",
            "📚 学术查新报告 (ScoutAgent)",
            "════════════════════════════════════════════════",
            f"目标 (自然语言): {self.statement_nl or '（未提供, 由哨兵从 Lean 命题推断）'}",
            f"目标 (Lean 命题): {self.lean_statement}",
            "",
            f"检索式 (共 {len(self.queries)} 组):",
        ]
        for i, q in enumerate(self.queries, 1):
            lines.append(f"  {i}. [{q.facet}] arxiv: {q.arxiv_query}")
            if q.mo_keywords:
                lines.append(f"     MO 关键词: {', '.join(q.mo_keywords)}")
        lines += [
            "",
            f"命中文献 (去重后 {len(self.papers)} 篇):",
        ]
        if not self.papers:
            lines.append("  （无命中 — 该方向确为荒地）")
        for i, p in enumerate(self.papers, 1):
            authors = ", ".join(p.authors[:4]) + (" 等" if len(p.authors) > 4 else "")
            lines.append(f"  {i}. {p.title} | {authors} | {p.published} | {p.primary_category}")
            if p.summary:
                lines.append(f"     摘要: {p.summary[:160]}...")
        if self.warnings:
            lines += ["", "⚠️ 检索源告警:"]
            lines += [f"  - {w}" for w in self.warnings]
        lines += [
            "",
            "── 独创性裁决 ──",
            f"verdict: {self.verdict.verdict} | novelty_score: {self.verdict.novelty_score}/10",
            "known_prior_work:",
            *([f"  - {w}" for w in self.verdict.known_prior_work] or ["  - （无）"]),
            f"analysis: {self.verdict.analysis or '（无）'}",
            f"recommended_generalization: {self.verdict.recommended_generalization or '（无）'}",
            "",
            f"耗时: 检索式 {self.query_seconds:.1f}s | 学术检索 {self.search_seconds:.1f}s | "
            f"裁决分析 {self.evaluate_seconds:.1f}s",
        ]
        return "\n".join(lines)

    def to_json(self) -> str:
        """JSON 报告: verdict 字段块与规范 schema 逐字一致, 外层附检索元数据。"""
        payload = {
            "target": {
                "statement_nl": self.statement_nl,
                "lean_statement": self.lean_statement,
            },
            "search": {
                "queries": [q.__dict__ | {"mo_keywords": list(q.mo_keywords)}
                            for q in self.queries],
                "papers": [p.__dict__ | {"authors": list(p.authors)} for p in self.papers],
                "warnings": list(self.warnings),
            },
            "verdict": {
                "verdict": self.verdict.verdict,
                "novelty_score": self.verdict.novelty_score,
                "known_prior_work": list(self.verdict.known_prior_work),
                "analysis": self.verdict.analysis,
                "recommended_generalization": self.verdict.recommended_generalization,
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 组件 A: 学术检索式生成器 (deepseek-v4-flash)
# ---------------------------------------------------------------------------

_QUERY_SYSTEM_PROMPT: Final[str] = (
    "你是顶尖的数论/组合数学学术文献情报专家, 精通 arXiv、MathOverflow 与 MathSciNet 的"
    "检索语法与术语体系。你的任务: 为一个待证明的数学命题提炼 3~5 组【极其专业】的"
    "学术检索式, 确保能全面命中任何相关的前人工作 (包括中文数学界术语)。\n"
    "\n"
    "检索式必须覆盖以下维度 (每组一个维度, 可多组同维度但措辞互补):\n"
    "1. 核心数学术语 (英文 + 中文译名, 如 'coprime 互素' 'Diophantine 丢番图');\n"
    "2. 猜想提出者 / 相关经典文献作者姓名 (必须给出最权威的原始作者, 用 au: 字段);\n"
    "3. 关键渐近上下界与数量级 (如 'bound c-a >= 3' 形式);\n"
    "4. arXiv 专用检索式: 必须使用 arXiv 字段前缀 (all:/ti:/au:/abs:/cat:) 与布尔算子\n"
    "   (AND/OR/ANDNOT), 短语用双引号, 建议组合 cat:math.NT 或 cat:math.CO 限定领域;\n"
    "5. MathOverflow 专用关键词: 贴合 MO 提问风格的口语化检索词。\n"
    "\n"
    "输出格式【严格要求】为 JSON 数组, 不要输出 JSON 以外的任何内容:\n"
    '[{"facet": "检索维度名", "arxiv_query": "arXiv 检索式", '
    '"mo_keywords": ["MO 关键词1", "MO 关键词2"]}]'
)

# 检索式生成失败时的兜底: 从命题文本粗提关键词构造单组检索式 (弱检索优于零检索)
_LEAN_NOISE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:theorem|lemma|example|axiom|opaque|def)\b|[(){}:⟨⟩,;:=<>|→∀∃λ∑∏ℕℤℚℝ]|\b\d+\b",
    re.IGNORECASE,
)


class LiteratureScoutAgent:
    """学术查新哨兵 — 推导状态机的前置「防撞车闸口」。

    流水线: 检索式生成 → 学术检索 (arXiv 官方 API, 不可达时降级 OpenAlex)
             → 独创性裁决 (结构化 JSON)。
    失败关闭: 检索全灭 / 裁决解析失败 → 抛异常, 由 main_loop 红色告警终止,
              绝不静默放行 (查新闸口的诚信)。
    """

    def __init__(
        self,
        model: str = SCOUT_MODEL,
        query_max_tokens: int = SCOUT_QUERY_MAX_TOKENS,
        eval_max_tokens: int = SCOUT_EVAL_MAX_TOKENS,
        categories: Sequence[str] = DEFAULT_CATEGORIES,
        max_results_per_query: int = 8,
    ) -> None:
        """初始化哨兵。

        Args:
            model: 查新模型 (默认 deepseek-v4-flash, 快且便宜; 查新无需深度推理)。
            query_max_tokens: 检索式生成的输出 token 上限。
            eval_max_tokens: 裁决分析的输出 token 上限。
            categories: arXiv 数学分类白名单。
            max_results_per_query: 每组检索式的最大命中数。
        """
        self.model: str = model
        self.query_max_tokens: int = query_max_tokens
        self.eval_max_tokens: int = eval_max_tokens
        self.categories: tuple[str, ...] = tuple(categories)
        self.max_results_per_query: int = max_results_per_query
        self.client = _get_client()

    # ---------------- LLM 调用基座 (2 次重试) ----------------

    async def _complete(self, system: str, user: str, max_tokens: int, what: str) -> str:
        """LLM 调用基座: 空内容/异常指数退避重试 (3 次), 重试时加倍 token 预算。

        本机实测: deepseek-v4-flash 偶发返回空 content (API 端抖动, 同参数下次即正常),
        且不支持 thinking_budget 参数; 加倍 max_tokens + 递增退避可骑过抖动窗口。
        """
        last_exc: Exception | None = None
        budget = max_tokens
        for attempt, delay in ((1, 2.0), (2, 5.0), (3, 10.0)):
            try:
                resp = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    max_tokens=budget,
                )
                content = (resp.choices[0].message.content or "").strip()
                if content:
                    return content
                last_exc = RuntimeError("模型返回空内容 (API 端抖动)")
                budget = max_tokens * 2
            except Exception as exc:  # noqa: BLE001 — 网络/API 异常统一退避重试
                last_exc = exc
            await asyncio.sleep(delay)
        raise RuntimeError(
            f"ScoutAgent {what} 连续三次失败 (model={self.model}): {last_exc}"
        ) from last_exc

    # ---------------- 组件 A: 学术检索式生成器 ----------------

    @staticmethod
    def _fallback_queries(statement_nl: str, lean_statement: str) -> list[SearchQueryGroup]:
        """LLM 检索式解析失败时的兜底: 从命题文本粗提关键词 (弱检索优于零检索)。"""
        text = statement_nl or lean_statement
        cleaned = _LEAN_NOISE_PATTERN.sub(" ", text)
        words = [w for w in cleaned.split() if len(w) >= 3][:6]
        phrase = " ".join(words).strip()
        if not phrase:
            phrase = lean_statement.strip()[:60]
        return [SearchQueryGroup(
            facet="兜底粗提 (LLM 检索式解析失败)",
            arxiv_query=f'all:"{phrase}"',
            mo_keywords=(phrase,),
        )]

    async def generate_search_queries(
        self, statement_nl: str | None, lean_statement: str
    ) -> tuple[SearchQueryGroup, ...]:
        """让 flash 提炼 3~5 组极其专业的学术检索式。

        Args:
            statement_nl: 命题的自然语言描述 (可为空, 哨兵会从 Lean 命题推断语义)。
            lean_statement: 待证明的 Lean 4 命题声明。

        Returns:
            SearchQueryGroup 元组 (3~5 组)。LLM 输出不合规时兜底为 1 组粗提检索式
            (弱检索优于零检索, 报告中将显示兜底维度名)。
        """
        user_prompt = (
            "【待证明命题 (自然语言)】\n"
            f"{statement_nl or '（未提供 — 请根据 Lean 命题自行推断其数学含义）'}\n"
            "\n"
            "【待证明命题 (Lean 4 声明)】\n"
            f"{lean_statement}\n"
            "\n"
            "请提炼 3~5 组专业学术检索式, 严格输出 JSON 数组。"
        )
        content = await self._complete(
            _QUERY_SYSTEM_PROMPT, user_prompt, self.query_max_tokens, "检索式生成"
        )
        match = _JSON_ARRAY_PATTERN.search(content)
        if match:
            try:
                groups: list[SearchQueryGroup] = []
                for item in json.loads(match.group(0)):
                    mo = item.get("mo_keywords") or []
                    if isinstance(mo, str):
                        mo = [mo]
                    arxiv_q = str(item.get("arxiv_query") or "").strip()
                    if not arxiv_q:
                        continue
                    groups.append(SearchQueryGroup(
                        facet=str(item.get("facet") or "未命名维度").strip(),
                        arxiv_query=arxiv_q[:200],
                        mo_keywords=tuple(str(k).strip() for k in mo if str(k).strip()),
                    ))
                if groups:
                    return tuple(groups[:5])
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass  # 落入兜底
        return tuple(self._fallback_queries(statement_nl, lean_statement))

    # ---------------- 组件 B: 学术 API 检索接口 ----------------

    @staticmethod
    def _arxiv_to_openalex(query: str) -> list[str]:
        """把 arXiv 检索式转换为 OpenAlex 短语列表 (剥离字段前缀, 提取引号短语)。"""
        cleaned = re.sub(r"\b(?:all|ti|au|abs|cat)\s*:", " ", query)
        phrases = [p.strip() for p in re.findall(r'"([^"]+)"', cleaned) if len(p.strip()) >= 2]
        if phrases:
            return phrases[:3]
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z'\-]{2,}", cleaned)
                 if w.lower() not in _STOPWORDS]
        if words:
            return words[:4]
        return [cleaned.strip()[:50]]

    @staticmethod
    def _http_get(url: str) -> bytes:
        """GET 请求 (超时/SSL 抖动重试一次 + 证书校验降级)。

        本机网络两个已知坑 (见 china-network-workarounds):
          1. 根证书库缺 ISRG Root X1 (Let's Encrypt) → CERTIFICATE_VERIFY_FAILED,
             仅此情形用非校验上下文重试 (只读公开检索接口, 风险可接受);
          2. 跨境链路偶发 TLS 抖动 (SSL EOF / 超时) → 普通重试一次。
        """
        last_exc: Exception | None = None
        for attempt in (1, 2):
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(url, headers={"User-Agent": _USER_AGENT}),
                    timeout=_HTTP_TIMEOUT,
                ) as resp:
                    return resp.read()
            except urllib.error.URLError as exc:
                last_exc = exc
                if isinstance(exc.reason, ssl.SSLCertVerificationError):
                    # 证书校验失败: 非校验上下文直连重试 (arXiv 官方 API 本机实测可行)
                    ctx = ssl._create_unverified_context()  # noqa: SLF001
                    try:
                        with urllib.request.urlopen(
                            urllib.request.Request(url, headers={"User-Agent": _USER_AGENT}),
                            timeout=_HTTP_TIMEOUT, context=ctx,
                        ) as resp:
                            return resp.read()
                    except Exception as exc2:  # noqa: BLE001
                        last_exc = exc2
                        break  # 非校验重试也失败 → 不再空转
            except Exception as exc:  # noqa: BLE001 — 超时/SSL EOF 等抖动
                last_exc = exc
            if attempt == 1:
                time.sleep(1.5)
        raise ScoutSearchError(f"HTTP 请求失败: {type(last_exc).__name__} {last_exc}") from last_exc

    def _fetch_arxiv(self, query: str) -> list[ScoutPaper]:
        """检索 arXiv 官方 Atom API (https→http 降级); 网络失败抛 ScoutSearchError。"""
        params = urllib.parse.urlencode({
            "search_query": query,
            "start": 0,
            "max_results": self.max_results_per_query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        })
        last_exc: Exception | None = None
        for endpoint in _ARXIV_ENDPOINTS:
            try:
                data = self._http_get(f"{endpoint}?{params}")
                break
            except Exception as exc:  # noqa: BLE001 — 网络层异常统一降级
                last_exc = exc
        else:
            raise ScoutSearchError(f"arXiv API 不可达: {type(last_exc).__name__} {last_exc}")

        allowed = {c.lower() for c in self.categories}
        papers: list[ScoutPaper] = []
        root = ET.fromstring(data)
        for entry in root.findall("atom:entry", _ATOM_NS):
            # category 是自闭合元素: 分类号在 term 属性上, .text 恒为 None
            cats = [(t.get("term") or "").strip().lower()
                    for t in entry.findall("atom:category", _ATOM_NS)]
            if allowed.isdisjoint(cats):
                continue
            pc = entry.find("arxiv:primary_category", _ATOM_NS)
            primary = (pc.get("term") or "") if pc is not None else ""
            entry_id_el = entry.find("atom:id", _ATOM_NS)
            entry_id = (entry_id_el.text or "") if entry_id_el is not None else ""
            title_el = entry.find("atom:title", _ATOM_NS)
            title = re.sub(r"\s+", " ", "".join(title_el.itertext())).strip() \
                if title_el is not None else "（无标题）"
            summary_el = entry.find("atom:summary", _ATOM_NS)
            summary = re.sub(r"\s+", " ", "".join(summary_el.itertext())).strip() \
                if summary_el is not None else ""
            authors = tuple(
                re.sub(r"\s+", " ", "".join(a.itertext())).strip()
                for a in entry.findall("atom:author", _ATOM_NS)
            )
            published_el = entry.find("atom:published", _ATOM_NS)
            published = ((published_el.text or "") if published_el is not None else "").strip()[:10]
            link = next((e.get("href") or "" for e in entry.findall("atom:link", _ATOM_NS)
                         if e.get("type") == "text/html"), "")
            papers.append(ScoutPaper(
                entry_id=entry_id,
                title=title or "（无标题）",
                summary=summary[: _SUMMARY_CAP],
                authors=authors[:8],
                published=published,
                primary_category=primary,
                url=link,
            ))
        return papers

    def _openalex_search(self, terms: Sequence[str]) -> list[dict]:
        """OpenAlex 单次检索: 多短语 OR 匹配标题+摘要 (type:preprint)。"""
        search = " ".join(f'"{t}"' for t in terms)
        filters = f"title_and_abstract.search:{search},type:preprint"
        params = urllib.parse.urlencode({
            "filter": filters,
            "sort": "publication_date:desc",
            "per-page": self.max_results_per_query,
            "mailto": _OPENALEX_MAILTO,
        })
        url = f"{_OPENALEX_ENDPOINT}?{params}"
        try:
            data = json.loads(self._http_get(url))
        except Exception as exc:  # noqa: BLE001
            raise ScoutSearchError(f"OpenAlex API 不可达: {type(exc).__name__} {exc}") from exc
        return data.get("results", [])

    def _map_openalex(self, results: Sequence[dict]) -> list[ScoutPaper]:
        """OpenAlex 原始结果 → ScoutPaper (含数学主题白名单近似过滤)。"""
        papers: list[ScoutPaper] = []
        for w in results:
            topic_names = []
            pt = w.get("primary_topic") or {}
            if pt.get("display_name"):
                topic_names.append(pt["display_name"])
            for c in (w.get("topics") or [])[:2]:
                if c.get("display_name"):
                    topic_names.append(c["display_name"])
            # 数学主题白名单近似过滤 (无主题信息则宽进, 交给裁决模型判断)
            if topic_names and not any(_MATH_TOPIC_PATTERN.search(t) for t in topic_names):
                continue
            inv = w.get("abstract_inverted_index")
            summary = ""
            if inv:
                pos: dict[int, str] = {}
                for word, idxs in inv.items():
                    for i in idxs:
                        pos[i] = word
                summary = " ".join(pos[i] for i in sorted(pos))[: _SUMMARY_CAP]
            authors = tuple(
                str(a["author"].get("display_name") or "?")
                for a in (w.get("authorships") or [])[:8]
            )
            doi = str(w.get("doi") or "")
            url_ = doi if doi.startswith("http") else (f"https://doi.org/{doi}" if doi else "")
            papers.append(ScoutPaper(
                entry_id=w.get("id") or f"oa:{w.get('display_name')}",
                title=str(w.get("display_name") or "（无标题）"),
                summary=summary,
                authors=authors,
                published=str(w.get("publication_date") or "")[:10],
                primary_category=topic_names[0] if topic_names else "",
                url=url_ or (w.get("id") or ""),
            ))
        return papers

    def _fetch_openalex(self, query: str) -> list[ScoutPaper]:
        """OpenAlex 降级检索 (type:preprint, 索引含 arXiv 预印本)。

        短语组合过窄 (标题/摘要精确匹配命中稀少) 时, 拆为单词 OR 检索
        补充召回 (两路结果按 entry_id 去重合并)。
        """
        phrases = self._arxiv_to_openalex(query)
        papers = self._map_openalex(self._openalex_search(phrases))
        if len(papers) < 2 and phrases:
            words = [w for w in re.findall(r"[A-Za-z][A-Za-z'\-]{2,}", " ".join(phrases))
                     if w.lower() not in _STOPWORDS][:5]
            if words and words != phrases:
                merged = {p.entry_id: p for p in papers}
                for p in self._map_openalex(self._openalex_search(words)):
                    merged.setdefault(p.entry_id, p)
                papers = list(merged.values())
        return papers

    def search_academic_sources(
        self, queries: Sequence[SearchQueryGroup]
    ) -> tuple[list[ScoutPaper], list[str]]:
        """学术检索主入口: arXiv 官方 API 为主, 不可达时自动降级 OpenAlex。

        同步实现 (urllib 阻塞), 由 scout() 放入 to_thread 执行。
        返回 (去重排序后的文献列表, 检索源告警列表); 所有查询全部失败时抛
        ScoutSearchError (失败关闭, 绝不静默放行)。
        """
        papers: dict[str, ScoutPaper] = {}
        warnings: list[str] = []
        arxiv_down = False
        failed_queries = 0

        for q in queries:
            got = False
            if not arxiv_down:
                try:
                    for p in self._fetch_arxiv(q.arxiv_query):
                        papers.setdefault(p.entry_id, p)
                    got = True
                except ScoutSearchError as exc:
                    warnings.append(
                        f"arXiv 官方 API 不可达 ({exc}); 已自动降级 OpenAlex 预印本索引"
                    )
                    arxiv_down = True
            if not got:
                try:
                    for p in self._fetch_openalex(q.arxiv_query):
                        papers.setdefault(p.entry_id, p)
                    got = True
                except ScoutSearchError as exc:
                    warnings.append(f"检索式 [{q.arxiv_query[:60]}...] 失败: {exc}")
            if not got:
                failed_queries += 1
            time.sleep(_POLITE_DELAY)

        if failed_queries == len(queries):
            raise ScoutSearchError(
                "所有学术检索源 (arXiv + OpenAlex) 均不可达, 查新闸口失败关闭"
            )
        ordered = sorted(papers.values(), key=lambda p: p.published, reverse=True)
        return ordered, warnings

    # ---------------- 组件 C: 独创性裁决与报告生成 ----------------

    async def evaluate_novelty(
        self,
        statement_nl: str | None,
        lean_statement: str,
        papers: Sequence[ScoutPaper],
    ) -> NoveltyVerdict:
        """将命题与检索到的文献交叉分析, 强制输出结构化独创性裁决。

        裁决解析失败时抛 RuntimeError (失败关闭): 查新闸口绝不以猜测放行。
        """
        system_prompt = (
            "你是极其严谨的数学文献分析法官, 专职【独创性裁决】。你将待证明命题与"
            "检索命中的文献逐篇交叉比对, 判断该命题是否已被前人完全解决。\n"
            "\n"
            "裁决标准:\n"
            "1. DUPLICATE_KNOWN: 命题本身或等价形式已被完整证明 (包括教科书级经典结果);\n"
            "2. PARTIALLY_KNOWN_OPEN: 前人做了相关/部分工作 (如弱化版、特殊情形、"
            "相关不等式), 但命题的精确表述或推广维度仍有未覆盖的空白;\n"
            "3. COMPLETELY_OPEN: 没有任何命中文献触及该命题的核心。\n"
            "\n"
            "novelty_score: 1=教科书级已知, 10=完全无人触及的开荒命题。\n"
            "known_prior_work: 逐条列出真正相关的前人论文 (作者 + 标题 + 年份), "
            "不相关的噪声文献一律不列。\n"
            "recommended_generalization: 若 verdict 为 DUPLICATE_KNOWN 或 "
            "PARTIALLY_KNOWN_OPEN, 必须给出向哪个方向进一步推广/加强/换域才能构成"
            "新成果的具体学术建议; 若 COMPLETELY_OPEN 则填 '无 (命题本身即新成果)'。\n"
            "\n"
            "输出格式【严格要求】为 JSON 对象, 不要输出 JSON 以外的任何内容:\n"
            '{"verdict": "DUPLICATE_KNOWN" 或 "PARTIALLY_KNOWN_OPEN" 或 "COMPLETELY_OPEN", '
            '"novelty_score": 1到10的整数, "known_prior_work": ["前人论文条目1", ...], '
            '"analysis": "详细学术对比分析", "recommended_generalization": "推广建议"}'
        )

        if papers:
            paper_lines = [
                f"{i}. {p.title} | {', '.join(p.authors[:3])} | {p.published} | {p.url}"
                f"\n   摘要: {p.summary[:280] or '（无摘要）'}"
                for i, p in enumerate(papers[:_MAX_PAPERS_FOR_JUDGE], 1)
            ]
            paper_block = "\n".join(paper_lines)
        else:
            paper_block = "（检索无命中 — 未发现任何相关文献）"

        user_prompt = (
            "【待证明命题 (自然语言)】\n"
            f"{statement_nl or '（未提供 — 请从 Lean 命题推断语义）'}\n"
            "\n"
            "【待证明命题 (Lean 4 声明)】\n"
            f"{lean_statement}\n"
            "\n"
            f"【检索命中的文献 (共 {len(papers)} 篇, 已按最新排序)】\n"
            f"{paper_block}\n"
            "\n"
            "请逐篇比对并输出 JSON 裁决。"
        )
        content = await self._complete(
            system_prompt, user_prompt, self.eval_max_tokens, "独创性裁决"
        )
        match = _JSON_BLOCK_PATTERN.search(content)
        if not match:
            raise RuntimeError(f"ScoutAgent 裁决输出不是 JSON: {content[:200]!r}")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"ScoutAgent 裁决 JSON 解析失败: {exc} — {content[:200]!r}") from exc

        verdict_raw = str(data.get("verdict") or "").strip().upper()
        if verdict_raw not in _VERDICTS:
            raise RuntimeError(f"ScoutAgent 裁决枚举非法: {verdict_raw!r} — {content[:200]!r}")
        try:
            score = int(data.get("novelty_score", 5))
        except (TypeError, ValueError):
            score = 5
        prior = data.get("known_prior_work") or []
        if isinstance(prior, str):
            prior = [prior]
        return NoveltyVerdict(
            verdict=verdict_raw,  # type: ignore[arg-type]
            novelty_score=max(1, min(10, score)),
            known_prior_work=tuple(str(x).strip() for x in prior if str(x).strip()),
            analysis=str(data.get("analysis") or "").strip(),
            recommended_generalization=str(data.get("recommended_generalization") or "").strip(),
        )

    # ---------------- 一站式入口 ----------------

    async def scout(self, statement_nl: str | None, lean_statement: str) -> ScoutReport:
        """一站式查新: 检索式生成 → 学术检索 → 独创性裁决 → 结构化报告。

        Args:
            statement_nl: 命题的自然语言描述 (可为空)。
            lean_statement: 待证明的 Lean 4 命题声明。

        Returns:
            ScoutReport: 含裁决、命中文献、检索式与分阶段耗时的完整报告。
        """
        t0 = time.monotonic()
        queries = await self.generate_search_queries(statement_nl, lean_statement)
        query_seconds = time.monotonic() - t0

        t0 = time.monotonic()
        papers, warnings = await asyncio.to_thread(self.search_academic_sources, queries)
        search_seconds = time.monotonic() - t0

        t0 = time.monotonic()
        verdict = await self.evaluate_novelty(statement_nl, lean_statement, papers)
        evaluate_seconds = time.monotonic() - t0

        return ScoutReport(
            statement_nl=statement_nl or "",
            lean_statement=lean_statement,
            queries=queries,
            papers=tuple(papers),
            verdict=verdict,
            warnings=tuple(warnings),
            query_seconds=query_seconds,
            search_seconds=search_seconds,
            evaluate_seconds=evaluate_seconds,
        )
