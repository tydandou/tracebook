# Tracebook v4.0.2 优化实施方案

Status: Implemented and verified for release on 2026-07-30. 本文记录 v4.0.2 的限定优化范围；
在代码与验证完成前，公开安装版本、插件 manifest、Git tag 和 GitHub Release 仍保持
v4.0.1，不提前执行发布操作。

## 1. 目标、范围与禁区

本轮处理当前暂存优化中已经由源码和隔离复现确认的问题：

1. schema-v2 实体改名后，入口索引必须只保留一个指向该实体的当前标题条目。
2. 系统注册命令必须维护可浏览的系统总索引、成员和有向关系页面。
3. 系统持久化遇到可预见的非法目标时必须在首次权威写入前失败；多文件替换中断时必须可诊断、可前滚。
4. 既有系统即使成员或关系已存在，也必须能通过幂等命令补齐旧根缺失的生成导航。
5. 项目显示名更新后，引用该项目的系统页面必须同步，不保留过期显示名。
6. 健康检查只把 schema-v2 权威实体的重复索引链接报告为实体完整性问题。
7. Skill、知识根模板和 CHANGELOG 必须与实际文件、版本边界和可选 `AGENTS.md` 契约一致。

不做：知识 Schema、registry JSON 版本、CLI 参数或返回 JSON 变更；数据库、网络服务、daemon、
新生产依赖；发布 manifest、安装命令、Git tag、Commit、Push 或 Release；与本轮问题无关的重构。

## 2. O1 — 知识实体索引按稳定链接收敛

### 已确认问题

旧实现按完整 `- [title](link)` 文本判断是否存在。`revise` 改标题后，同一 authority page 会追加
新条目，旧标题继续留在索引中；常规 duplicate-page 检查又有意跳过 `index.md`，因此无法发现。

### 方案

- 以规范实体链接作为条目身份，标题只作为可变展示字段。
- 写入实体时更新第一个同链接条目，并清理该链接的其余历史重复项。
- capture 继续通过既有事务一次提交 authority、index、status、log 和项目快照。
- health check 对重复链接做补充检测，但仅在链接目标可解析为当前扫描树中的 schema-v2 权威页时报告。

### 验收

- 多次改标题后索引只有一个条目且标题为 Current 标题。
- 完全相同的 capture 重放保持索引字节不变。
- 旧重复条目在下一次该实体写入时收敛。
- 普通 Markdown 页面在手写索引中被重复引用时不产生 schema-v2 实体误报。

## 3. O2 — 系统导航的预校验与可恢复事务

### 已确认问题

当前 `_persist` 先写 `system.json`，再读取/写入系统页和总索引。若后续目标是目录、symlink 或
不可解析文件，命令会返回失败，但 authority config 已经改变。隔离复现中 `system-bind-project`
返回 `INVALID_SYSTEM_STATE`，新成员仍出现在 `system.json`。

### 方案

1. 系统元数据操作统一按 `registry -> systems-registry` 的固定锁顺序执行；项目注册操作已使用
   `registry`，因此恢复只需取得该事务 scope 即可阻止并发元数据写入。
2. 在首次写入前读取并验证本次涉及的 system config、系统页、系统 registry 和系统总索引：
   仅允许不存在或普通文件，拒绝 symlink、目录和其他非普通条目。
3. 先计算所有目标的新内容，仅把发生变化的目标交给 `commit_updates`；registry 作为最终目标。
4. 可预见校验错误必须零写入。若进程在替换阶段崩溃，沿用现有 intent/manifest 协议诊断并安全前滚，
   不宣称多个文件在文件系统层面具有瞬时全局原子性。
5. 幂等 bind/relate 不再直接绕过导航维护：authority 未变时只提交实际缺失或过期的派生页面。
6. 元数据命令取得 `registry` 锁后，若同 scope 存在未完成事务则返回
   `TRANSACTION_RECOVERY_REQUIRED`；必须先用 `transactions` 诊断并显式执行
   `recover-transactions`，避免后续写入把原本可恢复的事务变为 blocked。

### 兼容性与回滚

- CLI、JSON、system registry/config schema、目录名和 Markdown 生成标记不变。
- 元数据命令比原来多持有一个低频 registry 锁；代价是系统与项目元数据操作串行，知识 capture 与
  context 的项目级并行不受影响。
- 回滚边界为 `system_registry.py`、`project_registry.py`、相关 tests 和本文；事务协议本身不变。

### 验收

- 非普通总索引或系统页导致结构化错误，system config、registry 和其他页面字节均不变。
- 模拟替换中断后，`transactions` 可诊断且 `recover-transactions` 可前滚。
- 替换中断后直接执行另一条系统或项目元数据命令时，新命令零写入并要求先恢复；恢复后重试可同时保留前后两次操作。
- 重复已有 bind/relate 可修复旧页面缺失的生成块；页面已正确时保持字节不变。
- 手写内容继续保留，生成块不重复，稳定 ID 不重复。

## 4. O3 — 项目改名同步系统页面

### 已确认问题

系统页在系统命令执行时从项目 registry 复制显示名；`project-update --name` 只刷新项目配置、项目页
和项目总索引，已绑定系统继续显示旧名。

### 方案

- 项目改名在同一 `registry -> systems-registry` 锁顺序内，预先计算项目配置、项目页、项目总索引及
  所有受影响系统页。
- 使用一个 registry-scope 可恢复事务提交实际变化目标；项目 location-only 更新不重写系统页面。
- 系统页仍以 `project_id` 为身份，以当前项目名为展示，不移动任何项目或系统目录。

### 验收

- 改名后所有包含该成员的系统页显示新名称，成员 ID 与关系方向不变。
- 非成员系统页面不变化；location-only 更新不触发系统导航写入。
- 任一受影响页面在预校验阶段非法时，项目配置与所有导航均保持原字节。

## 5. O4 — 文档、健康检查与版本边界

### 方案

- `check` 解析重复 Markdown 链接的实际目标，并复用 schema-v2 frontmatter 判定，避免普通文档误报。
- `SKILL.md` 和双语知识根 `AGENTS.md` 恢复“仓库 `AGENTS.md` 存在时读取”；缺失不是错误。
- 新检索时机规则、日志 write-gate 表述、双语模板更新以及本轮修复全部归入 `Unreleased`，明确
  release target 为 v4.0.2；不得把 v4.0.1 tag 中不存在的文件记入 v4.0.1。
- 修正文档中“实体路径总是由 scope、kind、knowledge_id 推导”的过度表述：project scope 包含
  kind，domain/pattern 当前由 scope 与 knowledge_id 定位。
- 公开 manifest、README 稳定安装 tag 在正式发布步骤前保持 v4.0.1。

## 6. 测试与完成标准

1. 新增失败零写入、事务中断恢复、旧根幂等重建、项目改名同步、普通 Markdown 重复链接不误报测试。
2. 保留并通过索引改名、重复收敛、系统成员/关系、手写内容保护和并发/事务既有测试。
3. 执行 `python -m unittest discover -v`；Windows 无 symlink 权限的既有跳过项单独报告。
4. 执行 Skill 包校验、`compileall`、`git diff --check` 和最终 Git diff 审查。
5. 不修改用户任务范围外文件，不 Commit、Push、打 tag 或发布。

## 7. 实施顺序

| 顺序 | 垂直切片 | 可独立验证与回退范围 |
|---|---|---|
| 1 | 本方案文档 | `docs/tracebook-v4.0.2-optimization-plan.md` |
| 2 | 系统持久化事务与幂等导航重建 | `system_registry.py`、系统测试 |
| 3 | 项目改名跨系统同步 | `project_registry.py`、项目/系统测试 |
| 4 | 健康检查收窄与指令/版本文档修正 | `check_knowledge.py`、Skill/templates/CHANGELOG、测试 |
| 5 | 全量验证、Diff 审查与 Tracebook write gate | 测试和外部知识检查；不扩大业务改动 |
