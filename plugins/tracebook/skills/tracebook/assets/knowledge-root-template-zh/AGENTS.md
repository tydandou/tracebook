# Tracebook 知识库

本目录是业务仓库之外的外部项目知识库，不是业务代码仓库。

## 用途

保存长期项目知识、业务规则、术语、代码路径映射、架构理解、故障结论、跨项目领域
知识与可复用工程模式。

## 必读顺序

处理业务项目任务时，按以下顺序读取：

1. 当前业务仓库的 `AGENTS.md`（如存在）。
2. 本文件。
3. 本根目录的 `index.md`——六个分区的导航入口。
4. `00-global/health/health-status.md`。
5. 解析器返回的当前项目路径，再读其 `index.md`。
6. 当前项目的 `project-status.md`。
7. 用任务原文执行 runner 的 `context-read-path`（即 Skill 的 Quick Start
   步骤 2）。若 `preflight` 返回 `blocked: true`，先执行其
   `required_action.argv`，再回到这一步。
8. 只读该命令返回的、与任务相关的权威页。

开场读取不是唯一一次检索。任务中途拿到新的文件路径、标识符或 `knowledge_id` 时，
可以再次检索；判断有用即可执行，无需额外许可。

默认不加载完整日志、原始素材、归档目录或 `99-archive`。这一约束针对知识库自身的
内容；用户为分析提供的日志属于任务输入，不受此限。

## 核心规则

- 写入知识前先读源码与上下文。
- 业务代码与长期知识分仓存放。
- 自动创建缺失的项目知识目录及其最小文档；**绝不**创建项目级 `AGENTS.md`。
- 只写经过验证、有证据支撑的结论。不确定的部分标记为 `Pending`。
- 创建 schema-v2 权威页并使用稳定的 `knowledge_id`；结论更新时修订既有 ID，
  不要为同一实体创建副本。
- 默认检索只返回 Current。仅在明确的历史问题或 `as-of` 重建时请求历史。
- 不得把原始对话记录或未经确认的 AI 推断当作事实存储。
- 业务代码仓库保持零写入。
- 保持目录、文件名、Markdown 链接、事件标记和生命周期字段不变。
- 新增内容默认使用中文；证据路径与机器字段保持原样。
- 维护入口索引，并在知识写入后执行本地检查。

## 规则文件

- `00-global/agent-workflow.md`
- `00-global/rules/reading-rules.md`
- `00-global/rules/directory-rules.md`
- `00-global/rules/auto-creation-rules.md`
- `00-global/rules/writing-rules.md`
- `00-global/rules/frontmatter-rules.md`
- `00-global/rules/source-attribution-rules.md`
- `00-global/rules/index-maintenance-rules.md`
- `00-global/rules/log-status-rules.md`
- `00-global/rules/knowledge-lifecycle-rules.md`
- `00-global/rules/synthesis-rules.md`
- `00-global/health/health-check-rules.md`

## 知识存放位置

按知识的复用范围选择目标，写入前先分类：

- `01-projects/{可读名称--id后缀}` —— 项目专属事实。目录名由项目名 slug 与稳定
  ID 短码组成，完整身份在该目录的 `project.json`。
- `02-domain` —— 跨项目可复用的业务知识（术语、规则、流程、场景）。
- `03-patterns` —— 跨项目可复用的工程知识（实践、设计模式、验证结论）。
- `04-systems` —— 多项目成员关系与有向服务关系。**不要手工创建**：由
  `system-create`、`system-bind-project`、`system-relate` 维护。
- `99-archive` —— Deprecated / Superseded 知识的归档，保留可追溯性。

本根目录的绝对路径：`{{knowledge_root}}`。

## 任务收尾报告

报告业务代码改动、知识库改动、健康检查结果、新增的长期知识，以及未确认的假设。
