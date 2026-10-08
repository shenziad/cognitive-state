# 第三轮：preflight 结果

完整运行：True。冻结输入、源文件、模型输入、轨迹、评分及实际调用账本复核通过。

| 条件 | 范围 | 成功/分配 | 实际执行 | 表示失败 | 修复调用 | 总 Tokens（已报告） |
|---|---|---:|---:|---:|---:|---:|
| full_context | main | 23/24 | 24 | 0 | 0 | 56,483 |
| cs_v03 | main | 24/24 | 24 | 0 | 2 | 124,023 |

实际响应 115 次，总 Tokens 180506，未知用量请求 0。

首次有效率、缓存输入、输出和延迟见 analysis.json；错误/跳过保留在分母中，低成本失败不代表效率优势。

- Small synthetic exploratory study; regression tasks were previously inspected.
- V0.3 is a bundle of schema, instructions, validation and repair; not an individual mechanism ablation.
- Common public contracts changed for every condition; old scores are not a matched baseline.
- Bytes are not model tokens; costs include all calls and do not imply currency savings.
