# Tracebook v4.0.3 优化实施方案

Status: Implemented and verified for release on 2026-08-01. 本文记录基于 v4.0.2、
当前暂存改动和实际运行复现得到的限定范围。

## 1. 项目目标与判断边界

Tracebook 的目标是把可验证、可追溯的长期知识保存在业务仓库之外，并支持按项目、系统、
domain 和 pattern 有边界地读取。v4.0.3 不改变 schema-v2、registry JSON、CLI 参数或返回
JSON，不引入服务、数据库或新依赖；只修复生命周期完整性和跨项目历史读取中与该目标直接
冲突的问题。

判断按三层证据进行：README、Skill 与生命周期规则代表公开契约；源码和存储布局代表当前
实现；隔离复现、单元/集成测试与发布矩阵代表实际行为。三者不一致时，以最小兼容修复恢复
契约一致性，而不是把实现偶然行为直接写成新规则。

## 2. 当前候选优化审查

### 合理并保留

1. `superseded` 失败信息区分自引用、缺失目标和非 Current 目标，使调用方能直接修正请求。
2. 明确 collection 边界：project authority 的路径包含 kind；domain/pattern 的 authority 目录
   按 scope 扁平存放。因此 project replacement 必须同 kind，domain/pattern 可跨 kind。
3. 未获授权的方案不应覆盖已确认事实；它应作为独立 `pending` 实体，放弃后再转为
   `deprecated`。

### 不合理并移除

候选改动曾计划把每个普通 `revise` 的历史标题写成
`(superseded by vN)`。`## Current` 与 `## History` 已明确区分当前和历史内容，新增后缀没有增加
可检索语义，却把普通版本更新与正式生命周期 `status: superseded` 混为一谈，并扩大了解析器、
健康检查和兼容面。v4.0.3 保持原有 History 格式。

候选规则还曾把 revise 限定为“外部行为变化”，这会阻断证据文件移动、健康问题修复和证据
强度变化后的受治理更新。最终规则以“结论、证据、标题或生命周期事实发生实质变化”为门槛，
仅排除格式和临时调查笔记。

## 3. 必须修复的核心问题

### P0 — 跨项目历史来源损坏

`context_search.py` 构造 History `Candidate` 时使用了错误的位置参数。隔离复现中，显式读取
另一个项目的历史版本返回 `source_project.project_id: true`，项目 ID 被写进 name 字段。
这破坏了多项目/系统交叉读取的来源追溯。

修复：所有 History 来源字段使用命名参数；在直接 API 和真实 Runner 多项目流程中同时断言
历史版本的稳定 project ID 与 name。

### P0 — Superseded 可指向未确认或伪 authority

旧校验只拒绝 `deprecated` 和 `superseded`，因此 `pending` 可替代已确认事实；只有 `status`
字段的普通 Markdown 也可能被接受。非 Superseded 请求还可携带无语义的 replacement 指针。

修复：replacement 必须是同 collection、身份匹配的 schema-v2 authority，且 status 必须严格
为 `current`；其他生命周期状态禁止 replacement 指针。拒绝必须发生在事务提交前。

### P0 — Domain/pattern 写入与健康检查矛盾

capture 按扁平目录允许 domain/pattern 跨 kind successor，但健康检查用
`scope + project + type + knowledge_id` 查找 replacement，导致合法写入随后被报告为 missing。

修复：健康检查身份与真实路径保持一致：project 包含 kind；domain/pattern 忽略 kind。相同规则
同时用于重复 authority 与 replacement 检查，replacement 非 Current 时报告明确问题。

## 4. 验证与发布门槛

1. 生命周期单测覆盖 Current、Pending、Deprecated、自引用、缺失目标、跨 kind domain successor
   及非 Superseded 指针。
2. 多项目 Runner 端到端测试覆盖根初始化、项目注册、项目知识入库、版本迭代、system 成员与
   关系、当前读取、reference 读取、历史交叉读取和空项目隔离。
3. 执行完整 unittest、Skill 包校验、compileall、`git diff --check`，并在临时根执行独立的
   三项目/两系统 CLI 验收。
4. 发布文件统一升级为 4.0.3；只有全部验证通过后才允许提交、推送、创建 `v4.0.3` tag 和
   GitHub Release。发布后验证远端 commit、tag、Release 和 CI。

实际结果：完整 unittest 296 项通过，9 项仅因 Windows 无符号链接特权跳过；Skill 包校验、
compileall 与 `git diff --check` 通过。独立 CLI 验收完成三项目、两系统、两条有向关系，覆盖
project/domain/pattern 入库、版本迭代、Pending 隔离、reference 过滤、跨项目 Current/History
来源、系统成员边界、三类健康检查、Deep audit，结束时待恢复事务为 0。

## 5. 回滚边界

代码回滚限于 `knowledge_entity.py`、`context_search.py`、`check_knowledge.py` 及对应测试和文档。
未修改 schema、registry、既有知识页或业务仓库；发布前可按单个修复提交差异回退。发布后如需
撤销，应发布后续补丁版本，不移动已公开 tag。
