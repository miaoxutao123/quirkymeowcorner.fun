# 有产出的日子 · 博客

一个记录产出、作品与思考的静态站。零第三方依赖，一条命令发布。

## 快速开始

```bash
# 写一篇
$EDITOR content/log/2026-11-27-标题.md

# 发布
./publish.sh
```

就这样。`publish.sh` 会构建、自检、提交、推送，然后 Cloudflare 自动上线。

## 目录

```
blog/
├── content/            # 只改这里
│   ├── log/            #   日志：做东西的过程
│   ├── works/          #   作品：做完的东西
│   └── thoughts/       #   思考：和 agent 聊完的判断
├── templates/base.html # 页面骨架
├── assets/style.css    # 全部样式
├── site.json           # 站点配置（标题、栏目、产出数据路径）
├── build.py            # 生成器
├── mdrender.py         # Markdown 渲染
├── publish.sh          # 一键发布
└── dist/               # 产物，不入库
```

## 写文章

文件名随意，但建议 `日期-短标题.md`。开头必须有 front matter：

```markdown
---
title: 文章标题
date: 2026-11-27
tags: [标签1, 标签2]
summary: 一句话摘要，会显示在列表页和 RSS 里。
draft: false
---

正文从这开始。
```

必填只有 `title` 和 `date`。`summary` 不写会自动从正文抽前 120 字。

`draft: true` 的文章不会出现在列表和 RSS 里，但文件会提交——适合先放着。

### 支持的 Markdown

标题、段落、粗体、斜体、删除线、行内代码、围栏代码块、无序/有序列表、引用、表格、链接、图片、分隔线。

就这些。没实现的语法（比如脚注）会原样当文本输出，不会报错也不会吞内容。

## 发布流程

```bash
./publish.sh                # 构建 + 自检 + 提交 + 推送
./publish.sh "改了什么"      # 自定义提交说明
./publish.sh --dry          # 只构建和自检，不提交
```

### 自检会拦住这些

发布前会跑五项检查，任何一项不过就不提交：

1. 关键文件齐全（style.css / feed.xml / sitemap.xml / 404.html）
2. 模板变量全部替换（防止 `{{title}}` 漏传上线）
3. 没有本地绝对路径泄漏（`file:///`、`C:\\`）
4. **站内链接全部可达**（这条抓到过 284 个死链）
5. 至少生成了一个文章页

宁可不发，不可发坏的。这是刻意的。

## 产出日历

首页的日历数据来自 `../ledger/data/days.json`，路径写在 `site.json` 里。

改了 ledger 的数据后，重新跑 `./publish.sh` 就会同步。找不到数据文件时不会报错，只是日历区留空。

日历上的格子只有**有产出的日子**才可点击。空白日是静态格子——早先做成链接，结果 390 天里 276 天是死链。

## 部署

托管在 **Cloudflare Workers Static Assets**（不是 Pages）。

原因：Cloudflare 2025 年 4 月起把投入全部转向 Workers，Pages 进入维护模式。静态资源在 Workers 上**请求免费且不限量**，成本一样，但不会一开始就站在停止演进的产品上。

配置在 `wrangler.jsonc`，指向 `./dist`。

### 首次部署

1. 建远程仓库并推送：

```bash
git remote add origin <你的仓库地址>
git push -u origin main
```

2. Cloudflare Dashboard → Workers & Pages → Create → 连接这个仓库
3. 构建设置：
   - Build command：`python build.py`
   - Deploy command：`npx wrangler deploy`
4. 部署后到 Settings → Domains & Routes 绑定你的域名

之后每次 `./publish.sh` 推上去，Cloudflare 自动构建上线。

### 本地预览

```bash
cd dist && python -m http.server 8791
```

注意必须用 HTTP 服务打开，不能双击 HTML 文件——CSS 用的是 `/style.css` 绝对路径，`file://` 协议下会加载失败。

## 设计取舍

**为什么不用 Astro / Hugo。** 前两次博客（`miaomiao-halo-blog`、`hexo_site_publish`）都死在依赖和图床上，Pages 至今 404。这次的判断是：**能自己修的东西才会一直用下去**。300 行 Python，出问题看堆栈就能定位。

代价是没有主题生态，样式要自己写。接受了。

**为什么不引数据库和前端框架。** 内容量到不了需要它们的规模。真到那一天，Markdown 文件不用改，换的只是外层。

**为什么不按文件数算产出。** 一次批量操作生成上万个文件仍然只是「一件事」。计分细节见 `../ledger/README.md`。
