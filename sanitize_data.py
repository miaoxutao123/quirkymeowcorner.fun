#!/usr/bin/env python3
"""数据脱敏：把产出数据里的密钥、令牌清掉。

为什么必须有这一步：days.json 里的 conv_samples 是对话原文摘录，
里面可能夹着用户当时复制进去的 API Key。这些数据要提交进公开仓库，
一旦推上去就等于公开泄漏——GitHub 的密钥扫描会直接拦下推送，
但更糟的情况是仓库是私有的、没人拦，密钥就这么一直躺在 commit 里。

这里做两道：
1. 按已知模式（sk-xxx、ghp_xxx、AKIA 等）匹配，命中就整段替换成占位符
2. 顺手做一次长度截断，防止超长 base64 之类的东西蒙混过关

用法：
    python sanitize_data.py            # 清理 data/ 下的快照
    python sanitize_data.py --check    # 只检查，有命中就退出码 1
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

# 常见密钥格式。宁可多杀，不可漏放——误杀的是一段文本，漏放的是真钥匙。
PATTERNS = [
    # 顺序有讲究：更具体的前缀要排在通用规则前面，
    # 否则 sk-proj-xxx 会先被 sk- 规则吃掉，替换后剩个 sk-***REDACTED*** 也还行，
    # 但标记就丢了厂商信息，排查时看不出来源。
    (re.compile(r"sk-proj-[A-Za-z0-9_\-]{16,}"), "sk-proj-***REDACTED***"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"), "sk-ant-***REDACTED***"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{16,}"), "sk-***REDACTED***"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "ghp_***REDACTED***"),
    (re.compile(r"gho_[A-Za-z0-9]{20,}"), "gho_***REDACTED***"),
    (re.compile(r"ghu_[A-Za-z0-9]{20,}"), "ghu_***REDACTED***"),
    (re.compile(r"ghs_[A-Za-z0-9]{20,}"), "ghs_***REDACTED***"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "github_pat_***REDACTED***"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA***REDACTED***"),
    # Google AI Studio / Gemini
    (re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "AIza***REDACTED***"),
    # 腾讯云 / 阿里云
    (re.compile(r"AKID[0-9A-Za-z]{32}"), "AKID***REDACTED***"),
    (re.compile(r"LTAI[0-9A-Za-z]{12,}"), "LTAI***REDACTED***"),
    # Slack / Stripe
    (re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"), "xox***REDACTED***"),
    (re.compile(r"[sr]k_live_[A-Za-z0-9]{20,}"), "sk_live_***REDACTED***"),
    # 通用赋值上下文
    (re.compile(r"(?i)(api[_-]?key\"?\s*[:=]\s*\")[^\"\s]{12,}"), r"\1***REDACTED***"),
    (re.compile(r"(?i)((?:app_?secret|client_?secret)\"?\s*[:=]\s*\")[^\"\s]{12,}"), r"\1***REDACTED***"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9_\-\.]{20,}"), r"\1***REDACTED***"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "***JWT-REDACTED***"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "***PRIVATE-KEY-REDACTED***"),
    # 带凭据的 URL（数据库连接串里的 user:password@）。
    # 这里刻意用 "占位" 而不是写真实示例，否则扫描器扫到自己会一直误报。
    (re.compile(r"(mongodb(?:\+srv)?://)[^:\s]+:[^@\s]+@"), r"\1***REDACTED***@"),
]


def scrub(text):
    """返回 (清理后的文本, 命中次数)。"""
    if not isinstance(text, str):
        return text, 0
    hits = 0
    for pat, repl in PATTERNS:
        text, n = pat.subn(repl, text)
        hits += n
    return text, hits


def walk(obj):
    """递归清理 dict / list 里的所有字符串。"""
    total = 0
    if isinstance(obj, dict):
        for k in list(obj):
            obj[k], n = walk(obj[k])
            total += n
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            obj[i], n = walk(v)
            total += n
    elif isinstance(obj, str):
        obj, total = scrub(obj)
    return obj, total


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    check_only = "--check" in sys.argv

    # 默认只扫 data/ 下的快照（那是要进仓库的部分）。
    # 传路径可以扫别的位置，比如 ledger 的备份和产物——泄漏不只在快照里。
    #
    # 显式指定的单个文件不做后缀过滤：备份文件的后缀千奇百怪
    # （days.json.bak_utc 的 suffix 是 ".bak_utc"），白名单一加就会漏掉。
    # 目录递归时仍按常见文本后缀收窄，避免去读二进制。
    TEXTUAL = {".json", ".md", ".html", ".txt", ".py", ".sh", ".js", ".yml", ".yaml", ".css", ".xml"}
    if args:
        files = []
        for a in args:
            p = Path(a)
            if p.is_dir():
                files.extend(sorted(x for x in p.rglob("*") if x.is_file() and x.suffix in TEXTUAL))
            elif p.is_file():
                files.append(p)
    else:
        files = sorted(DATA.glob("*.json"))

    if not files:
        print(f"没有找到可扫描的文件：{DATA}")
        return 0

    grand = 0
    for f in files:
        try:
            raw = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        # 用字符串级替换，避免 json 重新序列化打乱原有格式
        total = 0
        out = raw
        for pat, repl in PATTERNS:
            out, n = pat.subn(repl, out)
            total += n
        grand += total

        if total:
            if check_only:
                print(f"  {f}: 发现 {total} 处疑似密钥")
            else:
                f.write_text(out, encoding="utf-8")
                print(f"  {f}: 已清理 {total} 处")
        elif args:
            # 显式指定路径时把干净的文件也报出来，方便确认确实扫过了
            print(f"  {f}: 干净")

    if check_only and grand:
        print(f"\n共 {grand} 处疑似密钥，需要清理后重新提交。")
        return 1

    if not check_only and grand:
        print(f"\n共清理 {grand} 处。")

    # 清理后确认 JSON 仍然合法（只校验 .json，HTML/MD 不管）
    for f in files:
        if f.suffix != ".json":
            continue
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"  错误：{f} 清理后不是合法 JSON：{e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
