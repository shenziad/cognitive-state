# 冻结坏 CS 的匹配干预：探索性单案例诊断

原始运行：`D:\Develop\Cognitive State Representation for Long-Horizon LLM Agents\cognitive-state\results\raw\exp001\frontier_case_v02_20261002`

**这是观察到失败后选择的单案例，5 个干预版本各执行一次。结果不能用于确认研究假设，也不并入主实验的独立任务数。**

## 核验后的结果

| 版本 | 实际动作顺序 | 成功 | Credits / 预算 | API Tokens |
|---|---|---:|---:|---:|
| 原始坏 CS | ledger → consume_Z → blocked | 否 | 4 / 3 | 2980 |
| 只删 W 中 ledger 必要性假设 | ledger → consume_Z → blocked | 否 | 4 / 3 | 2941 |
| 只将 F.next_action 置 unknown | catalog → ledger → consume_Z → blocked | 否 | 4 / 3 | 4428 |
| 同时做上述两项 | ledger → consume_Z → blocked | 否 | 4 / 3 | 2827 |
| 仅改为来源支持的 consume_Z | ledger → consume_Z → blocked | 否 | 4 / 3 | 2893 |

全部 5 个版本失败；16 次请求均取得响应，无 API/格式错误。Provider 报告 input=15822、output=247，合计 **16,069 Tokens**。这些是执行器调用成本，原始提取没有重新调用或再次计费。

ledger 查询花 2 credits，剩余 1；随后 consume_Z 需要 2，因此被预算拒绝。所有版本最终都声明 blocked。没有版本实际完成消费或达成完整目标，因而“目标达成后查询数为 0”不能解释为停机策略正确。

## 这个结果支持到什么程度

1. 本例中，单独删除 ledger 必要性假设、屏蔽 next_action，以及二者组合，都没有消除先付费重查的行为。
2. 明确写入来源支持的 `Execute consume_Z` 后，执行器仍先查询 ledger。这说明正确 next_action 在这份包含冲突的状态中没有支配首次付费行动。
3. 这不能归因于 F 单独失效：正修复版本仍保留 W 的“ledger 必须先查”假设；所有版本都保留 F 中“确定身份”的 focus、ledger 身份缺口和 readiness 缺口，以及 W 的确认相关 belief。`both` 也不是完整冲突清除。
4. 原始 facts 已记录 pearl 接受且通知待消费。因此失败不能简单解释为历史接受信息被压缩丢失。更可靠的描述是：**保存正确事实的同时，状态中仍存在使执行器付费重查的确认需求。** 这不是唯一机制的因果证明。

## 来源和输入公平性

- 原始 artifact、source config、task、environment、executor prompt 和 1921-byte CS 的 SHA 锁定与复制件均一致。
- 原始 CS SHA256：`1558901a1c55cde53f5c97c5853abd47da5bcd1b5081e10ab9bdd344c07db17d`。
- 5 个 diff 仅修改预声明的 `world.assumptions` 与/或 `frontier.next_action`；Goal、facts、beliefs 和 F 的其它字段保持原字符串。
- 正修复操作名来自 h02，pearl 接受及待消费通知来自 h04；未添加未来回执、隐藏状态答案或 rubric。
- 全版本使用相同冻结 v0.3 prompt、模型配置与原始 fixture，模型只收到对应 CS 和共同公共工具。
- 逐调用 messages/response 与账本一致；16 个请求唯一计费，轨迹、观测、世界状态、评分及诊断独立重放一致。详见 `analysis.json`。

## 模拟接口的限制

原始公共操作描述仅说“Consume the pearl broker notice; requires an accepted pearl reservation”，默认回执只有 `{"applied":"consume_Z"}`；它没有明确报告 fulfilled。这可能鼓励额外确认，应在新的共同接口版本中校准，并给所有表示条件相同契约和真实动作回执。

本诊断 5 条轨迹均在真正消费之前就耗尽预算，不能据此确认回执语义造成首次 ledger 查询，也没有测试更明确回执是否改善行为。上一阶段 Full 在正确消费后继续查询 ledger 的失败，属于另一个需要分开审查的停机/接口问题。

## 后续可检验的问题

先在独立版本中校准消费操作的公共成功契约，再逐项检查残留的 identity/readiness 需求是否有历史依据。若开展完整一致性修复，它是新的来源支持规划条件，不能当作本例的单字段消融。保持所有旧结果，使用新 config 和重复观测；不根据这 5 次执行下宽泛结论。
