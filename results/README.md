# Results

所有实验结果使用 JSON。每次运行保存实际配置快照与结果；原始结果置于被 Git 忽略的 `results/raw/`。发布汇总结果时应标注实验 ID、运行时间、模型版本、prompt version、benchmark 版本、实例数、评分协议及 Token 口径。

建议的单实例结构：

```json
{
  "experiment_id": "exp001_context_equivalence",
  "instance_id": "example-id",
  "condition": "cognitive_state",
  "config": {
    "model": "chosen-model-version",
    "temperature": 0.0,
    "benchmark": "chosen-benchmark-version",
    "prompt_version": "v0.1"
  },
  "metrics": {
    "task_success": true,
    "final_goal_completion": 1.0,
    "tool_usage_correctness": 1.0,
    "decision_consistency": 1.0
  },
  "token_usage": {
    "extractor_input": 0,
    "extractor_output": 0,
    "executor_input": 0,
    "executor_output": 0
  },
  "artifacts": []
}
```

上例只定义字段形状，并非实验结果。实际评分范围和缺失值规则需在 benchmark 协议中固定。
