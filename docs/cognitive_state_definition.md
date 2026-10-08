# Cognitive State v0.3：设计草案

更新：2026-10-03。已按用户授权提供独立的 v0.3 最小运行器并恢复可靠性预检；见 [实现与第三轮协议](v03_implementation_and_cycle3.md)。旧入口、旧 Schema 及历史实验仍使用 v0.2；[原定义](versions/cognitive_state_v0.2.md)已归档。执行 prompt v0.3 与本状态版本是不同的版本轴。

> A task-conditioned, externalized representation of an agent's current cognitive status that preserves information necessary for future task execution.

保留核心定义。v0.3 将“必要”限定为：在明确的未来任务延续范围、公共工具契约和恢复成本下，足以支持继续决策与执行。评价对象包含状态的更新过程，不要求输出文本相同。

CS 不是 raw conversation history、model hidden state、KV cache 或 permanent memory。普通摘要也是竞争性表示；G/W/F 标签、JSON 格式或命名本身不能证明差异。要检验的机制是：状态能否持续保留有效证据、实际执行阶段和未完成义务，并在变化后正确更新。

## G/W/F 的职责

保留 `CS = (G, W, F)`。逻辑条目使用短 ID，跨字段引用同一内容；只在影响决策时保留元数据。允许空列表、缺省可选字段和没有候选行动。

| 分区 | 核心内容 | 约束 |
|---|---|---|
| G：Goal | 当前目标、可观察成功标准、硬约束、偏好，以及要求来源 | 执行方法不能自行升级为用户要求 |
| W：Working State | 关键判断及依据、重要操作的实际阶段、当前资源 | 推断和假设可区分；计划不能证明操作已发生 |
| F：Frontier | 未完成义务、会改变选择的未决问题，可选候选行动 | 不强制生成调查；候选行动不能覆盖 G/W |

以下是语义约定。独立运行器的 minimal-2 实现采用 [v0.3 编码 Schema](schemas/cognitive_state_v0.3r2.schema.json) 和额外的来源/引用/预算检查；旧 v0.2 parser 不读取该格式。结构通过不保证语义充分。

## Goal State (G)

- `objective`：当前总体目标。
- `requirements`：带 `id`、`text`、`source_refs` 的可观察成功标准。
- `constraints` / `preferences`：同样带来源的硬边界与软偏好。
- `revision`：目标修订标识，用于检查旧计划是否仍适用。

Goal 不保存模型猜测的额外验收要求。例如用户要求完成校准，模型不得自行追加“必须付费读 signed ledger”。要求是否已满足，由 W 中的实际观测支持。

目标来源的权限和适用范围由任务接口规定。工具输出可报告事实，但不能自行把用户的 private 要求改成 public。新要求只替换其适用范围内的旧要求；没有冲突的约束继续有效。无法解决的冲突须保留，不能一律让最新文本获胜。

## World Model / Working State (W)

### 关键判断

`claims` 的每项包含 `id`、`text`、`basis`、`source_refs`。`basis` 区分 `observed`（工具观测）、`reported`（来源陈述）、`inferred`（推断）、`assumed`（暂用前提）。推断另用 `depends_on` 引用依据条目。

这些标签说明依据类型，不保证内容绝对正确。假设不能因为多次重写而变成 observed。来源的对象、版本和适用范围决定证据是否仍有效。

必要时增加可选字段：

- `valid_when`：适用的对象、版本或公开条件。
- `recheck_when`：什么新事件会使重新确认有必要；不得编造失效事件。
- `standing`：默认 `active`；必要时为 `superseded`、`refuted`、`conflicted`。
- `superseded_by`：替代它的条目 ID。

v0.2 的 facts/beliefs/assumptions 区别保留为依据类型，不要求重复写入三个文本列表。主观 confidence 不再必填；只有在实验明确使用且评价其意义时才保留，不能视为校准概率。

“有证据”“尚未知”“已推翻”“与当前选择无关”应区分；最后一种通常直接不进入活动状态。

### 操作与资源

下一轮已冻结 [v0.3.1 对象与阶段规范](operation_lifecycle_v0.3.1.md)：分别记录 submission、job、sync_operation，明确请求返回不等于异步作业成功。对应 [Schema](schemas/cognitive_state_v0.3.1.schema.json) 是待实现规范；以下无 kind 的操作编码仍描述 cycle3 minimal-2，不能混用或追溯重算旧结果。

`operations` 记录仍影响未来行动的重要操作：`id`、`operation`、必要的对象或参数、`phase`、`source_refs`，以及必要的异步 handle。

阶段词汇包括 `planned`、`issued`、`accepted`、`completed`、`verified`、`failed`、`cancelled`、`unknown`。这不是所有工具必须依次经过的统一流水线；每个公共工具契约规定适用阶段及支持转换的回执。accepted 不自动等于任务完成，completed 也不自动满足独立验证要求。

操作超时或失败可能留下部分或未知副作用。没有充分执行证据时保留 unknown，按公共接口的检查或幂等能力处理，不能直接假定未执行并重复提交。

`resources` 保存影响决策的额度、时间或权限及其作用范围和来源。可信运行时已提供的实时值，无需提取模型重复猜测；各条件获得相同接口并计入输入成本。历史 credit 余额不能默认成为新 checkpoint 的余额。

## Frontier State (F)

`obligations` 表示尚未满足的义务，使用 `requirement_ref` 指向 G 的要求，必要时通过 `depends_on` 引用 W。`open_questions` 只保存答案可能改变行动选择、可行性或验收判断的问题；每项说明 `blocks` 哪个义务和 `decision_relevance`，必要时列出查询与已知成本。

新建信息缺口前先检查现有证据。问题已经解决且没有发生失效事件时，不应只因“再确认更稳妥”而重开。明确要求的独立验证仍是合法义务；高风险任务的复查规则由任务契约预先规定。

`candidate_action` 可省略。若保存，包含具体工具动作、`requires`（活动条目 ID）、`obligation_ref`、`goal_revision`；必要时增加已知成本。它是可重新计算的计划，执行前检查前提、当前资源和目标版本，不能覆盖 G/W。

允许直接执行、等待异步结果、需要补充信息、公开证据支持结束或当前受阻。空 `open_questions` 不等于完成；任务已完成时可不保存任何候选行动，执行器依据 G/W 和共同工具契约作出 finish 判断。

## 更新与停止

更新过程为 `CS_(t+1) = U(CS_t, a_t, o_(t+1), ΔG_(t+1))`。输入只包含上次实际保留状态及新公开材料；提取器不得读取隐藏评分、未来测试问题或已丢弃历史。

新增、修正和删除判断后，更新依赖它们的义务和计划。完成要求 G 中有效成功标准与 W 的公开执行证据一致；没有问题可问或已经写出计划都不是完成证据。详见[更新协议](state_update_protocol_v0.3.md)。

## 活动编码与研究记录

1. **活动状态**：执行器实际读取的 G/W/F，包含理解关键判断所需的内容。
2. **来源及变更记录**：研究复核用的来源定位、变更理由、原始响应；默认不提供给执行器。

`source_refs` 默认仅用于审计，不能把一个不含必要内容的 ID 算成已保存信息。允许按 ID 检索时，应设为明确的检索条件，计算访问、Token 和延迟，不能免费恢复历史。共享工具定义、当前用户消息及运行时资源也属于真实输入。

压缩时删除无活跃用途的旧事件；仍有依赖、可能导致重复执行或旧要求复活时，保留简短失效标记。研究记录可以增长，但不能因此宣称整个系统存储恒定。空列表和可选元数据是否省略，由未来编码协议规定，不能静默改变实验输入。

## 审阅与结论范围

[示例与事件表](examples/cognitive_state_v0.3/README.md)给出来源完整的设计例子。它不是模型成绩或人审 gold，也没有证明该表示最小。

v0.3 针对已观察问题提出机制假说，尚未验证效果。提取可靠性、内容充分性、更新正确性与执行器表现分别评价；参见[研究问题](research_question.md)、[实验设计](experiment_design.md)及[修订说明](design_revision_v0.3.md)。

## v0.3.1 实现状态

第四轮独立执行版本 `cycle4-execution-v2` 已实现并冻结，117 项离线测试通过，尚无新模型结果。见[实现说明](cycle4_execution_v2.md)。本文中 minimal-2 的旧编码说明继续用于理解 cycle3，新的 kind/phase 编码以冻结 v0.3.1 Schema 为准。
