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

# 常见的密钥前缀。宁可多杀，不可漏放——误杀的是一段文本，漏放的是真钥匙。
PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{16,}"), "sk-***REDACTED***"),
    (re.compile(r"sk-proj-[A-Za-z0-9_\-]{16,}"), "sk-proj-***REDACTED***"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "ghp_***REDACTED***"),
    (re.compile(r"gho_[A-Za-z0-9]{20,}"), "gho_***REDACTED***"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "github_pat_***REDACTED***"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA***REDACTED***"),
    (re.compile(r"(?i)(api[_-]?key\"?\s*[:=]\s*\")[^\"\s]{12,}"), r"\1***REDACTED***"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9_\-\.]{20,}"), r"\1***REDACTED***"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "***JWT-REDACTED***"),
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
    check_only = "--check" in sys.argv
    files = sorted(DATA.glob("*.json"))
    if not files:
        print(f"没有找到数据文件：{DATA}")
        return 0

    grand = 0
    for f in files:
        raw = f.read_text(encoding="utf-8")
        # 用字符串级替换，避免 json 重新序列化打乱原有格式
        total = 0
        out = raw
        for pat, repl in PATTERNS:
            out, n = pat.subn(repl, out)
            total += n
        grand += total

        if total:
            if check_only:
                print(f"  {f.name}: 发现 {total} 处疑似密钥")
            else:
                f.write_text(out, encoding="utf-8")
                print(f"  {f.name}: 已清理 {total} 处")
        else:
            print(f"  {f.name}: 干净")

    if check_only and grand:
        print(f"\n共 {grand} 处疑似密钥，需要清理后重新提交。")
        return 1

    if not check_only and grand:
        print(f"\n共清理 {grand} 处。")

    # 清理后确认仍是合法 JSON
    for f in files:
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"  错误：{f.name} 清理后不是合法 JSON：{e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
