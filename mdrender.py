#!/usr/bin/env python3
"""一个够用的 Markdown 子集渲染器。

为什么不用 markdown / mistune：
前两次博客都死在依赖上。这里只需要处理我实际会写的东西——
标题、段落、列表、代码块、引用、表格、链接、图片、行内强调。
自己写 200 行，出问题能自己修，不用等上游。

不支持的语法会被当成普通文本原样输出，不会报错、不会吃掉内容。
"""
import html
import re

# ---------- 行内 ----------


def _inline(text):
    """处理行内标记。顺序有讲究：先转义，再替换，代码片段要保护起来。"""
    # 行内代码先占位，避免里面的星号、下划线被当成强调
    codes = []

    def stash_code(m):
        codes.append(html.escape(m.group(1)))
        return f"\x00CODE{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash_code, text)

    text = html.escape(text, quote=False)

    # 图片 ![alt](src)
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)\)",
        r'<img src="\2" alt="\1" loading="lazy">',
        text,
    )
    # 链接 [text](url)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )
    # 粗体、斜体、删除线
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", text)

    # 还原代码
    for i, c in enumerate(codes):
        text = text.replace(f"\x00CODE{i}\x00", f"<code>{c}</code>")
    return text


# ---------- 受限的 iframe 嵌入 ----------
#
# 文章里偶尔要嵌一个自己的作品（比如一份单文件 HTML 演示）。
# 但不能为了这个就把渲染器改成"原样放行任意 HTML"——那等于给每一篇
# Markdown 开了注入口子，粘贴来的内容也能带 <script>。
# 所以只放行 iframe 一种标签，并且：
#   属性名必须在白名单里（srcdoc、onload 之类天然进不来）；
#   src 只能是站内路径，不能带 .. 回退、不能是 javascript:。
# 不满足的一律按普通文本转义输出，和"不支持的语法原样显示"保持一致。
IFRAME_ATTRS = {
    "src", "width", "height", "loading", "title", "class",
    "allowfullscreen", "sandbox", "referrerpolicy", "style",
}


def _safe_iframe(block):
    if not re.match(r"^<iframe\s+[^>]*>\s*</iframe>$", block, re.I):
        return False
    attrs = re.findall(r'([a-zA-Z-]+)(?:\s*=\s*"([^"]*)")?', block)
    src = None
    for name, value in attrs:
        name = name.lower()
        if name == "iframe":
            continue
        if name not in IFRAME_ATTRS:
            return False
        if name == "src":
            src = value or ""
    if not src:
        return False
    if not src.startswith("/") or src.startswith("//"):
        return False
    if ".." in src or "\\" in src or "javascript:" in src.lower():
        return False
    return True


# ---------- 块级 ----------

FENCE_RE = re.compile(r"^\s*```(\w*)\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
UL_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
OL_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
HR_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def render(md):
    """Markdown 文本 → HTML 片段。"""
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # 围栏代码块
        m = FENCE_RE.match(line)
        if m:
            lang = m.group(1)
            i += 1
            buf = []
            while i < n and not FENCE_RE.match(lines[i]):
                buf.append(lines[i])
                i += 1
            i += 1  # 跳过收尾围栏
            body = html.escape("\n".join(buf))
            cls = f' class="language-{lang}"' if lang else ""
            out.append(f"<pre><code{cls}>{body}</code></pre>")
            continue

        # 空行
        if not line.strip():
            i += 1
            continue

        # 受限 iframe：单独成块，前后段落都不能把它吞进去
        if line.lstrip().lower().startswith("<iframe"):
            block = line.strip()
            i += 1
            while i < n and "</iframe>" not in block and lines[i].strip():
                block += " " + lines[i].strip()
                i += 1
            out.append(block if _safe_iframe(block) else f"<p>{html.escape(block)}</p>")
            continue

        # 分隔线
        if HR_RE.match(line):
            out.append("<hr>")
            i += 1
            continue

        # 标题
        m = HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            i += 1
            continue

        # 表格：当前行含竖线且下一行是分隔行
        if "|" in line and i + 1 < n and TABLE_SEP_RE.match(lines[i + 1]):
            header = _split_row(line)
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(_split_row(lines[i]))
                i += 1
            th = "".join(f"<th>{_inline(c)}</th>" for c in header)
            tb = "".join(
                "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
                for r in rows
            )
            # 表格外面套一层滚动容器。
            # 不能直接给 table 加 display:block 来做横向滚动——那会把
            # table 布局干掉，表格缩成内容宽度，在宽屏上只占左边一小块。
            out.append(
                f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead>'
                f"<tbody>{tb}</tbody></table></div>"
            )
            continue

        # 引用块（连续 > 行合并）
        if QUOTE_RE.match(line):
            buf = []
            while i < n and QUOTE_RE.match(lines[i]):
                buf.append(QUOTE_RE.match(lines[i]).group(1))
                i += 1
            inner = render("\n".join(buf))
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        # 无序列表
        if UL_RE.match(line):
            buf = []
            while i < n and UL_RE.match(lines[i]):
                buf.append(UL_RE.match(lines[i]).group(1))
                i += 1
            items = "".join(f"<li>{_inline(x)}</li>" for x in buf)
            out.append(f"<ul>{items}</ul>")
            continue

        # 有序列表
        if OL_RE.match(line):
            buf = []
            while i < n and OL_RE.match(lines[i]):
                buf.append(OL_RE.match(lines[i]).group(1))
                i += 1
            items = "".join(f"<li>{_inline(x)}</li>" for x in buf)
            out.append(f"<ol>{items}</ol>")
            continue

        # 段落：连续非空、非块级起始的行合并
        buf = [line.strip()]
        i += 1
        while i < n:
            nxt = lines[i]
            if not nxt.strip():
                break
            if (FENCE_RE.match(nxt) or HEADING_RE.match(nxt) or QUOTE_RE.match(nxt)
                    or UL_RE.match(nxt) or OL_RE.match(nxt) or HR_RE.match(nxt)
                    or nxt.lstrip().lower().startswith("<iframe")
                    or ("|" in nxt and i + 1 < n and TABLE_SEP_RE.match(lines[i + 1]))):
                break
            buf.append(nxt.strip())
            i += 1
        out.append(f"<p>{_inline(' '.join(buf))}</p>")

    return "\n".join(out)


def plain(md, limit=140):
    """抽纯文本摘要，用于列表页和 meta description。"""
    text = md
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)
    text = re.sub(r"^>\s?", "", text, flags=re.M)
    text = re.sub(r"[*_~|]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text
