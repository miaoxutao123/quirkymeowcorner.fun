---
title: 一天推完六个版本
date: 2026-09-10
tags: [unity, agent, 工作流]
summary: 从一个空仓库到 v0.5，38 次提交全在一天之内。回头看，真正起作用的不是手速，是把"做到哪一步算完"提前定义清楚。
---

2026 年 9 月 10 日，我在 `wanderstar-worldsmith-demokit` 这个仓库推了 38 次提交。

第一次提交是凌晨 1 点 29 分，最后一次是晚上 8 点 01 分。中间跨了 v0.1、v0.2、v0.2.1、v0.3、v0.4、v0.5 六个版本标签。

这不是我状态最好的一天，但是结构最清楚的一天。所以值得写下来。

## 时间线

按提交时间还原，那天大致是这么过去的：

| 时段 | 干了什么 |
|---|---|
| 01:29 – 02:10 | v0.2 的 GameplayGraphIR、能力清单、实体注册表 |
| 10:26 – 11:33 | v0.2.1 加固，v0.3 星图与旅行服务 |
| 13:04 – 16:02 | v0.4 视觉资产、摄影呈现系统、Blender 素材 |
| 19:26 – 20:01 | v0.5 Dawnscar 星球设计 |

凌晨那段是纯架构，白天那段在补内容，傍晚那段在调观感。三种心态，三段连着。

## 让一天能推六个版本的三件事

**第一，把"完成"定义成可以提交的最小单位。**

v0.2 那一段的提交信息是这样的：

```
feat(v0.2): add GameplayGraphIR and capability manifest schema
feat(v0.2): EntityRegistry, WorldStateStore, graph runtime, the ...
feat(v0.2): generic F/E/Q interactor, zones, bootstrap orchestration
test(v0.2): dual-world graph smoke + negatives + no world-id s...
```

每一笔都是"可以单独回滚、单独说明"的状态。这一点很关键——如果一次提交里混了三个未完成的改动，回滚就没法做，后面出了线你也找不到是哪笔弄坏的。

**第二，先写验收标准，再写实现。**

那天有个规律：每个版本的前一两笔提交里一定有 `docs` 或 `test`，比如：

```
docs: add v0.2 Generic Agent World Runtime development spec
docs(v0.2.1): acceptance, runtime contracts, entity capabiliti...
```

我是先把"这个版本算不算做完"写成清单，然后照着清单写代码。这样做的直接好处是：不需要在写代码的过程中反复问自己"还要加什么"，判断成本从每一步降到了每版本一次。

**第三，用版本号切段，而不是用时间切段。**

时间切段（"今天下午做 v0.3"）的问题是结束点是主观的，容易拖。版本号切段的结束点写死在验收清单里，做完就是做完，做不完就说明这一版划大了，下一版拆小。

那天 v0.4 和 v0.5 都很小，基本是观感调整。这是刻意的：大版本之后接一个轻的，避免连着两版都开天窗。

## 一个反面的细节

那天最后三笔是：

```
fix(v0.3): visible feedback for photo/scan/interact success, f...
fix(v0.4): planet clipping and smooth terrain
fix(v0.5): make runtime systems truly generic, fix assist timer P1
```

三笔都是"加完之后发现不够"。尤其最后那笔 `make runtime systems truly generic`——我在 v0.2 就写了"generic"这个词，到 v0.5 才发现还真不 generic。

这类问题在当天修掉是好事，但它说明前面的验收清单漏了一条：**"generic" 这种词必须配一个反例测试**，否则它只是形容词。

后来我给自己加了条规矩，写在项目的 `AGENT.md` 里：任何声称"通用"的设计，必须在验收清单里配一个"换一个具体实例还能跑"的测试，否则不许叫通用。

## 值得记的一点

那天我同时在跟几个 coding agent 协作，但真正决定产出密度的不是 agent 快不快，是**我能不能在开工前把边界说清楚**。

边界清楚的版本，agent 一次就能给出可提交的代码；边界模糊的版本，来回对话十几轮，最后还是要自己写。

这也解释了为什么那天能推六个版本，而有些日子一次提交都没有。差别不在工具，在开工前那十分钟有没有想清楚。
