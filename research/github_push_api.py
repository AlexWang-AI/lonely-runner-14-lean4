"""github_push_api.py — 经 api.github.com 推送本地提交 (直连被墙时的等价通道)

流程: 读取 git HEAD 的全部文件 → blob → tree → commit → 更新 refs/heads/main。
Token 从环境变量 GH_TOKEN 读取 (绝不落盘)。
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import urllib.request

OWNER = "AlexWang-AI"
REPO = "lonely-runner-14-lean4"
API = f"https://api.github.com/repos/{OWNER}/{REPO}"


def api(method: str, path: str, token: str, data: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{API}{path}", method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Math-Institute-push",
        },
    )
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(data).encode("utf-8")
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read()
        return json.loads(body) if body else {}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        print("缺少 GH_TOKEN 环境变量")
        sys.exit(2)
    # 空仓库判定与引导 (必须先于 blob: 空仓库时 Git Data API 一律 409)
    parent = None
    try:
        ref = api("GET", "/git/ref/heads/main", token)
        parent = ref["object"]["sha"]
        print(f"已有 main ref: {parent[:8]} (作为 parent)")
    except Exception:
        print("仓库为空 — 用 Contents API 创建初始提交")
        readme = open("README.md", "rb").read()
        api("PUT", "/contents/README.md", token, {
            "message": "chore: initialize repository with README",
            "content": base64.b64encode(readme).decode("ascii"),
            "branch": "main",
        })
        ref = api("GET", "/git/ref/heads/main", token)
        parent = ref["object"]["sha"]
        print(f"初始提交 ✓ {parent[:8]}")

    files = subprocess.run(
        ["git", "ls-tree", "-r", "HEAD", "--name-only"],
        capture_output=True, text=True, encoding="utf-8",
    ).stdout.splitlines()
    print(f"待推送文件 {len(files)} 个")

    blobs: list[dict] = []
    for path in files:
        data = open(path, "rb").read()
        blob = api("POST", "/git/blobs", token,
                   {"content": base64.b64encode(data).decode("ascii"),
                    "encoding": "base64"})
        blobs.append({"path": path, "mode": "100644", "type": "blob",
                      "sha": blob["sha"]})
        print(f"  blob ✓ {path} ({len(data)} B)")
    tree = api("POST", "/git/trees", token, {"tree": blobs})
    print(f"tree ✓ {tree['sha']}")

    commit_data = {
        "message": "feat: complete formal verification of 14-runner CRT "
                   "decoupling in Lean 4 (0-sorry)",
        "tree": tree["sha"],
    }
    if parent:
        commit_data["parents"] = [parent]
    commit = api("POST", "/git/commits", token, commit_data)
    print(f"commit ✓ {commit['sha']}")

    api("PATCH", "/git/refs/heads/main", token,
        {"sha": commit["sha"], "force": True})
    print(f"\n✅ 推送完成: https://github.com/{OWNER}/{REPO}")
    print(f"   commit: {commit['sha']}")


if __name__ == "__main__":
    main()
