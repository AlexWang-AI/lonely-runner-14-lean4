"""
lean_verifier.py — Lean 4 形式化验证器 (LeanValidator) · v3 常驻服务架构

本模块是"AI 数学研究所"系统的【无情裁判】:
  - 不调用任何大模型, 只做极度严谨的代码提取、沙箱运行与报错捕获。
  - 它是 Prover Agent 与 Critic Agent 之间唯一的"事实来源" (source of truth)。

══════════════════════════ v3 架构 (Phase 2.5 性能手术) ══════════════════════════

[性能死穴与对策] (2026-08 实测)
  死穴 1: CLI 模式每次 `lean 文件.lean` 都要重新从磁盘加载全部 .olean
          (Mathlib.Tactic 实测 40~92 秒)。
  对策:   上线常驻进程 `lean --server` (LSP / JSON-RPC over stdio):
          - 进程常驻, 导入环境驻留内存, 只加载一次;
          - 每次验证通过 textDocument/didChange 推送新代码, 复用同一文档,
            服务器只重新加工变更部分 (实测秒级);
          - 配合 main_loop 的"预热与 Prover 推理并行", 单步验证成本趋近于零。
  死穴 2: Prover (v4-pro) 无预算约束深度思考空转 170 秒 → 已在 agents.py 修复
          (max_tokens + thinking_budget + 策略优先级 Prompt)。

[降级链] (任何一环失效都能出结果)
  常驻服务 (秒级) → 超时/崩溃 → 击杀并下次重建
                → 服务不可用 → 直连 lean.exe + Lake 环境缓存 (~40s)
                → lake 不可用 → lake env lean 慢速路径 (~50s)

[已知边界]
  - 常驻模式固定使用 server_prelude 导入 (默认 import Mathlib.Tactic), 代码自带
    import 行会被剥离 (避免导入集变化触发内存重载)。若证明需要超出 Mathlib.Tactic
    的模块, 请增大 server_prelude (如 "import Mathlib") — 一次重载, 之后仍秒级。
  - 死循环 (#eval 不终止) 会卡死常驻进程 → 超时后自动击杀并重建 (代价一次重载)。
"""

from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# 模块级常量
# ---------------------------------------------------------------------------

_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
_WORKSPACE_DIR: Final[Path] = _PROJECT_ROOT / "MathWorkspace"
_SANDBOX_FILE_NAME: Final[str] = "temp_verify.lean"

# v2 保留: CLI 回退路径的默认注入导入
DEFAULT_IMPORT: Final[str] = "import Mathlib.Tactic"

_DEFAULT_TIMEOUT: Final[float] = 300.0
_MAX_MESSAGE_LENGTH: Final[int] = 4000

_CODE_TAG_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"<\s*lean_code\s*>(.*?)<\s*/\s*lean_code\s*>",
    re.IGNORECASE | re.DOTALL,
)
_IMPORT_LINE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\s*import\s+\S+", re.MULTILINE)
# 常驻模式下剥离用户代码中的 import 行 (统一由 prelude 提供)
_STRIP_IMPORT_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\s*import\s+[^\n]*\n?", re.MULTILINE)
# 自适应 prelude 升级触发条件: 报错属于"窄导入缺东西"类, 而非代码本身有错
_WIDEN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"unknown identifier|unknown constant|unknown tactic|unknown module|"
    r"cannot find|undeclared|not found",
    re.IGNORECASE,
)


class LeanCodeParseError(ValueError):
    """Lean 代码提取失败时抛出的解析异常 (无标签 / 标签内为空 / 非字符串)。"""


class _ServerTimeoutError(TimeoutError):
    """常驻服务在期限内未返回诊断信息 (疑似死循环卡死服务器)。"""


def _truncate(text: str, limit: int = _MAX_MESSAGE_LENGTH) -> str:
    """截断过长的报错日志, 并在末尾标注被截断的字符数。"""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [已截断, 省略 {len(text) - limit} 个字符]"


# ---------------------------------------------------------------------------
# Lean 常驻服务会话 (LSP 客户端: JSON-RPC 帧协议 over stdio)
# ---------------------------------------------------------------------------


class _LeanServerSession:
    """`lean --server` 常驻会话。

    实现 LSP 的极小子集:
      - Content-Length 帧协议 (与 VSCode 同款);
      - initialize / initialized 握手;
      - textDocument/didOpen 首次推送文档 (触发导入加载);
      - textDocument/didChange 全量更新文档 (导入环境复用, 秒级重加工);
      - 监听 textDocument/publishDiagnostics 获取编译诊断。
    """

    def __init__(
        self,
        lean_exe: str,
        workspace_dir: Path,
        env: dict[str, str],
        doc_uri: str,
        prelude: str,
    ) -> None:
        """启动服务并完成握手 + 预热导入。

        Raises:
            RuntimeError: 进程启动失败或握手超时。
            _ServerTimeoutError: 预热导入加载超时。
        """
        self._doc_uri = doc_uri
        self._prelude = prelude
        self._version = 0
        self._next_id = 1
        self._dead = False
        self._lock = threading.Lock()
        self._responses: dict[int, threading.Event] = {}
        self._response_payloads: dict[int, dict] = {}
        self._diags: dict[str, tuple[list[dict], threading.Event]] = {}
        # fileProgress 加工完成信号 (processing 列表为空 = 该文档加工完毕)
        self._progress_done: dict[str, threading.Event] = {}

        try:
            self.proc = subprocess.Popen(
                [lean_exe, "--server"],
                cwd=str(workspace_dir),
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,  # 服务日志不阻塞管道
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"无法启动 lean --server: {exc}") from exc

        reader = threading.Thread(target=self._reader_loop, daemon=True)
        reader.start()

        # 握手: initialize (id=0)
        root_uri = workspace_dir.as_uri()
        try:
            self._send_request(
                "initialize",
                {"processId": os.getpid(), "rootUri": root_uri, "capabilities": {}},
                timeout=120,
            )
            self._send_notification("initialized", {})
        except Exception as exc:
            self.close()
            raise RuntimeError(f"lean --server 握手失败: {exc}") from exc

        # 预热: 打开文档并加载导入 (最耗时的一次, 之后全部秒级)
        try:
            self.open_document(prelude, timeout=600)
        except Exception:
            self.close()  # 预热失败必须击杀进程, 绝不留僵尸服务器吃资源
            raise

    # ---------------- 底层帧收发 ---------------- #

    def _send(self, payload: dict) -> None:
        """按 LSP Content-Length 帧协议发送一条消息。"""
        frame = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        header = f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii")
        with self._lock:
            if self._dead or self.proc.poll() is not None:
                raise RuntimeError("lean --server 进程已退出")
            self.proc.stdin.write(header + frame)
            self.proc.stdin.flush()

    def _send_request(self, method: str, params: dict, timeout: float) -> dict:
        """发送带 id 的请求并同步等待响应。"""
        req_id = self._next_id
        self._next_id += 1
        event = threading.Event()
        with self._lock:
            self._responses[req_id] = event
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        if not event.wait(timeout):
            raise _ServerTimeoutError(f"{method} 响应超时 ({timeout:.0f}s)")
        return self._response_payloads.pop(req_id, {})

    def _send_notification(self, method: str, params: dict) -> None:
        """发送无 id 的通知 (不等待响应)。"""
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _reader_loop(self) -> None:
        """后台线程: 持续解析服务器消息帧并分发。"""
        stream = self.proc.stdout
        try:
            while True:
                frame = self._read_frame(stream)
                if frame is None:
                    break
                try:
                    msg = json.loads(frame.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if "method" in msg:      # 服务器 → 客户端通知
                    self._handle_notification(msg)
                elif "id" in msg:        # 请求响应
                    with self._lock:
                        self._response_payloads[msg["id"]] = msg
                        event = self._responses.get(msg["id"])
                    if event is not None:
                        event.set()
        except Exception:
            pass
        finally:
            self._dead = True

    @staticmethod
    def _read_frame(stream) -> bytes | None:
        """读取一个 Content-Length 帧; 流结束返回 None。"""
        headers: dict[bytes, bytes] = {}
        while True:
            line = stream.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            key, _, value = line.partition(b":")
            headers[key.strip().lower()] = value.strip()
        length = int(headers.get(b"content-length", b"0"))
        return stream.read(length)

    def _handle_notification(self, msg: dict) -> None:
        """处理服务器推送的通知 (publishDiagnostics + fileProgress 完成信号)。

        实测协议 (探针 v3 结论):
          - 每次变更先来一轮【早期诊断】(0.2s, 常为空), 之后服务器继续后台加工;
          - 加工完成后推送【最终诊断】(含真实错误) + fileProgress 空列表;
          - 死循环代码: 早期诊断之后再无任何信号 (服务器永久卡死) → 超时击杀。
        因此等待协议必须是两阶段: 诊断 → 加工完成信号。
        注意: 必须 set 等待线程所持有的【既有 Event】, 而不是替换成新 Event。
        """
        method = msg.get("method")
        params = msg.get("params", {})
        if method == "textDocument/publishDiagnostics":
            uri = params.get("uri", "")
            diags = params.get("diagnostics", [])
            with self._lock:
                entry = self._diags.get(uri)
                event = entry[1] if entry is not None else threading.Event()
                self._diags[uri] = (list(diags), event)
                event.set()
        elif method == "$/lean/fileProgress":
            # processing 为空列表 = 加工完成; 否则只是进度心跳 (kind=1 开始等)
            if not params.get("processing"):
                uri = params.get("textDocument", {}).get("uri", "")
                with self._lock:
                    if uri:
                        self._progress_done.setdefault(uri, threading.Event()).set()
                    else:
                        # uri 缺失时保守广播: 唤醒所有等待者 (避免永久阻塞)
                        for event in self._progress_done.values():
                            event.set()

    # ---------------- 文档操作 ---------------- #

    def _wait_diagnostics(self, uri: str, timeout: float) -> list[dict]:
        """两阶段等待 (探针 v3 实测协议): 诊断推送 → 加工完成信号 → 返回最新诊断。

        若只等第一轮诊断会在 0.2s 就返回空结果 (误判成功); 必须等到
        fileProgress 空列表 (加工完成) 才算数 — 此刻最终诊断已就位。
        死循环代码永远等不到完成信号 → 超时 → 由调用方击杀服务器。
        """
        deadline = time.monotonic() + timeout
        with self._lock:
            _, diag_event = self._diags.setdefault(uri, ([], threading.Event()))
            done_event = self._progress_done.setdefault(uri, threading.Event())
            diag_event.clear()
            done_event.clear()

        # 阶段 1: 等待 (早期) 诊断推送
        remaining = deadline - time.monotonic()
        if not diag_event.wait(remaining):
            raise _ServerTimeoutError(f"诊断响应超时 ({timeout:.0f}s)")
        # 阶段 2: 等待加工完成信号 (最终诊断在此时已就位)
        remaining = deadline - time.monotonic()
        if not done_event.wait(remaining):
            raise _ServerTimeoutError(f"加工完成信号超时 ({timeout:.0f}s)")

        with self._lock:
            diags, _ = self._diags.get(uri, ([], threading.Event()))
            return list(diags)

    def open_document(self, text: str, timeout: float) -> list[dict]:
        """首次打开文档 (触发导入加载), 返回加载后的诊断。"""
        self._version += 1
        self._send_notification(
            "textDocument/didOpen",
            {"textDocument": {"uri": self._doc_uri, "languageId": "lean4",
                              "version": self._version, "text": text}},
        )
        return self._wait_diagnostics(self._doc_uri, timeout)

    def change_document(self, text: str, timeout: float) -> list[dict]:
        """全量更新文档内容 (导入环境复用, 只重加工变更部分)。"""
        self._version += 1
        self._send_notification(
            "textDocument/didChange",
            {"textDocument": {"uri": self._doc_uri, "version": self._version},
             "contentChanges": [{"text": text}]},
        )
        return self._wait_diagnostics(self._doc_uri, timeout)

    def set_prelude(self, prelude: str) -> None:
        """更新文档导入头部 (自适应升级用; 下次 change_document 生效)。"""
        self._prelude = prelude

    def close(self) -> None:
        """击杀常驻进程 (含子进程树)。"""
        self._dead = True
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                    capture_output=True, timeout=10,
                )
            else:
                self.proc.kill()
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# LeanValidator v3
# ---------------------------------------------------------------------------


class LeanValidator:
    """Lean 4 形式化验证器 — 系统的无情裁判 (v3 常驻服务架构)。

    典型用法:
        verifier = LeanValidator()
        verifier.warmup()                  # 可与 Prover 推理并行, 预热导入
        result = verifier.verify_code("example : 2 + 2 = 4 := by norm_num")
        # 第二次起每次验证秒级完成
    """

    def __init__(
        self,
        workspace_dir: Path | str | None = None,
        sandbox_file_name: str = _SANDBOX_FILE_NAME,
        default_import: str = DEFAULT_IMPORT,
        use_server: bool = True,
        server_prelude: str = "import Mathlib.Tactic.NormNum.Basic",
        prelude_ladder: tuple[str, ...] = (DEFAULT_IMPORT,),
        worker_id: str | None = None,
    ) -> None:
        """初始化验证器。

        Args:
            workspace_dir: Lean 工作区路径, 默认自动定位到项目根的 MathWorkspace/。
            sandbox_file_name: 沙箱临时文件名, 默认 temp_verify.lean。
            default_import: CLI 回退路径中, 代码无 import 时注入的默认导入。
            use_server: 是否启用 lean --server 常驻服务 (强烈建议 True)。
            server_prelude: 常驻模式的第一级 (最窄) 导入头部。
                默认 NormNum.Basic (实测加载 ~21s, 比 Mathlib.Tactic 快 2-7 倍);
                预热速度因此大幅提升。
            prelude_ladder: 自适应升级阶梯。验证报"未知标识符/未知 tactic"类
                错误时自动升级到下一级重新验证 (实测机制见 _verify_server)。
                默认阶梯: NormNum.Basic → Mathlib.Tactic; 需要更大覆盖面可追加
                "import Mathlib" (代价: 升级时一次性重载约 3 分钟)。
            worker_id: 并行 Worker 标识 (V3 并行引擎用)。非空时沙箱文件名自动
                变为 temp_worker_{worker_id}.lean, 各 Worker 文件绝不重名 —
                杜绝多支线并发验证时的文件覆写 race condition。注意: 并行使用
                时每个 Worker 必须持有独立的 LeanValidator 实例 (常驻服务会话
                与沙箱文件均为实例私有, 实例间零共享)。
        """
        self.workspace_dir: Path = (
            Path(workspace_dir).resolve() if workspace_dir else _WORKSPACE_DIR
        )
        self.worker_id: str | None = worker_id
        if worker_id and sandbox_file_name == _SANDBOX_FILE_NAME:
            sandbox_file_name = f"temp_worker_{worker_id}.lean"
        self.sandbox_file: Path = self.workspace_dir / sandbox_file_name
        self.default_import: str = default_import
        self.use_server: bool = use_server
        self.server_prelude: str = server_prelude
        # 自适应 prelude 阶梯: 从最窄开始, 报"未知标识符"时逐级升级
        self._prelude_ladder: tuple[str, ...] = (server_prelude,) + tuple(prelude_ladder)
        self._prelude_tier: int = 0
        self._lake_env_cache: dict[str, str] | None = None
        self._session: _LeanServerSession | None = None
        self._session_lock = threading.Lock()
        self._server_disabled = False  # 服务不可用后永久回退 CLI

    # ------------------------------------------------------------------ #
    # 1. 精准提取器 (与 v2 一致)                                          #
    # ------------------------------------------------------------------ #

    def extract_lean_code(self, raw_text: str) -> str:
        """从混合了自然语言与代码的字符串中, 精准提取 <lean_code> 标签内的代码。

        实战加固 (V5 首战): 模型常把代码再包一层 Markdown 围栏
        (```lean ... ```), 直接编译会报 unexpected token '`' — 此处剥离。
        """
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise LeanCodeParseError("输入文本为空, 无法提取 Lean 代码")
        match = _CODE_TAG_PATTERN.search(raw_text)
        if match is None:
            raise LeanCodeParseError(
                "未找到 <lean_code> ... </lean_code> 标签, "
                "请让 Prover Agent 用标签包裹代码后重试"
            )
        code = match.group(1).strip()
        # 剥离 Markdown 代码围栏 (```lean / ``` 首尾行)
        code = re.sub(r"^```(?:lean4?|mathlib)?\s*", "", code)
        code = re.sub(r"\s*```$", "", code)
        code = code.strip()
        if not code:
            raise LeanCodeParseError("<lean_code> 标签内代码为空")
        return code

    # ------------------------------------------------------------------ #
    # 2. 常驻服务管理                                                      #
    # ------------------------------------------------------------------ #

    def _build_env(self) -> dict[str, str]:
        """构造子进程基础环境: elan bin 前置到 PATH (unicode 路径陷阱兜底)。"""
        env = os.environ.copy()
        home = Path(os.environ.get("USERPROFILE") or Path.home())
        elan_bin = home / ".elan" / "bin"
        if elan_bin.is_dir():
            env["PATH"] = str(elan_bin) + os.pathsep + env.get("PATH", "")
        return env

    @staticmethod
    def _resolve_executable(name: str, env: dict[str, str]) -> str | None:
        """解析可执行文件绝对路径 (Windows PATH 含中文时 CreateProcess 搜索失效)。"""
        return shutil.which(name, path=env.get("PATH"))

    def _get_lake_env(self) -> dict[str, str]:
        """Lake 预编译环境上下文 (带缓存): LEAN_PATH 等, 供 lean 直连使用。"""
        if self._lake_env_cache is not None:
            return self._lake_env_cache
        env = self._build_env()
        lake = self._resolve_executable("lake", env)
        if lake is None:
            raise RuntimeError("找不到 lake 可执行文件")
        proc = subprocess.run(
            [lake, "env", "printenv"],
            cwd=str(self.workspace_dir), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"lake env printenv 失败: "
                f"{proc.stderr.decode('utf-8', errors='replace').strip()[:200]}"
            )
        lake_vars: dict[str, str] = {}
        for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                lake_vars[key.strip()] = value.strip()
        if "LEAN_PATH" not in lake_vars:
            raise RuntimeError("lake env printenv 输出中缺少 LEAN_PATH")
        merged = env.copy()
        merged.update(lake_vars)
        merged["PATH"] = env["PATH"]
        self._lake_env_cache = merged
        return merged

    def warmup(self) -> None:
        """预热常驻服务: 启动 lean --server 并加载导入 (可与 Prover 推理并行)。

        失败时不抛异常 (由 verify_code 自动降级 CLI 路径), 保证管线永不中断。
        """
        if not self.use_server:
            return
        try:
            self._ensure_session()
        except Exception:
            pass  # 预热失败 → 验证时自动回退 CLI

    def _ensure_session(self) -> _LeanServerSession | None:
        """惰性创建常驻会话 (线程安全, 幂等); 失败一次后永久禁用服务。"""
        with self._session_lock:
            if self._server_disabled:
                return None
            if self._session is not None and not self._session._dead:
                return self._session
            try:
                env = self._get_lake_env()
                lean_exe = self._resolve_executable("lean", env)
                if lean_exe is None:
                    raise RuntimeError("找不到 lean 可执行文件")
                self._session = _LeanServerSession(
                    lean_exe=lean_exe,
                    workspace_dir=self.workspace_dir,
                    env=env,
                    doc_uri=self.sandbox_file.as_uri(),
                    prelude=self._prelude_ladder[self._prelude_tier],
                )
                atexit.register(self.close)  # 进程退出时收尸, 杜绝孤儿服务器
                return self._session
            except Exception:
                if self._session is not None:
                    self._session.close()  # 击杀任何残留进程, 防止僵尸服务器
                self._session = None
                self._server_disabled = True  # 永久回退 CLI, 不再重试
                return None

    def close(self) -> None:
        """显式关闭常驻服务 (进程随 Python 退出也会被系统回收)。"""
        with self._session_lock:
            if self._session is not None:
                self._session.close()
                self._session = None

    # ------------------------------------------------------------------ #
    # 3. 编译器无情检验 (v3: 常驻服务快路径 + CLI 降级链)                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _diags_to_result(
        diags: list[dict], code: str, elapsed: float, mode: str
    ) -> dict[str, str]:
        """把 LSP 诊断数组映射为统一结果字典。

        severity: 1=error, 2=warning, 3=info, 4=hint。
        """
        errors = [d for d in diags if d.get("severity") == 1]
        warnings = [d for d in diags if d.get("severity") == 2]

        def _fmt(d: dict) -> str:
            start = d.get("range", {}).get("start", {})
            line = int(start.get("line", 0)) + 1
            col = int(start.get("character", 0)) + 1
            return f"  第 {line} 行第 {col} 列: {d.get('message', '')}"

        if errors:
            body = "\n".join(_fmt(d) for d in errors[:15])
            return {
                "status": "error",
                "message": f"编译失败 ❌ ({mode}, 耗时 {elapsed:.2f} 秒, "
                           f"{len(errors)} 个错误):\n{_truncate(body)}",
                "code": code,
            }
        if warnings:
            body = "\n".join(_fmt(d) for d in warnings[:10])
            return {
                "status": "success",
                "message": f"验证通过 ✅ ({mode}, 耗时 {elapsed:.2f} 秒), "
                           f"{len(warnings)} 条警告:\n{_truncate(body)}",
                "code": code,
            }
        return {
            "status": "success",
            "message": f"验证通过 ✅ ({mode}, 耗时 {elapsed:.2f} 秒, 零警告)",
            "code": code,
        }

    def _verify_server(self, code: str, timeout: float) -> dict[str, str] | None:
        """常驻服务快路径 (含自适应 prelude 升级); 服务不可用返回 None (降级 CLI)。

        杠杆 1 (2026-08 性能手术): 默认用最窄导入预热 (NormNum.Basic ~21s,
        比 Mathlib.Tactic 快 2-7 倍); 若报错属于"未知标识符/未知 tactic"类
        (窄导入缺东西), 自动升级 prelude 阶梯并重验 — 升级代价一次性, 之后仍秒级。
        """
        session = self._ensure_session()
        if session is None:
            return None
        document = self._prelude_ladder[self._prelude_tier] + "\n\n" + _STRIP_IMPORT_PATTERN.sub("", code)

        def _run(document_text: str) -> dict[str, str]:
            start = time.monotonic()
            try:
                diags = session.change_document(document_text, timeout=timeout)
            except _ServerTimeoutError:
                with self._session_lock:
                    if self._session is session:
                        self._session.close()
                        self._session = None
                return {
                    "status": "timeout",
                    "message": (
                        f"编译超时 ({timeout:.0f} 秒, 已击杀常驻进程, 下次验证自动重建)。"
                        f"疑似死循环或证明搜索爆炸卡死服务器"
                    ),
                    "code": code,
                }
            except Exception:
                with self._session_lock:
                    if self._session is session:
                        self._session.close()
                        self._session = None
                return {"status": "__server_down__", "message": "", "code": code}
            return self._diags_to_result(diags, code, time.monotonic() - start, mode="常驻服务")

        result = _run(document)
        # 自适应升级: 窄导入缺东西 (未知标识符类) 且阶梯还有更宽层级 → 升级重验
        while (
            result["status"] == "error"
            and _WIDEN_PATTERN.search(result["message"])
            and self._prelude_tier < len(self._prelude_ladder) - 1
        ):
            self._prelude_tier += 1
            widened = self._prelude_ladder[self._prelude_tier]
            session.set_prelude(widened)
            document = widened + "\n\n" + _STRIP_IMPORT_PATTERN.sub("", code)
            result = _run(document)
            if result["status"] in ("success", "timeout"):
                result["message"] += f"\n(已自适应升级 prelude → {widened})"

        if result["status"] == "__server_down__":
            return None
        return result

    def verify_code(self, code: str, timeout: float = _DEFAULT_TIMEOUT) -> dict[str, str]:
        """对已提取的纯净代码执行 Lean 4 编译检验 (核心方法, v3 降级链)。

        执行策略 (自动降级):
            1. 常驻服务: lean --server + didChange (热内存, 秒级);
            2. CLI 快路径: 直连 lean.exe + Lake 环境缓存 (~40s);
            3. CLI 慢路径: lake env lean (~50s)。

        Args:
            code: 待验证的 Lean 代码 (纯净代码, 不含标签)。
            timeout: 编译超时秒数, 默认 300 秒。

        Returns:
            统一字典:
              {"status": "success" | "error" | "timeout", "message": ..., "code": ...}
        """
        if self.use_server:
            server_result = self._verify_server(code, timeout)
            if server_result is not None:
                return server_result

        # ---------------- CLI 降级链 (v2 逻辑) ---------------- #
        try:
            sandbox_path = self._write_to_sandbox(code)
        except FileNotFoundError as exc:
            return {"status": "error", "message": f"沙箱写入失败: {exc}", "code": code}

        base_env = self._build_env()
        try:
            lake_env = self._get_lake_env()
        except Exception:
            lake_env = None
        if lake_env is not None:
            lean_exe = self._resolve_executable("lean", lake_env)
            command = [lean_exe or "lean", sandbox_path.name]
            run_env = lake_env
            mode = "CLI 快路径"
        else:
            lake_exe = self._resolve_executable("lake", base_env)
            command = [lake_exe or "lake", "env", "lean", sandbox_path.name]
            run_env = base_env
            mode = "CLI 慢路径"

        try:
            proc = subprocess.Popen(
                command, cwd=str(self.workspace_dir), env=run_env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            return {
                "status": "error",
                "message": "找不到 lean 可执行文件, 请确认 Lean 4 工具链已安装且 "
                           "~/.elan/bin 在 PATH 中 (Phase 1 应已配置)",
                "code": code,
            }

        start_time = time.monotonic()
        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout)
            elapsed = time.monotonic() - start_time
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start_time
            LeanValidator._kill_process_tree(proc)
            stdout_bytes, stderr_bytes = proc.communicate()
            partial_log = _truncate(
                (stderr_bytes.decode("utf-8", errors="replace").strip()
                 or stdout_bytes.decode("utf-8", errors="replace").strip()
                 or "(超时前无任何输出 — 疑似死循环证明)")
            )
            return {
                "status": "timeout",
                "message": (
                    f"编译超时 ({timeout:.0f} 秒, 已击杀进程树)。可能原因: "
                    f"① 慢导入 (本机 Mathlib.Tactic 加载实测 40~92 秒) "
                    f"② 证明搜索爆炸或死循环。超时前输出:\n{partial_log}"
                ),
                "code": code,
            }

        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
        if proc.returncode == 0:
            if stderr:
                message = f"验证通过 ✅ ({mode}, 耗时 {elapsed:.2f} 秒)。编译器警告:\n{_truncate(stderr)}"
            else:
                message = f"验证通过 ✅ ({mode}, 耗时 {elapsed:.2f} 秒, 零警告)"
            return {"status": "success", "message": message, "code": code}
        error_log = stderr or stdout or "(无输出)"
        return {
            "status": "error",
            "message": f"编译失败 ❌ ({mode}, 耗时 {elapsed:.2f} 秒):\n{_truncate(error_log)}",
            "code": code,
        }

    # ------------------------------------------------------------------ #
    # 4. 沙箱写入 (CLI 路径用) 与一站式入口                               #
    # ------------------------------------------------------------------ #

    def _ensure_default_import(self, code: str) -> str:
        """CLI 路径导入策略: 代码自带 import 则保留, 否则注入默认导入。"""
        if _IMPORT_LINE_PATTERN.search(code):
            return code
        return f"{self.default_import}\n\n{code}"

    def _write_to_sandbox(self, code: str) -> Path:
        """将代码写入沙箱文件 (CLI 路径用, 每次覆盖)。"""
        if not self.workspace_dir.is_dir():
            raise FileNotFoundError(
                f"Lean 工作区不存在: {self.workspace_dir} (请先完成 Phase 1 初始化)"
            )
        code = self._ensure_default_import(code)
        self.sandbox_file.write_text(code, encoding="utf-8")
        return self.sandbox_file

    @staticmethod
    def _kill_process_tree(proc: subprocess.Popen) -> None:
        """超时后击杀整个进程树 (Windows 用 taskkill /T 递归击杀)。"""
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True, timeout=10,
                )
            else:
                proc.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def clear_env_cache(self) -> None:
        """清空 Lake 环境缓存。依赖更新 (lake update) 后调用。"""
        self._lake_env_cache = None

    def verify(self, raw_text: str, timeout: float = _DEFAULT_TIMEOUT) -> dict[str, str]:
        """完整验证管线: 提取标签代码 → 编译检验 → 统一字典返回。

        提取失败时返回 parse_error 而非抛出异常。
        """
        try:
            code = self.extract_lean_code(raw_text)
        except LeanCodeParseError as exc:
            return {
                "status": "parse_error",
                "message": f"代码提取失败: {exc}",
                "code": "",
            }
        return self.verify_code(code, timeout=timeout)


# ---------------------------------------------------------------------------
# 自检入口: 常驻服务秒级验证 + CLI 降级路径回归
#   python agent_core/lean_verifier.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    verifier = LeanValidator()
    print("=" * 64)
    print("[自检 1] parse_error — 无标签输入 (纯正则, 秒级)")
    r0 = verifier.verify("这是一段没有标签的普通文本")
    print(f"  status: {r0['status']}")

    print("[自检 2] 常驻服务预热 (一次性导入加载)")
    t0 = time.monotonic()
    verifier.warmup()
    print(f"  预热耗时: {time.monotonic() - t0:.1f} 秒")

    print("[自检 3] 常驻服务 · 合法证明 (应秒级)")
    t0 = time.monotonic()
    r1 = verifier.verify_code("example : 2 + 2 = 4 := by norm_num")
    dt1 = time.monotonic() - t0
    print(f"  status: {r1['status']} | 耗时: {dt1:.2f} 秒")

    print("[自检 4] 常驻服务 · 非法代码 (应秒级报错)")
    t0 = time.monotonic()
    r2 = verifier.verify_code("example : Nat = String := by rfl")
    dt2 = time.monotonic() - t0
    print(f"  status: {r2['status']} | 耗时: {dt2:.2f} 秒")

    print("[自检 5] 常驻服务 · 死循环击杀 (2 秒短超时, 服务将被重建)")
    hang = "partial def loop (n : Nat) : Nat := loop n\n#eval loop 0"
    r3 = verifier.verify_code(hang, timeout=2.0)
    print(f"  status: {r3['status']}")

    print("[自检 6] CLI 降级路径回归 (use_server=False)")
    cli_verifier = LeanValidator(use_server=False)
    t0 = time.monotonic()
    r4 = cli_verifier.verify_code("example : 2 + 2 = 4 := by rfl")
    dt4 = time.monotonic() - t0
    print(f"  status: {r4['status']} | 耗时: {dt4:.1f} 秒")

    print("=" * 64)
    ok = (
        r0["status"] == "parse_error"
        and r1["status"] == "success"
        and r2["status"] == "error"
        and r3["status"] == "timeout"
        and r4["status"] == "success"
    )
    print("功能自检全部通过 ✅" if ok else "功能自检存在异常 ❌, 请检查上方输出")
    print(f"关键指标: 常驻服务单次验证 {dt1:.2f}s / {dt2:.2f}s (v2 CLI 为 40~90s)")
