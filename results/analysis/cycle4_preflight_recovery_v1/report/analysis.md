# 第四轮：preflight

完整运行：True；执行版本 `cycle4-execution-v2`。

| 条件 | 成功/分配 | 最终编码有效 | 首次有效 | 过早完成 | 总 Tokens | 提取+修复 Tokens |
|---|---:|---:|---:|---:|---:|---:|
| full_context | 23/24 | 不适用 | 不适用 | 0 | 91743 | 0 |
| summary | 24/24 | 24 | 24 | 0 | 114718 | 30055 |
| cs_v02 | 22/24 | 24 | 24 | 0 | 142598 | 36126 |
| cs_v031 | 22/24 | 24 | 24 | 0 | 162364 | 62712 |

实际响应 294 次；已知 Tokens 511423；总 Tokens 511423；未知用量请求 0。

行为失败、编码错误与跳过均保留分配分母。语义维度、调用阶段成本、缓存输入和延迟见 summary.json。

局限：
- Small known synthetic development tasks; no unseen generalization claim.
- Assistant content annotations; not independent human gold and not condition blinded.
- Maintenance, repair and failed calls counted; tokens do not establish currency savings.
- V0.3.1 changes schema, instructions and validation as a bundle; not a single-field causal test.
