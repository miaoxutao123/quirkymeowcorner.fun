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

# 产出数据快照：从上级 ledger/ 同步过来。
# 站点是独立仓库，ledger 在仓库外，不同步的话云端构建读不到数据。
bash sync-data.sh || die "同步产出数据失败"

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

# 4b-2. 要提交的内容里不能有密钥。
# 这道守卫是被 GitHub 的 secret scanning 拦下来之后补的：days.json 的
# conv_samples 存的是对话原文，里面有当时贴进去的真实 API Key，
# 推到公开仓库等于公开泄漏。
#
# 扫两处：data/ 的数据快照，以及暂存区里所有将要提交的文本文件。
# 只扫 data/ 不够——content/ 下的文章也可能引用到原文。
if ! python sanitize_data.py --check >/dev/null 2>&1; then
  echo "  数据里有疑似密钥，已阻止提交：" >&2
  python sanitize_data.py --check 2>&1 | sed 's/^/  /' >&2
  die "先跑 python sanitize_data.py 清理"
fi

# 暂存区里的文本文件逐个扫，命中就阻止。用 git diff --cached 拿文件名，
# 避免把 dist/ 之类的大目录也扫一遍。
leaked=""
while IFS= read -r f; do
  [ -f "$f" ] || continue
  case "$f" in
    *.json|*.md|*.html|*.txt|*.py|*.sh|*.js|*.yml|*.yaml|*.css|*.xml|*.svg) ;;
    *) continue ;;
  esac
  if grep -qaE 'sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{35}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|AKID[0-9A-Za-z]{32}|LTAI[0-9A-Za-z]{12,}|xox[baprs]-[A-Za-z0-9-]{10,}' "$f" 2>/dev/null; then
    leaked="$leaked  $f"$'\n'
  fi
done < <(git diff --cached --name-only --diff-filter=ACM 2>/dev/null)

if [ -n "$leaked" ]; then
  echo "  即将提交的文件里有疑似密钥：" >&2
  printf '%s' "$leaked" >&2
  die "清理后再提交（python sanitize_data.py <file>）"
fi

# 产物 HTML 也不能带（build.py 可能把对话原文渲染进页面）
if grep -rqE 'sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{35}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}' dist --include='*.html' --include='*.xml' 2>/dev/null; then
  die "产物 HTML 里有疑似密钥，检查 build.py 是否把对话原文渲染进页面"
fi
ok "没有密钥泄漏"

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

# 4e. 日历必须真有内容。
# 线上曾经出现过整片空日历、首屏写着"已记 0 个有产出的日子"却构建成功的情况，
# 所以这里直接断言产物里有非零的日历格子和真实的提交数。
python - <<'PY' || die "日历没有内容"
import re, sys
from pathlib import Path

html = Path("dist/index.html").read_text(encoding="utf-8")

# 有产出的格子是 <a class="cell l1..l4">，空白日是 <span class="cell l0">。
# 图例里的样例格子也是 <i class="cell lN">，所以必须按标签名限定，
# 否则会把图例的 5 个样本算进来（114 天会显示成 119）。
active = len(re.findall(r'<a class="cell l[1-4]', html))
if active == 0:
    print("  首页日历里没有任何带产出的格子（全是 l0）", file=sys.stderr)
    sys.exit(1)

m = re.search(r'已记 <b>(\d+)</b>', html)
if not m or int(m.group(1)) == 0:
    print("  首屏统计显示有产出的日子为 0", file=sys.stderr)
    sys.exit(1)

# 数据截至不能是占位符
if "数据截至 <b>—</b>" in html:
    print("  首屏「数据截至」是空的", file=sys.stderr)
    sys.exit(1)

# 日历上可点的天数应当和首屏「已记 N 天」对得上。
# 对不上的话说明数据统计和日历渲染用了两套口径，是更隐蔽的 bug。
days = int(m.group(1))
if active != days:
    print(f"  日历格子 {active} 个，但首屏写着已记 {days} 天", file=sys.stderr)
    sys.exit(1)

print(f"  日历 {active} 个有产出的格子，与「已记 {days} 天」一致")
PY
ok "日历有实际内容"

# 4f. 文章页数量对得上
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

# 注意：这里不能"没有变更就 exit"。
# 没有新变更，不代表远程是最新的——可能是手动 commit 过、或者上次推送失败、
# 或者只是落后于 origin。提交和推送是两件事，必须分开判断。
if git diff --cached --quiet; then
  ok "没有新变更，跳过提交"
else
  [ -n "$MSG" ] || MSG="publish: $(date '+%Y-%m-%d %H:%M')"
  git -c core.quotepath=false commit -q -m "$MSG"
  ok "已提交：$MSG"
fi

branch=$(git rev-parse --abbrev-ref HEAD)
if git remote get-url origin >/dev/null 2>&1; then
  if git push -q origin "$branch"; then
    ok "已推送到 origin/$branch"
    printf '\n发布完成。Cloudflare 会在几十秒内自动构建上线。\n'
  else
    die "推送失败（检查凭证或网络），提交仍保留在本地"
  fi
else
  printf '\n\033[33m还没有配置 origin 远程仓库，提交已完成但未推送。\033[0m\n'
  printf '配好之后执行：git push -u origin %s\n' "$branch"
fi
