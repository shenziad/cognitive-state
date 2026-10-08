# 第四轮：longitudinal

完整运行：True；执行版本 `cycle4-execution-v2`。

| 条件 | 成功/分配 | 最终编码有效 | 首次有效 | 过早完成 | 总 Tokens | 提取+修复 Tokens |
|---|---:|---:|---:|---:|---:|---:|
| full_context | 8/8 | 不适用 | 不适用 | 0 | 55325 | 0 |
| summary | 7/8 | 8 | 8 | 0 | 57471 | 16772 |
| cs_v02 | 8/8 | 8 | 8 | 0 | 66416 | 20074 |
| cs_v031 | 8/8 | 8 | 8 | 0 | 88521 | 33838 |

实际响应 111 次；已知 Tokens 267733；总 Tokens 267733；未知用量请求 0。

行为失败、编码错误与跳过均保留分配分母。语义维度、调用阶段成本、缓存输入和延迟见 summary.json。

| 场景 | 条件 | 整链全成功 | 成功段数 |
|---|---|---|---:|
| archive_workflow | full_context | True | 4/4 |
| archive_workflow | summary | False | 3/4 |
| archive_workflow | cs_v02 | True | 4/4 |
| archive_workflow | cs_v031 | True | 4/4 |
| release_workflow | full_context | True | 4/4 |
| release_workflow | summary | True | 4/4 |
| release_workflow | cs_v02 | True | 4/4 |
| release_workflow | cs_v031 | True | 4/4 |

局限：
- Small known synthetic development tasks; no unseen generalization claim.
- Assistant content annotations; not independent human gold and not condition blinded.
- Maintenance, repair and failed calls counted; tokens do not establish currency savings.
- V0.3.1 changes schema, instructions and validation as a bundle; not a single-field causal test.
