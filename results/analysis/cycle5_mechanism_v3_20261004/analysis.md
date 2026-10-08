# 第五轮 mechanism

完整运行：True；模型 `deepseek-ai/DeepSeek-V4-Flash`，temperature=0，thinking=false。

| 条件 | 成功/分配 | 策略归属 Tokens | credits |
|---|---:|---:|---:|
| full_context | 12/12 | 75964 | 12 |
| full_planner | 12/12 | 124934 | 12 |
| summary_s1 | 12/12 | 85187 | 12 |
| summary_s2 | 12/12 | 125567 | 12 |
| cs1 | 12/12 | 98812 | 12 |
| cs_text | 12/12 | 149312 | 12 |

实际全账本：204 次尝试，618444 已知 Tokens，0 次未知用量。策略归属包含各自完整源提取；共享 CS 源只在实际账本计一次，不相加冒充实际收费。

| 条件 | 任务层 | 成功/保存 |
|---|---|---:|
| full_context | historical_counterfactual | 12/12 |
| full_planner | historical_counterfactual | 12/12 |
| summary_s1 | historical_counterfactual | 12/12 |
| summary_s2 | historical_counterfactual | 12/12 |
| cs1 | historical_counterfactual | 12/12 |
| cs_text | historical_counterfactual | 12/12 |

| 基础配对 | 条件 | 双成员全成功 |
|---|---|---|
| hd01 | full_context | True |
| hd01 | full_planner | True |
| hd01 | summary_s1 | True |
| hd01 | summary_s2 | True |
| hd01 | cs1 | True |
| hd01 | cs_text | True |
| hd02 | full_context | True |
| hd02 | full_planner | True |
| hd02 | summary_s1 | True |
| hd02 | summary_s2 | True |
| hd02 | cs1 | True |
| hd02 | cs_text | True |
| hd03 | full_context | True |
| hd03 | full_planner | True |
| hd03 | summary_s1 | True |
| hd03 | summary_s2 | True |
| hd03 | cs1 | True |
| hd03 | cs_text | True |
| hd04 | full_context | True |
| hd04 | full_planner | True |
| hd04 | summary_s1 | True |
| hd04 | summary_s2 | True |
| hd04 | cs1 | True |
| hd04 | cs_text | True |
| hd05 | full_context | True |
| hd05 | full_planner | True |
| hd05 | summary_s1 | True |
| hd05 | summary_s2 | True |
| hd05 | cs1 | True |
| hd05 | cs_text | True |
| hd06 | full_context | True |
| hd06 | full_planner | True |
| hd06 | summary_s1 | True |
| hd06 | summary_s2 | True |
| hd06 | cs1 | True |
| hd06 | cs_text | True |

| 条件 | 审阅范围 | 具体来源错误/审阅 | 歧义 |
|---|---|---:|---:|
| full_planner | planner | 3/12 | 2 |
| summary_s1 | final | 5/12 | 5 |
| summary_s2 | final | 2/12 | 1 |
| summary_s2 | organizer | 1/12 | 2 |
| cs1 | final | 1/12 | 0 |

实际评分、失败、状态来源与成本归属分别报告。解释与案例需对照公开来源和真实轨迹，不将编码有效或字段存在等同于状态充分。

## 局限

- Known assistant-authored synthetic development workflows; paired members are correlated.
- Assistant source annotations are not independent human gold or condition blinded.
- CS-text compares this reversible field-path presentation only; it retains structure and all source information.
- Strategy deployment costs include shared source extraction for each strategy; their sum is not actual suite cost.
- Token usage does not establish measured currency fees or behavioral equivalence.
- Incomplete deployment rows do not cover all incurred strategy costs; actual_condition_usage and unassociated requests preserve them.
