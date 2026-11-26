#!/usr/bin/env python3
"""站点生成器：content/ 下的 Markdown + ledger 的产出数据 → dist/ 静态站。

设计约束（刻意为之）：
- 零第三方依赖，只用标准库。装环境不会失败，就不会有"配不动了"的那一天。
- 构建必须是幂等的：同样输入必得同样输出，diff 干净才敢自动提交。
- 数据源只有一个：内容来自 content/，产出日历来自 ledger/data。不复制、不同步。
- 出错要出声：文章 front matter 缺字段直接报错退出，不静默跳过。
"""
import html
import json
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import mdrender

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
TEMPLATES = ROOT / "templates"
ASSETS = ROOT / "assets"
DIST = ROOT / "dist"

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)

# 猫头标志的内联版本，用在顶栏。和 assets/favicon.svg 是同一只猫，
# 但去掉外框、只留脸，在 30px 尺寸下更清楚。
CAT_SVG = """<svg viewBox="4 8 56 52" xmlns="http://www.w3.org/2000/svg" focusable="false">
<path d="M14 26 L12.5 12 L25 18.5 Z" fill="var(--warm)"/>
<path d="M50 26 L51.5 12 L39 18.5 Z" fill="var(--warm)"/>
<path d="M32 17c-9.4 0-17 7.1-17 15.9 0 9 7.6 16.1 17 16.1s17-7.1 17-16.1C49 24.1 41.4 17 32 17z" fill="var(--warm)"/>
<circle cx="24.6" cy="32.4" r="4.1" fill="var(--ink)"/>
<path d="M36.2 29.3l5.6 5.6M41.8 29.3l-5.6 5.6" stroke="var(--ink)" stroke-width="2.8" stroke-linecap="round" fill="none"/>
<path d="M29.4 40.2q2.6 2.4 5.2 0" stroke="var(--ink)" stroke-width="2.2" stroke-linecap="round" fill="none"/>
<path d="M8 34h8M10 39l7 2M56 34h-8M54 39l-7 2" stroke="var(--warm)" stroke-width="2" stroke-linecap="round" fill="none" opacity=".75"/>
</svg>"""


# ---------- front matter ----------

def parse_front_matter(text):
    """解析 --- 包起来的 key: value 头。只支持一层，够用。"""
    m = FM_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip()
        # 数组形式 tags: [a, b]
        if v.startswith("[") and v.endswith("]"):
            meta[k] = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        elif v.lower() in ("true", "false"):
            meta[k] = v.lower() == "true"
        else:
            meta[k] = v.strip('"').strip("'")
    return meta, text[m.end():]


# ---------- 模板 ----------

_TPL_CACHE = {}


def tpl(name):
    if name not in _TPL_CACHE:
        _TPL_CACHE[name] = (TEMPLATES / f"{name}.html").read_text(encoding="utf-8")
    return _TPL_CACHE[name]


def fill(template, **kw):
    """把 {{key}} 替换掉。没给值的占位符原样留着，方便发现漏传。"""
    def sub(m):
        key = m.group(1).strip()
        if key in kw:
            return str(kw[key])
        return m.group(0)

    return re.sub(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}", sub, template)


# ---------- 读取内容 ----------

def load_posts():
    posts = []
    errors = []

    for section in ("log", "works", "thoughts"):
        d = CONTENT / section
        if not d.exists():
            continue
        for f in sorted(d.glob("*.md")):
            raw = f.read_text(encoding="utf-8")
            meta, body = parse_front_matter(raw)

            if not meta.get("title"):
                errors.append(f"{f.relative_to(ROOT)}: 缺 title")
                continue
            if not meta.get("date"):
                errors.append(f"{f.relative_to(ROOT)}: 缺 date")
                continue

            try:
                d_obj = date.fromisoformat(str(meta["date"])[:10])
            except ValueError:
                errors.append(f"{f.relative_to(ROOT)}: date 格式应为 YYYY-MM-DD")
                continue

            slug = meta.get("slug") or f.stem
            posts.append({
                "section": section,
                "slug": slug,
                "title": meta["title"],
                "date": d_obj,
                "date_str": d_obj.isoformat(),
                "summary": meta.get("summary") or mdrender.plain(body, 120),
                "tags": meta.get("tags") or [],
                "draft": bool(meta.get("draft")),
                "body": body,
                "html": mdrender.render(body),
                "source": str(f.relative_to(ROOT)),
                "url": f"/{section}/{slug}/",
            })

    if errors:
        print("内容有问题，构建中止：", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        sys.exit(1)

    posts.sort(key=lambda p: (p["date"], p["slug"]), reverse=True)
    return posts


def load_ledger(cfg):
    """读产出日历数据。路径写在 site.json 里，指不到就退化为空，不让构建挂掉。"""
    days_path = (ROOT / cfg.get("ledger", "")).resolve()
    sum_path = (ROOT / cfg.get("ledgerSummary", "")).resolve()
    if not days_path.exists():
        print(f"  警告：没找到产出数据 {days_path}，日历区会留空", file=sys.stderr)
        return [], {}
    days = json.loads(days_path.read_text(encoding="utf-8"))
    summary = json.loads(sum_path.read_text(encoding="utf-8")) if sum_path.exists() else {}
    return days, summary


# ---------- 页面 ----------

def build_calendar(days, lo, hi):
    """周列热力图。

    布局要点：格子用 grid 显式定位，月份标签用绝对定位挂在同一个滚动画布上。
    早先试过让标签也走 grid，结果 57 列的总宽超出容器，标签被挤成两行、
    和格子完全对不上——标签宽度天生大于格子宽度，不能同用一套列轨。
    """
    from datetime import timedelta

    by_date = {d["date"]: d for d in days}
    start = date.fromisoformat(lo)
    offset = (start.weekday() + 1) % 7  # 对齐到那一周的周日
    start = start - timedelta(days=offset)
    end = date.fromisoformat(hi)

    cells = []
    months = []
    last_month = None
    d = start
    idx = 0
    while d <= end:
        iso = d.isoformat()
        rec = by_date.get(iso)
        week = idx // 7
        dow = idx % 7
        if rec:
            s = rec["score"]
            level = 1 if s < 12 else 2 if s < 30 else 3 if s < 60 else 4
        else:
            level = 0
        ms = " ms" if rec and rec.get("milestone") else ""
        if rec:
            # 只有真有产出的日子才生成落地页，也只有它们才给链接。
            # 空白格子做成链接的话，日历上 390 天里有 276 天是死链。
            proj = "、".join(list(rec.get("repo_breakdown") or {})[:2])
            info = f"<b>{iso}</b>"
            if rec["commits"]:
                info += f"　{rec['commits']} 次提交"
            info += f"　{rec['score']} 分"
            if proj:
                info += f"<br>{html.escape(proj)}"
            cells.append(
                f'<a class="cell l{level}{ms}" style="grid-row:{dow + 1};'
                f'grid-column:{week + 1}" href="/day/{iso}/" '
                f'data-info="{html.escape(info, quote=True)}" '
                f'title="{iso} · {rec["commits"]} 次提交 · {rec["score"]} 分"></a>'
            )
        else:
            cells.append(
                f'<span class="cell l0" style="grid-row:{dow + 1};'
                f'grid-column:{week + 1}" title="{iso} · 没有记录"></span>'
            )
        if d.month != last_month:
            months.append((week, d))
            last_month = d.month
        d += timedelta(days=1)
        idx += 1

    # 月份标签：只有 1 月带年份。
    # 曾经想让第一个月也带年份，但"2025 10月"比一格宽得多，会把紧邻的
    # 11 月标签压住。年份改由下方 range 说明承担，标签只负责定位。
    month_html = []
    for w, dd in months:
        label = f"{dd.year} 1月" if dd.month == 1 else f"{dd.month}月"
        month_html.append(f'<span style="left:{w * 13}px">{label}</span>')

    weeks = idx // 7 + 1
    span_lo = date.fromisoformat(lo).strftime("%Y.%m")
    span_hi = date.fromisoformat(hi).strftime("%Y.%m")
    return f"""<div class="cal-box">
  <div class="cal-scroll">
    <div class="cal-inner" style="width:{weeks * 13}px">
      <div class="cal-months">{''.join(month_html)}</div>
      <div class="cal" style="grid-template-columns:repeat({weeks},10px)">
        {''.join(cells)}
      </div>
    </div>
  </div>
  <div class="cal-legend">
    <span>少</span><i class="cell l0"></i><i class="cell l1"></i><i class="cell l2"></i>
    <i class="cell l3"></i><i class="cell l4"></i><span>多</span>
    <span class="legend-ms"><i class="cell l2 ms"></i>里程碑日</span>
    <span class="legend-range">{span_lo} – {span_hi}</span>
  </div>
</div>"""


def page(title, description, body, cfg, active="", extra_head=""):
    parts = []
    for n in cfg["nav"]:
        cls = ' class="on"' if n["key"] == active else ""
        parts.append(f'<a href="{n["path"]}"{cls}>{n["label"]}</a>')
    nav_html = "".join(parts)
    return fill(
        tpl("base"),
        lang=cfg["site"]["lang"],
        title=html.escape(title),
        description=html.escape(description),
        site_title=html.escape(cfg["site"]["title"]),
        site_title_en=html.escape(cfg["site"].get("titleEn", "")),
        site_url=cfg["site"]["url"].rstrip("/"),
        favicon=cfg["site"].get("favicon", "/favicon.svg"),
        cat_svg=CAT_SVG,
        nav=nav_html,
        body=body,
        year=datetime.now().year,
        extra_head=extra_head,
    )


def post_card(p):
    tags = ""
    if p["tags"]:
        tags = '<span class="tags">' + "".join(
            f'<span class="tag">{html.escape(t)}</span>' for t in p["tags"]
        ) + "</span>"
    tag_attr = html.escape("|".join(p["tags"]), quote=True)
    return f"""<article class="card" data-reveal data-tags="{tag_attr}">
  <a class="card-link" href="{p['url']}">
    <div class="card-meta"><time>{p['date_str']}</time>{tags}</div>
    <h3>{html.escape(p['title'])}</h3>
    <p>{html.escape(p['summary'])}</p>
  </a>
</article>"""


def build_index(cfg, posts, days, summary):
    published = [p for p in posts if not p["draft"]]
    lo, hi = (summary.get("range") or ["2025-11-01", "2026-11-27"])
    cal = build_calendar(days, lo, hi)

    latest = published[:6]
    latest_html = "".join(post_card(p) for p in latest) or '<p class="empty">还没有文章。</p>'

    counts = {s: len([p for p in published if p["section"] == s]) for s in
              ("log", "works", "thoughts")}

    stats = ""
    if summary:
        stats = f"""<div class="stats">
  <div class="stat"><div class="k">活跃日</div><div class="v">{summary['active_days']}</div></div>
  <div class="stat"><div class="k">提交</div><div class="v">{summary['total_commits']}</div></div>
  <div class="stat"><div class="k">私有占比</div><div class="v">{summary['private_ratio']}%</div></div>
  <div class="stat"><div class="k">里程碑日</div><div class="v">{summary['milestone_days']}</div></div>
</div>"""

    body = f"""<section class="hero">
  <h1>在<span class="poke">怪猫</span>的角落，<br>记下做出来的东西</h1>
  <p class="tagline">{html.escape(cfg['site']['tagline'])}</p>
  <p class="desc">{html.escape(cfg['site']['description'])}</p>
  <div class="hero-meta">
    <span class="pill">已记 <b>{summary.get('active_days', 0)}</b> 个有产出的日子</span>
    <span class="pill">文章 <b>{len(published)}</b> 篇</span>
    <span class="pill">数据截至 <b>{summary.get('generated_at', '')[:10] or '—'}</b></span>
  </div>
</section>

<section class="cal-section" data-reveal>
  <div class="sec-head">
    <h2>产出日历</h2>
    <p>每一格是一天。颜色越深，那天做得越多。点进去看当天到底写了什么。</p>
  </div>
  {cal}
  {stats}
</section>

<section class="sections" data-reveal>
  <div class="sec-grid">
    <a class="sec-card" href="/log/">
      <h3>{cfg['sections']['log']['title']} <span class="count">{counts['log']}</span></h3>
      <p>{cfg['sections']['log']['desc']}</p>
      <span class="arrow" aria-hidden="true">→</span>
    </a>
    <a class="sec-card" href="/works/">
      <h3>{cfg['sections']['works']['title']} <span class="count">{counts['works']}</span></h3>
      <p>{cfg['sections']['works']['desc']}</p>
      <span class="arrow" aria-hidden="true">→</span>
    </a>
    <a class="sec-card" href="/thoughts/">
      <h3>{cfg['sections']['thoughts']['title']} <span class="count">{counts['thoughts']}</span></h3>
      <p>{cfg['sections']['thoughts']['desc']}</p>
      <span class="arrow" aria-hidden="true">→</span>
    </a>
  </div>
</section>

<section class="recent" data-reveal>
  <div class="sec-head"><h2>最近写的</h2></div>
  <div class="cards">{latest_html}</div>
</section>"""

    return page(cfg["site"]["title"], cfg["site"]["description"], body, cfg)


def build_section(cfg, section, posts):
    items = [p for p in posts if p["section"] == section and not p["draft"]]
    meta = cfg["sections"][section]
    cards = "".join(post_card(p) for p in items) or '<p class="empty">这一栏还是空的。</p>'

    # 标签筛选：把所有标签聚起来做成 chip，只有一个标签时不显示（没意义）
    all_tags = []
    for p in items:
        for t in p["tags"]:
            if t not in all_tags:
                all_tags.append(t)
    filter_html = ""
    if len(all_tags) > 1:
        chips = ['<button class="chip on" type="button" data-tag="*">全部</button>']
        chips += [f'<button class="chip" type="button" data-tag="{html.escape(t)}">'
                  f'{html.escape(t)}</button>' for t in all_tags]
        filter_html = '<div class="filter-bar" id="filterBar">' + "".join(chips) + "</div>"

    body = f"""<section class="sec-head page-head">
  <h1>{meta['title']}</h1>
  <p>{meta['desc']}</p>
</section>
{filter_html}
<div class="cards">{cards}</div>
<p class="filter-empty" id="filterEmpty">这个标签下还没有文章。</p>"""
    return page(f"{meta['title']} · {cfg['site']['title']}", meta["desc"], body, cfg, active=section)


def build_post(cfg, p):
    tags = ""
    if p["tags"]:
        tags = '<div class="post-tags">' + "".join(
            f'<span class="tag">{html.escape(t)}</span>' for t in p["tags"]
        ) + "</div>"
    section_title = cfg["sections"][p["section"]]["title"]
    body = f"""<article class="post">
  <header>
    <div class="post-meta"><time>{p['date_str']}</time></div>
    <h1>{html.escape(p['title'])}</h1>
    {tags}
  </header>
  <div class="prose">{p['html']}</div>
  <footer class="post-foot">
    <a href="/{p['section']}/">← 回到{section_title}</a>
  </footer>
</article>"""
    return page(f"{p['title']} · {cfg['site']['title']}", p["summary"], body, cfg, active=p["section"])


def build_day(cfg, d, posts):
    """单日详情。这是日历点击后的落地页，也是"这天有产出"的证据页。"""
    if not d:
        return None
    related = [p for p in posts if p["date_str"] == d["date"] and not p["draft"]]

    hl = ""
    if d["highlights"]:
        parts = []
        for h in d["highlights"]:
            tag = f"<b>{html.escape(h['type'])}</b> " if h["type"] else ""
            parts.append(
                f"<li><code>{html.escape(h['repo'])}</code> {tag}"
                f"{html.escape(h['text'])}</li>"
            )
        hl = '<h2 class="plain">当天做了什么</h2><ul class="hl">' + "".join(parts) + "</ul>"

    types = ""
    if d["types"]:
        chips = "".join(
            f"<span>{html.escape(k)} <b>{v}</b></span>" for k, v in d["types"].items()
        )
        types = f'<h2 class="plain">提交类型</h2><div class="types">{chips}</div>'

    rel = ""
    if related:
        rel = '<div class="cards">' + "".join(post_card(p) for p in related) + "</div>"
    else:
        rel = '<p class="empty">这天还没有写成文章。</p>'

    proj = "、".join(d["projects"]) if d["projects"] else "—"
    body = f"""<section class="day-head">
  <div class="post-meta"><time>{d['date']} {d['weekday']}</time></div>
  <h1>{d['date']}</h1>
  <p class="day-stat">
    <span>提交 <b>{d['commits']}</b> 次</span><span class="sep">·</span>
    <span>强度 <b>{d['score']}</b></span><span class="sep">·</span>
    <span><b>{len(d['projects'])}</b> 个项目</span>
  </p>
  <p class="day-stat"><span>{html.escape(proj)}</span></p>
</section>
{hl}
{types}
<h2 class="plain">相关文章</h2>
{rel}
<p class="back"><a href="/">← 回到日历</a></p>"""
    return page(f"{d['date']} · {cfg['site']['title']}", f"{d['date']} 的产出记录", body, cfg)


# ---------- 输出 ----------

def clean_dist():
    """清空 dist。

    不用 shutil.rmtree：一是它在 Windows 上遇到被占用的文件会整体失败，
    二是这个环境里 rmtree 会被拦截去走回收站，导致构建直接崩。
    逐个删文件、再自底向上删空目录，稳得多。
    """
    if not DIST.exists():
        DIST.mkdir(parents=True)
        return
    for p in sorted(DIST.rglob("*"), key=lambda x: len(x.parts), reverse=True):
        try:
            if p.is_file() or p.is_symlink():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
        except OSError:
            pass  # 删不掉就留着，一会儿覆盖写，不影响正确性


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_static():
    if ASSETS.exists():
        for f in ASSETS.rglob("*"):
            if f.is_file():
                target = DIST / f.relative_to(ASSETS)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)


def build_feed(cfg, posts):
    """RSS 2.0。有了它，将来接微信读书、各类阅读器都方便。"""
    base = cfg["site"]["url"].rstrip("/")
    items = []
    for p in posts[:20]:
        items.append(f"""<item>
  <title>{html.escape(p['title'])}</title>
  <link>{base}{p['url']}</link>
  <guid isPermaLink="true">{base}{p['url']}</guid>
  <pubDate>{p['date'].strftime('%a, %d %b %Y 00:00:00 +0800')}</pubDate>
  <description>{html.escape(p['summary'])}</description>
</item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>{html.escape(cfg['site']['title'])}</title>
<link>{base}/</link>
<description>{html.escape(cfg['site']['description'])}</description>
<language>{cfg['site']['lang']}</language>
{''.join(items)}
</channel>
</rss>"""


def main():
    cfg = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
    posts = load_posts()
    days, summary = load_ledger(cfg)

    clean_dist()
    DIST.mkdir(parents=True, exist_ok=True)

    write(DIST / "index.html", build_index(cfg, posts, days, summary))

    for section in ("log", "works", "thoughts"):
        write(DIST / section / "index.html", build_section(cfg, section, posts))

    published = [p for p in posts if not p["draft"]]
    for p in published:
        write(DIST / p["section"] / p["slug"] / "index.html", build_post(cfg, p))

    by_date = {d["date"]: d for d in days}
    for iso, d in by_date.items():
        html_out = build_day(cfg, d, published)
        if html_out:
            write(DIST / "day" / iso / "index.html", html_out)

    write(DIST / "404.html", page(
        "找不到页面", "这个地址没有内容。",
        '<section class="post"><h1>找不到页面</h1>'
        '<p>这个地址没有内容。<a href="/">回到首页</a>。</p></section>',
        cfg,
    ))

    copy_static()

    # 站点地图：让搜索引擎能爬到
    urls = ["/", "/log/", "/works/", "/thoughts/"]
    urls += [p["url"] for p in published]
    urls += [f"/day/{d}/" for d in by_date]
    base = cfg["site"]["url"].rstrip("/")
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sm.append(f"<url><loc>{base}{u}</loc></url>")
    sm.append("</urlset>")
    write(DIST / "sitemap.xml", "\n".join(sm))

    write(DIST / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    write(DIST / "feed.xml", build_feed(cfg, published))

    n_pages = len(list(DIST.rglob("*.html")))
    print(f"构建完成：{n_pages} 个页面，{len(published)} 篇文章，{len(by_date)} 个日历落地页")


if __name__ == "__main__":
    main()
