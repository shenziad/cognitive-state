# Hypotheses

## Hypothesis 1

Cognitive State can replace large portions of historical context while maintaining task-level performance.

**检验思路**：在相同未来任务上比较 Cognitive State 与 Full Context 的任务成功率和最终目标完成度，并报告 Token Reduction。

## Hypothesis 2

Compared with normal summarization, Cognitive State preserves more task-relevant information.

**检验思路**：在相同或匹配的输入 Token 预算下比较 Cognitive State 与 Summary 的后续任务表现，分析丢失的目标、约束、信念与下一步信息。

## Hypothesis 3

The optimal state should minimize representation size while maintaining future behavioral capability.

**检验思路**：改变状态长度预算，绘制 Token 用量与任务表现的关系，并在预先设定的可接受性能损失范围内寻找最小表示。

这些是假设，不是当前已验证的结论。

## v0.3 的检验边界与机制问题（2026-10-03）

H1–H3 原文保留。第二轮尚未确认它们；实验现已暂停，下面是后续设计要求。

- H1：预先限定未来任务延续范围与公共恢复接口；同时看相对 Full 的变化和独立标准下的绝对完成能力。两条件均失败不算等价证明。
- H2：使用有竞争力的任务导向摘要，提供相同公开材料及可比较的修复预算。相同 UTF-8 bytes 不等于相同 Token；报告实际观测预算。
- H3：预先规定可接受性能损失与绝对质量门槛，再找可行的最小状态。格式失败与语义容量不足分开；全部失败仍进入端到端分母及成本。

新增的探索性机制预测尚未验证，也不取代 H1–H3：

1. 来源和有效性规则可能减少无依据验收条件、已解决问题的无故重开。
2. 明确操作阶段可能减少把计划当完成、重复提交以及丢失异步进度。
3. 依赖失效和目标修订规则可能改善证据被推翻或目标改变后的行为连续性。
4. 候选计划既可能减少重新规划，也可能固化错误，因此其净收益是开放问题，需要有/无计划的匹配比较。

这些机制应在公共接口、格式可靠性和预算受控后分别检验；语义消融须检查跨字段残留。详细进入条件见 [实验设计](experiment_design.md)。
