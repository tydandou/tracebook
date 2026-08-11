# Tracebook first-launch copy

These drafts are ready for manual posting after checking each community's
current rules. Replace no claims with estimates: the linked demo verifies
cross-session persistence, evidence, isolation, and health checks, but it is not
a token-savings benchmark.

## Hacker News — Show HN

**Title**

Show HN: Tracebook – Evidence-backed project memory for coding agents

**Post**

I built Tracebook because my coding agents kept rediscovering the same project
facts in every new session: architecture decisions, incident root causes, API
contracts, and business rules.

Tracebook is a local-first Agent Skill for Codex, Claude Code, and compatible
Open Agent Skills hosts. It loads focused project knowledge before repository
work and captures only conclusions that are durable, verified, and backed by a
source reference.

The storage model is deliberately boring: inspectable Markdown under
`~/.tracebook`. There is no server, database, daemon, embedding model, API key,
or memory folder added to business repositories.

The part I cared most about was governance rather than capture volume. Facts
have stable IDs, lifecycle states, version history, explicit project scope, and
health checks that surface missing or newer evidence. Cross-project context is
available only through explicit project selection or recorded system
relationships.

I added a reproducible demo that runs the real workflow in temporary
directories: Session 1 captures a refund retry policy with source evidence;
Session 2 retrieves it; everything is removed on exit.

Site and demo: https://tydandou.github.io/tracebook/

Source: https://github.com/tydandou/tracebook

I would especially value feedback on the boundary: would you rather keep agent
memory outside the repo, or review it alongside code?

## Reddit — r/ClaudeAI, r/codex, or r/LocalLLaMA

**Title**

I built a local Markdown project memory for coding agents—with evidence and lifecycle, not transcript dumps

**Post**

Disclosure: I am the maintainer.

My recurring problem with Claude Code and Codex was not raw context size. It was
losing the conclusions that took real work to verify. A new session would reopen
the same files and reconstruct the same architecture decision or bug root cause.

Tracebook preserves those conclusions as an external Markdown knowledge layer.
Before repository work it retrieves only relevant current knowledge. After the
task it writes nothing unless the conclusion is durable, verified, and tied to
evidence.

Design choices:

- local Markdown under `~/.tracebook`
- no MCP server, vector DB, daemon, hook, cloud account, or API key
- zero writes to the business repository
- Current / Pending / Deprecated / Superseded / Historical lifecycle
- stable project identity across clones of the same Git remote
- explicit, bounded cross-project relationships
- transactional writes and health checks for stale evidence

It is not semantic search, and it is not a task manager. The tradeoff is less
automatic capture in exchange for a smaller, inspectable set of governed facts.

I made the core claim reproducible instead of publishing a made-up token number:
the demo captures a sourced rule in one simulated session and recalls it in a
second, using isolated temporary directories.

Demo: https://tydandou.github.io/tracebook/demo/

GitHub: https://github.com/tydandou/tracebook

I am looking for critical feedback from people who use coding agents on
long-lived repositories. What would make this trustworthy enough to keep
installed?

## V2EX — 分享创造

**标题**

[开源] Tracebook：给 Codex / Claude Code 一个有证据、能跨会话的本地项目记忆

**正文**

大家好，我是 Tracebook 的维护者。

我在长期使用编程 Agent 时反复遇到一个问题：上次花时间确认过的架构决策、事故根因、
API 约定和业务规则，到了新会话又要重新读代码、重新推导。

Tracebook 想解决的不是“保存更多聊天记录”，而是保存少量经过验证、以后值得复用的工程
结论。Agent 开始仓库工作前只读取当前任务相关的知识；任务结束后，只有通过证据门禁的
持久结论才会写入。

目前的设计：

- 知识以 Markdown 保存在本机 `~/.tracebook`
- 不需要服务器、数据库、后台进程、向量模型或 API Key
- 不向业务仓库写入记忆目录、Hook 或配置
- 知识支持 Current、Pending、Deprecated、Superseded 和历史版本
- 每个当前事实都可以关联源码、配置、测试或文档证据
- 支持显式、有边界的多项目系统关系
- 写入带事务保护，并可检查缺失或晚于知识更新时间的证据

它不是项目任务管理器，也不是语义搜索引擎。这个边界是有意的：我更关心 Agent 为什么
相信一个项目事实，以及这个事实是否仍然有效。

我准备了一个可以直接运行的隔离演示：第一次会话捕获带源码证据的退款重试规则，第二次
会话检索出来，退出后自动删除临时项目和知识根目录。没有拿无法复现的 Token 百分比做宣传。

官网与演示：https://tydandou.github.io/tracebook/

GitHub：https://github.com/tydandou/tracebook

很希望听到大家对“知识放在业务仓库外”这个取舍的意见。如果你实际使用 Codex、Claude Code
或其他编程 Agent，也欢迎告诉我什么条件会让你愿意长期保留这样一个 Skill。
