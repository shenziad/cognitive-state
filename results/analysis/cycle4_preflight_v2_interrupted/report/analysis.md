# 第四轮：preflight

完整运行：False；执行版本 `cycle4-execution-v2`。

| 条件 | 成功/分配 | 最终编码有效 | 首次有效 | 过早完成 | 总 Tokens | 提取+修复 Tokens |
|---|---:|---:|---:|---:|---:|---:|
| full_context | 未完成/未知/24 | 未完成/未知 | 未完成/未知 | 0 | 10136 | 0 |
| summary | 未完成/未知/24 | 5 | 5 | 0 | 未完成/未知 | 6327 |
| cs_v02 | 未完成/未知/24 | 5 | 5 | 0 | 33371 | 7718 |
| cs_v031 | 未完成/未知/24 | 6 | 6 | 0 | 33665 | 15430 |

实际响应 57 次；已知 Tokens 100764；总 Tokens 未完成/未知；未知用量请求 1。

行为失败、编码错误与跳过均保留分配分母。语义维度、调用阶段成本、缓存输入和延迟见 summary.json。

本阶段中断，表中编码和动作计数只覆盖已保存记录。未运行组合不是行为失败；不得从不平衡的部分样本计算条件成功率、编码率或成本优势。

局限：
- Small known synthetic development tasks; no unseen generalization claim.
- Assistant content annotations; not independent human gold and not condition blinded.
- Maintenance, repair and failed calls counted; tokens do not establish currency savings.
- V0.3.1 changes schema, instructions and validation as a bundle; not a single-field causal test.
