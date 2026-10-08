# v0.3.1：操作、异步作业与目标完成

2026-10-03。这是下一轮冻结的语义规范，尚未接入模型运行器。保留 G/W/F，只细化 W 中操作记录的对象范围。cycle3 的代码、门槛、原始输出及评分均不追溯修改。

## 1. 四个不同的判断

| 对象 | 判断 | 所需依据 | 不能推出 |
|---|---|---|---|
| 提交请求 submission | 请求已返回 `phase=completed`，结果 `outcome=accepted` | 公共契约认可的接受回执，绑定此次请求/尝试及作业 ID | 异步作业已经成功 |
| 异步作业 job | `phase=accepted` 或 `running` | 同一作业的接受/进度回执 | 已达到终态 |
| 异步作业 job | `phase=succeeded` / `failed` / `cancelled` | 同一作业、当前版本的终态回执 | 其他对象完成、独立验收通过、用户全部目标满足 |
| 当前目标 Goal | 可以 `finish completed` | 所有当前要求的对象、效果和明确要求的验收均有依据 | 仅凭接口调用成功即可完成 |

`submission.completed` 只表示这次提交交互已得到明确终结的响应，不表示业务成功；必须同时保存 outcome。接受与拒绝都是已返回响应，分别写 accepted/rejected。HTTP 状态码的含义取决于公开契约，不能把任意 2xx 自行当作业务完成。

同步操作使用独立的 `kind=sync_operation`；公共成功回执可支持 `phase=succeeded`，不强行建立异步作业。

## 2. 最小编码

仍放在 `world.operations` 中，不另加顶层状态。

共同必填：`id`（活动条目 ID）、`kind`、`entity_id`（对象身份）、`operation`、`phase`、`source_refs`。身份与操作名不同：同一 submit 操作可以产生多个尝试；同名作业不能凭名称合并。只有影响续做时才保留已结束请求。

| kind | phase 枚举 | 附加字段 |
|---|---|---|
| submission | planned, issued, completed, unknown | outcome 为 accepted/rejected/unknown；completed 要求 accepted 或 rejected；接受时必须有 job_ref |
| job | accepted, running, succeeded, failed, cancelled, unknown | 可选 handle；异步真实对象 ID 已知时 entity_id 使用该 ID |
| sync_operation | planned, issued, succeeded, failed, cancelled, unknown | 可选 target |

`job_ref` 指向仍保留的 job 活动条目 ID；source_refs 指向审计来源，不能替代实际内容。job 的 `operation` 表示创建/执行该作业的公开操作名，并非要求再次执行该操作。

不知道服务器是否接受时，以本地 attempt ID 标识 submission、phase=unknown、outcome=unknown；不能虚构 job ID。若公开事件已给出 job ID，可建立对应 job。一个请求超时不证明没有副作用，也不证明作业终止。

### 接受回执之后

```json
[
  {"id":"s1","kind":"submission","entity_id":"attempt-1","operation":"submit_job","phase":"completed","outcome":"accepted","job_ref":"j1","source_refs":["e1"]},
  {"id":"j1","kind":"job","entity_id":"job-17","operation":"submit_job","phase":"accepted","handle":"job-17","source_refs":["e1"]}
]
```

这里两条记录并不矛盾。Frontier 仍保留取得 job-17 成功结果的义务；若用户只要求“成功提交”，且没有其他验收条件，则该用户目标可能已满足。**用户要求“提交”和要求“完成作业”必须区别评价。**

### 同一作业的成功回执之后

收到 e2 明确报告 job-17 succeeded，更新 j1.phase=succeeded、来源包含 e2；s1 不必重写。若用户要求独立验证，验证前仍不能完成目标。验证作为单独的 sync_operation（例如 validate_result）及其效果 claim，不用 job.phase=verified 混合两条生命周期。

完整可审阅例子与反例见 [conformance_cases.json](examples/cognitive_state_v0.3.1/conformance_cases.json)。该文件是规范测试，不是模型成绩或参考状态条件。

## 3. 证据与更新规则

1. 转换由公开契约及实际回执支持；工具目录描述 future effects 不构成执行证据。自然语言状态不能因为引用了一个 tool ID 就自动获准升级。
2. 匹配 entity_id、attempt、目标/结果版本；另一个作业的成功不更新本作业。重试使用同一幂等键是否指向同一作业，只由公开回执确定。
3. `accepted → running → succeeded/failed/cancelled` 是允许的常见变化，不是必经顺序；直接终态可由明确回执支持。cancel 请求已接受不等于 job 已 cancelled。
4. 有公开单调序号/版本时，迟到的旧回执不覆盖更新终态。没有可靠先后顺序而回执冲突时保留冲突和必要证据，不凭接收时间强行确定最终状态。
5. 作业终态不证明输出满足所有业务要求。保存仍相关的结果效果、版本与验收证据；新目标或结果变更可能重新产生义务，但不抹去已发生的操作。
6. 目标若依赖测量，G 保留用户规则，W 保留测量依据，F 的候选行动引用相关活动证据。不能把测量结论的来源伪装成用户要求。依赖遗漏与悬空引用分开记录。
7. 继承来源时保持 user/runtime/contract/observation 的类别，不能因旧条目被放在 constraints 中，就将其中工具来源提升为用户目标权威。旧来源 ID 不授予读取已删除历史的权限。

## 4. 校验分层

- **编码有效性**：JSON、字段类型、枚举、必填字段、ID 唯一、活动引用可解析、kind 与 phase 兼容、字节预算。可给最多一次已记录修复；不填造事实。
- **内容诊断**：回执是否真的支持阶段、对象是否匹配、依赖是否完整、是否虚构要求、是否错误关闭义务。下一轮离线评分，不把隐藏答案或语义标注反馈给生成器，不作为选择成功样本的门槛。
- **行为评价**：错误重提、错误完成、工具/资源违约、最终目标完成。无论表示是否合法，均保留所有分配组合的分母。

结构性检查只能证明编码约束，不能证明自然语言被正确理解。公共环境照常拒绝非法操作；模型由拒绝回执继续行动属于已记录的执行过程。

## 5. 对上一轮反例的解释

cycle3 的 untyped `submit_silver / phase=completed` 没有明确对象范围，不能区分“请求返回”与“作业完成”。其 claims 保留 done=false，轨迹也正确，因此应记录为**旧编码下缺乏明确范围的阶段升级**，不能直接称作“模型虚构整个作业成功”。旧轮按当时冻结规则停止的事实保留；新轮不重新判旧轮通过。

下一轮采用新编码消除歧义，并将确实无依据的阶段提升作为可测语义错误报告。只有给状态增加 kind 标签，尚不能证明它改善行为或长期更新。
