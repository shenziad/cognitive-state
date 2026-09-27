# Cognitive State v0.2

> A task-conditioned, externalized representation of an agent's current cognitive status that preserves information necessary for future task execution.

Cognitive State 是与任务相关、可外部保存的 Agent 当前认知状态表示。它的判据是能否支持未来行动，而非复述过去发生的文字。

它**不是** raw conversation history、普通 summary、model hidden state、KV cache 或 permanent memory。长期记忆可以作为证据来源，但 Cognitive State 表示当前任务所需的可行动状态。

\[
CS=(G,W,F)
\]

## Goal State (G)

描述 Agent 当前目标，包含 `objective`、`success_criteria`、`constraints`、`preferences`。成功标准应尽可能可观察；约束应保留会影响后续选择的边界。

```yaml
goal:
  objective: Fix authentication bug
  success_criteria:
    - All tests pass
  constraints:
    - No database migration
  preferences: []
```

## World Model / Working State (W)

描述 Agent 当前认为世界是什么样。除了已确认的 facts，还应显式保存未完全确认的 beliefs 与默认成立的 assumptions，避免将猜测误写成事实。Belief 的 confidence 是当前主观置信度，不代表已校准的概率。

```yaml
world:
  facts:
    - JWT validation fails after expiration
  beliefs:
    - claim: Timestamp conversion may be wrong
      confidence: 0.7
  assumptions:
    - Database schema is unchanged
```

## Frontier State (F)

描述 Agent 当前认知边界，包含 `current_focus`、`information_needs`、`next_action`。它应使接手的 Agent 知道先查什么、为什么查，以及下一步可以执行什么。

```yaml
frontier:
  current_focus: JWT verification logic
  information_needs:
    - Whether timezone conversion exists
  next_action: Inspect token validation function
```

## 表示与更新原则

1. 对同一历史，状态依未来任务而变；只保留会影响后续目标、判断或行动的信息。
2. 保留事实、信念和假设的区别；不确定内容应能在后续观察中修正。
3. `next_action` 是建议的可执行行动，不等同于已完成的行动。
4. 当目标或世界认识变化时，重估 G、W、F；过时内容应修正或移除。
5. 状态最小化需要同时衡量大小与未来行为能力，不能只优化字数。

JSON 字段名称以上述示例为准；第一阶段可先使用人审状态，随后对提取质量进行实验验证。
