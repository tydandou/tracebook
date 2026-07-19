# Tracebook

[English](README.md) | [简体中文](README.zh-CN.md)

Tracebook 是面向软件开发工作的本地持久化知识层。它的 Agent Skill 会在任务开始前加载
聚焦的项目上下文，并在任务结束后把经过验证、值得长期保留的结论捕获到业务仓库之外。

本仓库同时提供 Codex 和 Claude Code 的原生 marketplace metadata；支持 Open Agent
Skills 的其他 Agent 也能使用同一份 Skill 包。日常使用以自然语言为主；确定性 JSON
runner 则用于集成、诊断和高级工作流。

## 为什么需要 Tracebook

重要的工程上下文很容易散落在对话、事故记录、源代码和个人笔记中。Tracebook 将这些
上下文保存在受治理的 Markdown 知识根目录里，并记录证据、生命周期状态、索引和健康
历史。Agent 只需读取相关上下文，而人可以检查捕获了什么以及为什么捕获。

知识根目录与业务代码相互分离。因此，多个业务仓库可以共用一个本地知识系统，无需向
这些业务仓库安装文件、hook 或服务。

## 核心能力

- 使用项目、领域和模式三种范围，分别保存仓库专属事实、可复用业务知识和可复用工程实践。
- 基于证据捕获知识，并支持 `Current`、`Pending`、`Deprecated`、`Superseded` 和
  `Historical` 生命周期状态。
- 确定性解析项目、执行受治理写入、更新索引/状态/日志，并返回结构化 JSON 结果。
- 通过标准化 Git 身份让同一远端的多个 clone 共享项目知识，同时隔离无关项目。
- 提供 Local、Light、Regular 和显式 Deep 健康行为；Deep 发现只是待复核候选，
  不会自动成为事实。
- 生成可移植的标准 Markdown 链接，并审计 Wikilink，以兼容手工编辑的 Obsidian 知识。
- 知识保存在本地，对业务仓库保持严格的零写入边界。

## 环境要求

- 项目解析需要 Git 仓库。没有远端的仓库会使用稳定的绝对路径回退身份。
- 源码使用的 Python 语法要求 Python 3.10 或更高版本。发布 CI 矩阵配置为在 Ubuntu
  和 Windows 上验证 Python 3.10 与 3.13；本地完整验证环境是 Windows 上的 Python
  3.13.12。
- 通过 marketplace 安装时使用 Codex 或 Claude Code。文档中的命令形态已用 Codex
  CLI 0.144.1 和 Claude Code 2.1.138 核验；这些版本是验证证据，并非声明的最低版本。
- 对其他 Open Agent Skills host，按其文档规定的方式安装完整 Skill 目录；同样需要满足
  上述 Python runtime 要求。

## 安装

当前仓库是 `1.0.0` 发布候选。在匹配的 `v1.0.0` tag 发布前，
[CHANGELOG.md](CHANGELOG.md) 会保持 Unreleased。下面带 tag 的 Codex 命令应在
tag 发布后使用；从未打 tag 的 clone 开发时，请使用本地加载方式。

### Codex

tag 发布后执行：

```text
codex plugin marketplace add tydandou/tracebook --ref v1.0.0
codex plugin add tracebook@tracebook
```

本地开发时，clone 仓库并添加其本地 marketplace：

```text
git clone https://github.com/tydandou/tracebook.git
cd tracebook
codex plugin marketplace add .
codex plugin add tracebook@tracebook
```

安装后启动新的 Codex 会话。

### Claude Code

```text
claude plugin marketplace add tydandou/tracebook
claude plugin install tracebook@tracebook
```

从本地 clone 开发时，直接加载插件目录：

```text
git clone https://github.com/tydandou/tracebook.git
cd tracebook
claude --plugin-dir ./plugins/tracebook
```

通过 marketplace 安装后，启动新会话或运行 `/reload-plugins`。

### Open Agent Skills

可复用包位于
[`plugins/tracebook/skills/tracebook/`](plugins/tracebook/skills/tracebook/)。
将这个完整目录以 `tracebook` 名称复制到目标 Agent 文档指定的 Skill 目录，然后启动
新会话。请让 `SKILL.md`、`references/`、`assets/` 和 `scripts/` 保持在一起。

知识默认保存在 `~/.tracebook`。如需选择其他外部根目录，请在启动 Agent 前设置
`TRACEBOOK_ROOT`。下面的示例只读取现有的用户主目录值，不会替换或赋值 `HOME`。

POSIX shell：

```sh
export TRACEBOOK_ROOT="$HOME/team-knowledge"
```

PowerShell：

```powershell
$env:TRACEBOOK_ROOT = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'team-knowledge'
```

## 快速开始

1. 通过 marketplace 安装 Tracebook，或加载本地 clone。
2. 在正在处理的 Git 仓库中启动新的 Agent 会话。
3. 发出请求：`Use Tracebook to load the relevant project knowledge before you
   diagnose this issue.`
4. 像平常一样工作。Tracebook 会解析外部根目录和项目身份，并返回一小组有序的上下文
   路径供 Agent 读取。
5. 完成有证据支持的工作后，发出请求：`Capture the verified durable conclusions
   with Tracebook and report the health result.` 检查返回的知识改动、证据、生命周期状态
   和健康结果。

临时问答、纯日志分析、未经验证的推断、用户禁止写入或没有持久结论的任务，不会触发
Tracebook 写入持久知识。

## 选择知识范围

| 范围 | 适用内容 | 存储位置 |
| --- | --- | --- |
| `project` | 单个仓库特有的事实 | `01-projects/<slug>` |
| `domain` | 可复用的业务术语、规则、流程或行业知识 | `02-domain` |
| `pattern` | 可复用的工程实践 | `03-patterns` |

应选择最窄且准确的范围。不能仅因为项目事实可能对其他地方有用，就把它提升为领域或
模式知识。

## 自然语言使用方式

Plugin 的设计目标是在日常任务语言中直接调用。例如：

- `Use Tracebook to load architecture and source-map context before changing the order flow.`
- `Use Tracebook while debugging this incident, but do not capture anything unless the root cause is verified.`
- `Capture this verified settlement term as reusable domain knowledge with its source evidence.`
- `Record this idempotent-consumer approach as a reusable pattern, then run the required health check.`
- `Run a Deep Tracebook audit for the current project; keep findings as candidates for human review.`

工程工作开始前，Skill 依次读取外部根目录规则、健康状态、项目索引和项目状态，随后只
读取相关文档。任务结束后，它按照
[`SKILL.md`](plugins/tracebook/skills/tracebook/SKILL.md) 中的持久写入门禁处理。

## 日常工作流

以下是用于集成、诊断和其他需要可复现命令场景的确定性 runner 工作流。自然语言
Plugin 用法仍是主要入口。下面的示例假定 shell 位于业务仓库根目录，`SKILL_DIR`
指向已安装的 Tracebook Skill，并且已按前文设置 `TRACEBOOK_ROOT`。

### 解析

使用默认知识根目录时，可运行简短命令：

```text
python "$SKILL_DIR/scripts/tracebook_runner.py" resolve --cwd .
```

如需显式传入已配置的根目录：

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" resolve \
  --root "$TRACEBOOK_ROOT" \
  --cwd .
```

`resolve` 只在已配置的外部根目录中初始化或修复缺失的模板文件，注册标准化 Git 身份，
并返回 `root`、`project` 和有序的 `read_paths`。它不会搜索或导入另一个现有知识根目录。

### 捕获

把请求保存在业务仓库之外，例如系统临时目录：

```json
{
  "scope": "project",
  "kind": "business-rule",
  "category": "business-rules",
  "title": "Order retry eligibility",
  "body": "Only orders in the retryable state may re-enter fulfillment.",
  "evidence": [
    "src/order.py:L20-L38"
  ],
  "status": "Current",
  "write_intent": "durable",
  "content_kind": "knowledge"
}
```

然后运行：

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" capture \
  --root "$TRACEBOOK_ROOT" \
  --cwd . \
  --request "$REQUEST_FILE"
```

`Current` 知识必须包含证据列表。持久但明确尚未解决的条目可以使用 `Pending` 并提供
空证据列表；不能把 `Pending` 表述为已确认事实。证据格式 `src/order.py:L20-L38`
指向业务仓库中的依据，不会把源码复制到知识根目录。

### 检查捕获范围

集成必须保持以下精确数据依赖：

```text
capture.changed_paths -> repeated check --changed
capture.new_paths     -> repeated check --new-path
capture.health_scope  -> check --scope
check_type Deep       -> audit --scope with the same health_scope
```

例如，根据返回的每条路径重复相应参数，组装检查命令：

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" check \
  --root "$TRACEBOOK_ROOT" \
  --cwd . \
  --source-root . \
  --changed "$CHANGED_PATH_1" \
  --changed "$CHANGED_PATH_2" \
  --new-path "$NEW_PATH_1" \
  --scope "$HEALTH_SCOPE"
```

未跟随 capture 的直接 `check` 或 `audit` 调用在省略 `--scope` 时默认使用
`project`。但在 capture 之后，缺失或无效的 `health_scope` 是错误：应停止并报告响应
不完整，绝不能回退到 `project`。

### 执行要求的 Deep 审计

`check_type: Deep` 表示需要执行 Deep 审计，不表示审计已经完成。必须复用同一个 capture
`health_scope`：

```sh
python "$SKILL_DIR/scripts/tracebook_runner.py" audit \
  --root "$TRACEBOOK_ROOT" \
  --cwd . \
  --source-root . \
  --scope "$HEALTH_SCOPE"
```

审计报告包含候选发现。任何发现成为持久结论前，都必须由人对照证据进行确认。

### 结构化 JSON 字段

| 命令 | 返回字段 | 含义 |
| --- | --- | --- |
| `resolve` | `root`、`project`、`read_paths` | 已配置根目录、标准化项目记录和聚焦上下文路径 |
| `capture` | `changed_paths`、`new_paths`、`skipped`、`health_scope`、`event_id` | 知识事务结果，以及后续检查必须使用的范围 |
| `check` | `check_type`、`changed_paths`、`report` | 要求的健康级别、已持久化健康路径和 Markdown 报告 |
| `audit` | `changed_paths`、`report` | 已持久化 Deep 健康路径和 Markdown 审计报告 |

当 `event_id` 可用时，它标识幂等的捕获事件。`skipped: true` 表示 capture 没有产生新的
知识写入。消费者只能使用对应命令实际返回的字段。

## 知识目录与多项目隔离

默认本地根目录采用以下受治理布局：

```text
~/.tracebook/
├── 00-global/          # 共享规则、工作流和健康状态
├── 01-projects/        # 每个标准化项目 slug 一个隔离目录
├── 02-domain/          # 可复用业务知识
├── 03-patterns/        # 可复用工程知识
├── raw/                # 等待整理的原始材料
└── 99-archive/         # 历史材料
```

对于存在 `origin` 的仓库，Tracebook 将远端标准化为稳定的 Git 身份。同一远端的多个
clone 共享 `01-projects/<slug>` 下的同一个目录，不同仓库则获得不同项目记录。仅本地
仓库使用稳定的绝对路径回退身份。

## 链接策略

Markdown 链接是规范的输出格式。Tracebook 模板和 runner 写入会生成使用相对路径的
标准 Markdown 链接，使知识可以在不同 Markdown 工具间移植。

Wikilink 作为兼容输入，用于手工编辑的 Obsidian 知识。健康检查会同时审计 Markdown
链接和 Wikilink，但 Tracebook 不会生成 Wikilink。受治理的存储位置详见
[`目录规则`](plugins/tracebook/skills/tracebook/references/directory-rules.md)。

## 隐私与仓库边界

- 所有 Tracebook 知识和健康状态都留在已配置的本地外部根目录中（默认
  `~/.tracebook`）。
- Tracebook 仅在读取上下文或验证证据时读取业务文件，不会把源代码树复制进知识根目录。
- 初始化、capture、check 和 audit 只写外部根目录。安装和运行 Tracebook 对业务仓库
  保持零写入，也不会在那里创建项目级 `AGENTS.md`。
- 不需要也不提供 API key、cloud sync、MCP server、vector database、后台 daemon
  或 hook。
- Tracebook 不会自动发现、迁移、导入、复制或修改现有知识根目录。把
  `TRACEBOOK_ROOT` 指向某个位置是显式配置选择，而不是导入操作。

现有外部知识**不会被自动导入**。Tracebook 不会搜索另一个知识根目录，也不会把其中
内容合并到已配置的根目录。

## 健康检查与人工确认

| 级别 | 典型行为 |
| --- | --- |
| Local | 没有更高级别触发条件时，只读取并报告所选范围；不会写入 scope status 或日志，也不会重建全局聚合状态。 |
| Light | 在知识写入或知识文件变化后执行；检查链接、索引、来源、代码路径和状态。 |
| Regular | 由时间间隔或累计改动、页面、待确认项、缺失来源触发；增加孤立页面、漂移、重复和日志检查。 |
| Deep | 达到 Deep 阈值、核心知识页面过大或显式请求审计时执行；对照证据抽样检查持久结论。 |

详细策略见
[`健康检查规则`](plugins/tracebook/skills/tracebook/references/health-check-rules.md)。
`check` 结果可以要求 Deep 工作，但只有 `audit` 才会真正执行。Deep 发现只是潜在的事实、
来源、根因和状态问题，不会自动断言业务事实，必须人工复核。任何健康命令都不能修改
业务代码。

## 故障排查

- **Plugin 不可用：** 确认添加 marketplace 后再安装 `tracebook@tracebook`，然后启动
  新会话。在 Claude Code 中，`/reload-plugins` 可重新加载已安装插件。
- **项目解析失败：** 在 Git 仓库内运行，并通过 `--cwd` 传入该目录。当多个 clone
  应共享知识时，检查 `git remote get-url origin`。
- **知识出现在意外位置：** 检查启动 Agent 的环境中的 `TRACEBOOK_ROOT`。若未设置，
  根目录为 `~/.tracebook`。
- **Capture 被拒绝：** 检查 `write_intent: durable`、`content_kind: knowledge`、允许的
  scope/kind/category 组合，以及 `Current` 知识的证据。`Pending` 只用于持久但未解决的条目。
- **Capture 后的检查没有范围：** 将缺失或无效的 `health_scope` 视为不完整 runner
  响应，不能使用默认 project 范围重试。
- **现有笔记没有出现：** Tracebook 不会发现或导入现有知识根目录。除非另有明确批准的
  迁移流程，否则必须保持现有材料不变。
- **出现链接警告：** 生成的知识使用 Markdown 链接；手工 Wikilink 会作为兼容输入被
  审计，但不会由 Tracebook 生成。

## 开发与发布验证

在仓库 clone 中运行聚焦集成测试和完整测试套件：

```text
python -m unittest tests.test_runner_integration -v
python -m unittest discover -s tests -v
```

校验 Skill 包、编译 Python 源码并检查空白字符：

```text
python plugins/tracebook/skills/tracebook/scripts/validate_skill_package.py
python -m compileall -q plugins/tracebook/skills/tracebook/scripts tests
git diff --check
```

仓库 CI 会在 Ubuntu 和 Windows 上使用 Python 3.10 与 3.13 运行完整测试和上述静态
检查。Linux 会执行在缺少符号链接权限的 Windows 主机上可能跳过的符号链接边界用例。

记录或发布版本前，应对照当前 Codex 和 Claude Code CLI help 检查 marketplace 命令，
验证中英文指南并发布匹配的 Git tag。在 `v1.0.0` 存在之前，不要使用带 tag 的 Codex
安装命令。

## 当前限制

- 不迁移、不发现、也不自动导入现有知识根目录。
- 不提供 cloud sync、MCP server、vector database、daemon、hook 或后台服务。
- 不会自动确认业务陈述或 Deep 审计发现为真；证据和人工复核仍具有权威性。
- 不在业务仓库内安装，也不生成仓库配置。
- 发布 CI 配置为在 Ubuntu 和 Windows 上验证 Python 3.10 与 3.13；不声明该矩阵之外
  的环境兼容性。
- 生成输出使用 Markdown 链接。Wikilink 是审计和手工编辑的兼容输入，不是生成输出。
- Deep 候选提取会扫描所选 project、domain 或 pattern 范围内的每个活跃的持久
  Markdown 页面，并在每个二级标题知识条目内分别判断 evidence 或 Pending 状态。
  它仍是启发式检查：候选列表为空并不能证明知识正确。

## 参与贡献

改动应保持克制、有证据支持，并在 Skill、runner、测试和两种语言 README 之间保持一致。
提交 pull request 前，请运行上述开发与发布验证命令。新增 runtime 能力的改动必须更新
测试，且不能削弱外部根目录或人工复核边界。

## 许可证

Apache-2.0。详见 [LICENSE](LICENSE)。
