# Datasets

在这里记录 benchmark 来源、许可、版本、下载或生成步骤、历史截断点和任务拆分。大型或受限数据不应直接提交；正式实验前固定数据版本与实例 ID。

当前 [exp001-pilot-v0.1](exp001/v0.1/README.md) 包含 12 个助手制作的合成任务，参考状态尚待研究者审核。

第二轮使用 [continuation-v0.2](exp001/continuation_v0.2/README.md)：6 组 A/B 配对、2 controls，配对共享公开工具目录和恢复机制，关键差异来自历史证据。候选状态不输入主比较，仍待研究者审核。设计见 [公平续做任务](../docs/continuation_v02_design.md)。

`exp001/executor_calibration_v0.1/` 是独立执行协议校准集。`exp003/longitudinal_v0.1/` 包含两个连续四交接场景；世界继承及历史边界规则见 [连续交接设计](../docs/longitudinal_pilot_design.md)。所有数据均为助手构造的小型合成任务，不能代表自然长期任务分布。

第三轮输入位于 `cycle3_v03/` 与 `cycle3_v03r2/`。preflight 为六类短合成模板、各两个标签版本；修订版只更换标签/工作区值，不构成独立泛化集。regression 和 longitudinal 来自此前已查看的任务，只能作为已知任务回归；本轮没有对它们调用模型。参见[第三轮报告](../results/analysis/research_cycle3_20261003/analysis.md)。

第四轮实际输入已生成于 `cycle4_v1/`：12 个预检实例、14 个已知回归实例、两个四段链；包含确定性顺序和 adaptation.json。offline_solution 只用于离线可解性验证，不发送给模型。执行已冻结，详见[实现说明](../docs/cycle4_execution_v2.md)。

## 新工作流候选 v0.1

[independent_workflows_v01](independent_workflows_v01/README.md) 包含 12 条业务工作流、48 个 checkpoint。用户要求、事件、工具契约先于状态字段设计；同目录分开保存公开投影、特权评分 fixture、离线解和 provenance。已通过构造审查与离线可解性/负面路径检查，尚未运行真实模型；离线解不得作为免费 baseline 输入。

这些是助手编写的新开发实例，不能称为正式 held-out 泛化集。历史必要性、No History 和历史差异配对仍待检验；失败后恢复规则及模型输入投影还需在下一轮冻结。见[设计](../docs/independent_workflow_design_v01.md)和[审查](../docs/independent_workflow_review_v01.md)。
