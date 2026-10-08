# 第四轮恢复实验与研究进展

原预检因 API 错误中断，保留原轮并按单独恢复计划从头运行；不拼接部分样本。

| 阶段 | 完成 | Full | Summary | CS v0.2 | CS v0.3.1 | 已知 Tokens |
|---|---|---:|---:|---:|---:|---:|
| preflight | True | 23/24 | 24/24 | 22/24 | 22/24 | 511423 |
| regression | True | 14/14 | 14/14 | 12/14 | 14/14 | 440988 |
| longitudinal | True | 8/8 | 7/8 | 8/8 | 8/8 | 267733 |

## 本轮主要发现

三个阶段共完成 184 个分配组合（96 预检、56 回归、32 连续交接）；压缩条件的 138 份表示全部首次编码有效，无编码修复。来源审阅与行为成绩分开记录，不能把这些编码结果解释为语义完全正确。

**具体正面线索：保留已完成工作的决策身份。** archive 链的 Summary 在第三段丢失此前确认并修复的 right 分支，第四段缺少选择依据而实际 `finish blocked`；Full、CS v0.2、CS v0.3.1 都保留该依据并执行 `seal_right`。错误来源先于当前行为揭示完成审阅。两版 CS 都成功，不能把本案例归因于 v0.3.1 新增字段、G/W/F 名称或 JSON 编码。

**负面结果：总成本目标仍未达到。** v0.3.1 三阶段总 Tokens 均高于 Full 和 Summary；v0.2 各阶段均高于 Summary，回归虽少于 Full，却只有 12/14 成功。连续交接仅有两个已知工作流，每条件一次；CS 整链 2/2、Summary 1/2 是开发案例结果，不能确认普遍优势或行为等价。

**状态正确性和行为成功不一致。** 预检 35/72 份压缩表示有具体来源错误，其中 32 份仍行为成功。回归 v0.2 的两次失败在实际校准完成后添加预算外 ledger 查询；连续实验 v0.3.1 又保留与当前成功阶段并存的旧 claim，按歧义记录。这些问题需要独立的状态更新诊断。

## 连续交接

| 工作流 | 条件 | 整链全成功 | 成功段数 |
|---|---|---|---:|
| archive_workflow | full_context | True | 4/4 |
| archive_workflow | summary | False | 3/4 |
| archive_workflow | cs_v02 | True | 4/4 |
| archive_workflow | cs_v031 | True | 4/4 |
| release_workflow | full_context | True | 4/4 |
| release_workflow | summary | True | 4/4 |
| release_workflow | cs_v02 | True | 4/4 |
| release_workflow | cs_v031 | True | 4/4 |

## 成本与审阅

整个流程（含中断原轮和独立探测）：629 次尝试，1,320,918 已知 Tokens，1 次未知用量；完整总 Tokens 未知。

下表计入提取、维护、执行及失败调用；相对 Full 的正数表示更多 Tokens。它不按任务成功筛选，也不代表人民币费用。

| 阶段 | 条件 | 全部策略 Tokens | 相对 Full |
|---|---|---:|---:|
| preflight | full_context | 91743 | +0.0% |
| preflight | summary | 114718 | +25.0% |
| preflight | cs_v02 | 142598 | +55.4% |
| preflight | cs_v031 | 162364 | +77.0% |
| regression | full_context | 115569 | +0.0% |
| regression | summary | 93868 | -18.8% |
| regression | cs_v02 | 109928 | -4.9% |
| regression | cs_v031 | 121623 | +5.2% |
| longitudinal | full_context | 55325 | +0.0% |
| longitudinal | summary | 57471 | +3.9% |
| longitudinal | cs_v02 | 66416 | +20.0% |
| longitudinal | cs_v031 | 88521 | +60.0% |

| 阶段 | 条件 | 最终表示有效 | 首次有效 | 来源审阅有具体错误的表示 | 全部策略 Tokens |
|---|---|---:|---:|---:|---:|
| preflight | summary | 24/24 | 24/24 | 11/24 | 114718 |
| preflight | cs_v02 | 24/24 | 24/24 | 15/24 | 142598 |
| preflight | cs_v031 | 24/24 | 24/24 | 9/24 | 162364 |
| regression | summary | 14/14 | 14/14 | 1/14 | 93868 |
| regression | cs_v02 | 14/14 | 14/14 | 3/14 | 109928 |
| regression | cs_v031 | 14/14 | 14/14 | 0/14 | 121623 |
| longitudinal | summary | 8/8 | 8/8 | 2/8 | 57471 |
| longitudinal | cs_v02 | 8/8 | 8/8 | 0/8 | 66416 |
| longitudinal | cs_v031 | 8/8 | 8/8 | 0/8 | 88521 |

编码失败/提取未完成的表示按 not_observed 记录；上述来源错误计数不能与编码有效率或任务成功率互换。全部维护、修复、执行和失败成本保留。

详细证据：[恢复预检](../cycle4_preflight_recovery_v1/semantic_behavior_notes.md)、[回归](../cycle4_regression_recovery_v1/semantic_behavior_notes.md)、[连续交接](../cycle4_longitudinal_recovery_v1/semantic_behavior_notes.md)。原中断轮单独见 [关联分析](../cycle4_preflight_v2_interrupted/semantic_behavior_notes.md)。

## 新任务与下一步

已生成并离线审查 12 条业务工作流、48 个 checkpoint；先写用户要求、工具契约和事件，不以 G/W/F 标签作为任务答案。修复了公开接口泄露、隐含执行要求和失败后仍假定成功等构造问题。它们仍是已知开发候选任务，离线可解性不是模型验证，也没有证明每段都需要历史。见 [设计](../../../docs/independent_workflow_design_v01.md)、[审计](../../../docs/independent_workflow_review_v01.md)和[数据](../../../datasets/independent_workflows_v01/README.md)。

下一步优先核查这些候选任务的历史必要性：用 No History 与改变早期事实、保持当前请求相同的配对版本，检查工具能否免费恢复答案及当前提示是否已暴露选择。随后冻结阶段 A 的最小机制矩阵，比较强摘要、额外规划、两步摘要、CS 和同信息文本编码；先区分保留的信息、额外推理和表示形式。v0.3.1 的旧 claim 撤销问题应在单独的新更新版本处理，再在新任务检验。

[机制与成本方案](../../../docs/mechanism_and_cost_plan_v01.md)目前仅为草案：运行器、干预规则和新实验协议尚未冻结，A/B/C 均未调用模型。长期成本曲线留待前述检查完成；没有继续扩大本轮样本或选择性重跑。

## 解释范围

- Recovery is a separate full run; partial rows are never merged into its denominator.
- Task success and encoding validity do not establish source-grounded state correctness.
- All tasks are known synthetic development data; repetitions are correlated.
- Assistant review is not independent human gold or condition-blinded.
- Unknown usage remains unknown; token totals are not currency amounts.
