# Phase 1 Experiment Design

## 目标

验证完整历史、普通摘要和结构化 Cognitive State 对未来任务行为能力的影响。第一阶段使用 API-based LLM，不训练模型。

## 输入条件

对每个任务实例，在固定的历史截断点构造同一段 `H_t` 和相同的后续任务 `T`：

1. **Full Context**：Executor 接收完整历史。
2. **Summary**：Executor 接收由历史生成的普通摘要。
3. **Cognitive State**：Executor 接收包含 Goal、World Model、Frontier 的 JSON。

摘要与状态都只能读取截断点前的信息。记录生成它们所消耗的 Token；主比较报告 Executor 输入 Token，成本比较同时报告提取与执行总 Token。为检验结构本身，另设 Summary 与 Cognitive State 的等预算比较。

## 流程

```text
Historical Context → State Extractor → Cognitive State JSON
                                   └→ Summary
各输入条件 → 同一 Agent Executor → 同一评估器 → JSON 结果
```

固定执行模型、temperature、工具集、任务环境、最大输出预算和评分规则；随机化条件运行顺序。每个条件使用相同实例 ID，记录模型版本、prompt version、seed（如 API 支持）和时间戳。避免将评价答案泄漏到提取提示中。

## 评价指标

不使用文本完全一致作为成功标准。

| 指标 | 操作化定义 |
| --- | --- |
| Task Success Rate | 达到任务预注册成功条件的实例比例 |
| Final Goal Completion | 按各任务预注册的目标检查项计算完成比例 |
| Tool Usage Correctness | 必要工具调用是否正确、是否有错误或禁止调用 |
| Decision Consistency | 与任务约束及已知证据一致的关键决策比例；允许不同但同样有效的路径 |
| Token Reduction | 相对 Full Context 的输入 Token 降幅；另报端到端总 Token |

报告每个实例与总体统计，并保留失败案例以分析状态遗漏、错误信念及过时 Frontier。评分脚本应尽量使用环境信号或事先制定的 rubric；涉及人工/LLM judge 时记录评分协议并抽样复核。

## 实验序列

- `exp001_context_equivalence`：比较三条件的未来任务行为及 Token 成本。
- `exp002_state_extraction`：分析提取准确性、缺失项和不确定性标注。
- `exp003_long_horizon_agent`：在多轮续做中观察状态更新与行为连续性。

每次运行保存所用 `config.json` 快照及 `result.json`（或一组实例 JSON）。结果至少包含 `experiment_id`、`instance_id`、`condition`、`config`、`metrics`、`token_usage` 和 `artifacts`。敏感原始内容另行处理，绝不写入凭据。`results/raw/` 用于未纳入版本控制的原始输出。

## 尚待确定

正式运行前需选定 benchmark、任务拆分、样本量、成功阈值、评分者协议和具体 API 模型，并将其冻结到配置中。当前文件是实验预案，不声称已有结果。
