# exp001: Context Equivalence

对固定历史截断点的相同续做任务，比较 Full Context、Summary 与 Cognitive State 的任务行为与 Token 成本。正式运行前在 `config.json` 填入模型、benchmark、任务集与预算，并冻结评分规则。每次运行保存配置快照及 JSON 结果。实验细节见 `docs/experiment_design.md`。
