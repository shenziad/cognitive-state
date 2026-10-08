# 第四轮：regression

完整运行：True；执行版本 `cycle4-execution-v2`。

| 条件 | 成功/分配 | 最终编码有效 | 首次有效 | 过早完成 | 总 Tokens | 提取+修复 Tokens |
|---|---:|---:|---:|---:|---:|---:|
| full_context | 14/14 | 不适用 | 不适用 | 0 | 115569 | 0 |
| summary | 14/14 | 14 | 14 | 0 | 93868 | 45738 |
| cs_v02 | 12/14 | 14 | 14 | 0 | 109928 | 49683 |
| cs_v031 | 14/14 | 14 | 14 | 0 | 121623 | 64913 |

实际响应 165 次；已知 Tokens 440988；总 Tokens 440988；未知用量请求 0。

行为失败、编码错误与跳过均保留分配分母。语义维度、调用阶段成本、缓存输入和延迟见 summary.json。

局限：
- Small known synthetic development tasks; no unseen generalization claim.
- Assistant content annotations; not independent human gold and not condition blinded.
- Maintenance, repair and failed calls counted; tokens do not establish currency savings.
- V0.3.1 changes schema, instructions and validation as a bundle; not a single-field causal test.
