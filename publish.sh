#!/usr/bin/env bash
# 一条命令发布：构建 → 自检 → 提交 → 推送
#
# 用法：
#   ./publish.sh                # 正常发布
#   ./publish.sh "自定义说明"    # 自定义这次提交的说明
#   ./publish.sh --dry          # 只构建和自检，不提交
#
# 设计原则：宁可不发，不可发坏的。
# 任何一步不过就直接退出，不提交半成品。

set -euo pipefail
cd "$(dirname "$0")"

DRY=0
MSG=""
for arg in "$@"; do
  case "$arg" in
    --dry) DRY=1 ;;
    *) MSG="$arg" ;;
  esac
done

say() { printf '\033[1m%s\033[0m\n' "$*"; }
ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }
die() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ---------- 1. 环境 ----------
say "1/5 检查环境"
command -v python >/dev/null || die "找不到 python"
command -v git    >/dev/null || die "找不到 git"
git rev-parse --git-dir >/dev/null 2>&1 || die "当前目录不在 git 仓库里。先执行：git init && git remote add origin <url>"
ok "python / git 就绪"

# ---------- 2. 内容校验 ----------
say "2/5 校验文章"
n_md=$(find content -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
[ "$n_md" -gt 0 ] || die "content/ 下没有 Markdown"
ok "找到 $n_md 篇 Markdown"

# ---------- 3. 构建 ----------
say "3/5 生成站点"
python build.py || die "构建失败"
[ -f dist/index.html ] || die "没有生成 dist/index.html"
ok "dist/ 已生成"

# ---------- 4. 产物自检 ----------
say "4/5 自检产物"

# 4a. 每个静态资源都能被引用到
[ -f dist/style.css ] || die "缺 dist/style.css"
[ -f dist/app.js ] || die "缺 dist/app.js"
[ -f dist/favicon.svg ] || die "缺 dist/favicon.svg"
[ -f dist/feed.xml ] || die "缺 dist/feed.xml"
[ -f dist/sitemap.xml ] || die "缺 dist/sitemap.xml"
[ -f dist/404.html ] || die "缺 dist/404.html"
ok "关键文件齐全"

# 4b. 不能有占位符漏传（{{xxx}} 说明模板变量没被替换）
if grep -rqE '\{\{[a-zA-Z_]+\}\}' dist --include='*.html'; then
  echo "  漏传的模板变量：" >&2
  grep -rhoE '\{\{[a-zA-Z_]+\}\}' dist --include='*.html' | sort -u | sed 's/^/    /' >&2
  die "模板占位符没有被替换"
fi
ok "模板变量全部替换"

# 4c. 不能有本地绝对路径泄漏
if grep -rqE 'file:///|[A-Za-z]:\\\\' dist --include='*.html'; then
  die "产物里有本地绝对路径，检查 build.py 的链接生成"
fi
ok "没有本地路径泄漏"

# 4d. 相对链接都能对上实际文件
python - <<'PY' || die "站内有死链"
import re, sys
from pathlib import Path

dist = Path("dist")
bad = []
for f in dist.rglob("*.html"):
    txt = f.read_text(encoding="utf-8")
    for href in re.findall(r'href="(/[^"#?]*)"', txt):
        if href.endswith((".css", ".xml", ".txt")):
            if not (dist / href.lstrip("/")).exists():
                bad.append((f.name, href))
            continue
        p = dist / href.lstrip("/")
        if not (p / "index.html").exists() and not p.exists():
            bad.append((f.name, href))
if bad:
    print(f"  {len(bad)} 个链接指向不存在的页面：", file=sys.stderr)
    for name, href in bad[:10]:
        print(f"    {name} → {href}", file=sys.stderr)
    sys.exit(1)
PY
ok "站内链接全部可达"

# 4e. 文章页数量对得上
n_posts=$(find dist -mindepth 2 -maxdepth 2 -name 'index.html' -path '*/log/*' -o -mindepth 2 -maxdepth 2 -name 'index.html' -path '*/works/*' -o -mindepth 2 -maxdepth 2 -name 'index.html' -path '*/thoughts/*' | wc -l | tr -d ' ')
[ "$n_posts" -ge 1 ] || die "没有生成任何文章页"
ok "文章页 $n_posts 个"

if [ "$DRY" -eq 1 ]; then
  say "--dry：自检通过，不提交"
  exit 0
fi

# ---------- 5. 提交与推送 ----------
say "5/5 提交并推送"

git add -A

if git diff --cached --quiet; then
  ok "没有变更，无需提交"
  exit 0
fi

[ -n "$MSG" ] || MSG="publish: $(date '+%Y-%m-%d %H:%M')"

git -c core.quotepath=false commit -q -m "$MSG"
ok "已提交：$MSG"

branch=$(git rev-parse --abbrev-ref HEAD)
if git remote get-url origin >/dev/null 2>&1; then
  git push -q origin "$branch"
  ok "已推送到 origin/$branch"
  printf '\n发布完成。Cloudflare 会在几十秒内自动构建上线。\n'
else
  printf '\n\033[33m还没有配置 origin 远程仓库，提交已完成但未推送。\033[0m\n'
  printf '配好之后执行：git push -u origin %s\n' "$branch"
fi
