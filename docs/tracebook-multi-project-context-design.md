# Tracebook Multi-Project Context Design

Status: Implemented (read model)

## 中文摘要

一个会话始终有唯一的当前目标项目，默认只读取该项目；用户明确点名其他服务，或选择已登记的微服务系统时，才按稳定 `project_id` 扩展读取范围。`preflight` 可在新目录尚未创建前无写入执行，避免模型在加载知识前猜测“是否相关”。`04-systems` 仅记录项目成员和有向依赖关系，用于限定读取集合，不合并项目身份或项目知识。跨项目结果保留来源项目；`reference` 视图只返回架构、模块和决策，适用于明确指定来源的新项目脚手架。

## Goal

Support normal multi-repository and microservice development without making a
shared knowledge root an implicit all-project search index. A session has one
active target project; other projects enter the context only through an
explicit project selection or registered system.

## Decisions

- `preflight` is read-only and accepts a not-yet-created target path. It avoids
  the previous circular choice where an agent had to decide relevance before
  loading any context, while preventing exploratory requests from registering
  empty projects.
- `resolve` remains the activation operation. It initializes a root when
  appropriate and registers the target project once development starts.
- `project-search` resolves human names or known signals to stable
  `project_id` values. Names are never an authority for cross-project reads.
- `04-systems` is a many-to-many metadata graph. A system has a stable
  `system_id`, named members, and directed relationships such as `api` or
  `event`. It selects a bounded read set and never merges project identity or
  project knowledge directories.
- `context --project-id` and `context --system-id` are opt-in expansions. The
  response identifies the source project for every project-scoped item.
- `context-read` retrieves explicitly selected registered projects without a
  target `cwd`; it is the required read path for a not-yet-created project's
  reference-architecture research.
- `context --profile reference` permits only `architecture`, `module`, and
  `decision` entries from selected projects. It is intended for an explicitly
  named architecture source when scaffolding a new project.

## Operational Examples

Opening `payment-service` and asking for `order-service` event fields:

1. Resolve `payment-service` as the active project.
2. Search and select `order-service` by stable ID, or select the registered
   commerce system.
3. Query only those records; returned facts retain the `order-service` source.
4. Do not write merely because the fact was read. A later durable conclusion
   is still classified by its owning project, domain, or pattern scope.

## Boundaries

This change deliberately adds a read-selection graph, not a new capture or
health scope. Existing project/domain/pattern capture semantics and health
contracts remain backward-compatible. A future system-owned authority-page
scope must be designed together with lifecycle, health, source attribution,
and conflict rules; it must not be introduced by copying a fact into every
member project.
