# 第五轮 mechanism

完整运行：False；模型 `deepseek-ai/DeepSeek-V4-Flash`，temperature=0，thinking=false。

| 条件 | 成功/分配 | 策略归属 Tokens | credits |
|---|---:|---:|---:|
| full_context | 未知/12 | 0 | 0 |
| full_planner | 未知/12 | 0 | 0 |
| summary_s1 | 未知/12 | 0 | 0 |
| summary_s2 | 未知/12 | 0 | 0 |
| cs1 | 未知/12 | 0 | 0 |
| cs_text | 未知/12 | 0 | 0 |

实际全账本：26 次尝试，78153 已知 Tokens，1 次未知用量。策略归属包含各自完整源提取；共享 CS 源只在实际账本计一次，不相加冒充实际收费。


实际评分、失败、状态来源与成本归属分别报告。解释与案例需对照公开来源和真实轨迹，不将编码有效或字段存在等同于状态充分。

## 局限

- Known assistant-authored synthetic development workflows; paired members are correlated.
- Assistant source annotations are not independent human gold or condition blinded.
- CS-text compares this reversible field-path presentation only; it retains structure and all source information.
- Strategy deployment costs include shared source extraction for each strategy; their sum is not actual suite cost.
- Token usage does not establish measured currency fees or behavioral equivalence.
- Incomplete deployment rows do not cover all incurred strategy costs; actual_condition_usage and unassociated requests preserve them.
