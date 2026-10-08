# 第三轮：preflight 结果

完整运行：True。冻结输入、源文件、模型输入、轨迹、评分及实际调用账本复核通过。

| 条件 | 范围 | 成功/分配 | 实际执行 | 表示失败 | 修复调用 | 总 Tokens（已报告） |
|---|---|---:|---:|---:|---:|---:|
| full_context | main | 24/24 | 24 | 0 | 0 | 55,646 |
| cs_v03 | main | 15/24 | 15 | 9 | 19 | 113,072 |

实际响应 113 次，总 Tokens 168718，未知用量请求 0。

首次有效率、缓存输入、输出和延迟见 analysis.json；错误/跳过保留在分母中，低成本失败不代表效率优势。

- Small synthetic exploratory study; regression tasks were previously inspected.
- V0.3 is a bundle of schema, instructions, validation and repair; not an individual mechanism ablation.
- Common public contracts changed for every condition; old scores are not a matched baseline.
- Bytes are not model tokens; costs include all calls and do not imply currency savings.

## 预检门槛未通过

Full Context 24/24 成功；CS v0.3 15/24 可用且成功。初次有效 5/24，19 次调用修复；修复后仍有 9 次表示失败。已进入执行的 15 次均完成，但不能用该选择子集声称端到端可靠。

最终失败分类：{"source_class_false_rejection_of_grounded_contract_constraint": 1, "candidate_action_at_root": 5, "target_string_instead_of_object": 1, "frontier_nested_in_world": 1, "malformed_json": 1}。公开接口约束的来源误拒属于当前校验器缺陷；其余涉及 JSON/字段嵌套和 target 类型。错误反馈缺少字段位置，提示没有完整示范可选 candidate_action 的嵌套。未出现字节超限。

本轮门槛失败，未解锁比较。冻结失败结果后，单独版本 minimal-2 修正实现问题并重跑全部预检；改用新标签仍复用相同模板，不是独立泛化测试。
