# 四条件回归：来源与行为关联

56 个组合全部完成。Full Context、Summary、CS v0.2、CS v0.3.1 分别成功 14/14、14/14、12/14、14/14；42 份压缩表示全部首次编码有效。来源审阅先于当前行为揭示，条件未盲化，研究助手审阅不代表独立人审 gold。逐案例公开状态见 [review.json](review.json)，行为、预算和证据 hash 见 [semantic_behavior_notes.json](semantic_behavior_notes.json)。

## 两次失败：已经完成目标后增加独立查证

`cont2_completed_a/b` 的旧版 CS 正确保存了已校准对象和剩余对象，随后却要求校准后再查询 `current/calibration_ledger`。校准花 2 credits，ledger 查询也花 2，当前预算只有 3。来源审阅发现了无依据重开/额外验证和资源依赖未传播的问题。

实际轨迹均为剩余校准成功→付费 ledger 查询返回预算耗尽→finish completed。最终校准目标达到，评分记录名义支出 4、预算 3、一次约束违规，因此任务失败。失败原因不是对象身份丢失、重复校准或 API 中断，也不能通过只看 Final Goal Completion=1 将其判为成功。

## 来源错误也可能行为成功

- Summary 的 `cont2_belief_b` 开头将 incident 写成 resolved，但公开来源只确认了诊断，明确没有应用修复。后续待办仍正确，执行器实际应用修复并成功。
- v0.2 的 `cont2_goal_b` 在最新授权范围已明确后又要求查询 owner scope。执行器照做，但多出的 1 credit 查询仍在预算内，最终成功。任务成功率没有反映这项冗余行为。

具体来源错误表示数：Summary 1/14、v0.2 3/14、v0.3.1 0/14；有歧义表示分别 1、5、2。0 个具体错误不等同于证明状态绝对正确，尤其审阅不是独立 gold。

## 成本与解释

| 条件 | 全部策略 Tokens | 成功 |
|---|---:|---:|
| Full Context | 115,569 | 14/14 |
| Summary | 93,868 | 14/14 |
| CS v0.2 | 109,928 | 12/14 |
| CS v0.3.1 | 121,623 | 14/14 |

165 次响应、440,988 Tokens，无未知用量。v0.3.1 本阶段追平 Full/Summary 的行为成功数，成本仍高于两者；本阶段 v0.2 比 Full 少用 Tokens，但成绩更低，不能宣称同等表现的节省。14 个已知开发实例、单次重复及整套提示/Schema 改动，不能支持泛化或单字段因果结论。
