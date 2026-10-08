# Results

所有实验结果使用 JSON。每次运行保存实际配置快照与结果；原始结果置于被 Git 忽略的 `results/raw/`。发布汇总结果时应标注实验 ID、运行时间、模型版本、prompt version、benchmark 版本、实例数、评分协议及 Token 口径。

建议的单实例结构：

```json
{
  "experiment_id": "exp001_context_equivalence",
  "instance_id": "example-id",
  "condition": "cognitive_state",
  "config": {
    "model": "chosen-model-version",
    "temperature": 0.0,
    "benchmark": "chosen-benchmark-version",
    "prompt_version": "v0.1"
  },
  "metrics": {
    "task_success": true,
    "final_goal_completion": 1.0,
    "tool_usage_correctness": 1.0,
    "decision_consistency": 1.0
  },
  "token_usage": {
    "extractor_input": 0,
    "extractor_output": 0,
    "executor_input": 0,
    "executor_output": 0
  },
  "artifacts": []
}
```

上例只定义字段形状，并非实验结果。实际评分范围和缺失值规则需在 benchmark 协议中固定。

exp001 的实际格式还包含 repetition、运行状态、错误、表示大小、细项检查和 artifact 路径。每个实例 artifact 中保存调用及分阶段 Token 用量。详见 [运行说明](../experiments/exp001_context_equivalence/README.md)。mock 的证据类型为 mock_protocol_validation，API Token 及科学结论为 null；不得作为真实实验结果引用。

2026-10-02 完成 SiliconFlow 首轮真实先导实验；[分析报告](analysis/exp001_siliconflow_round1_20261002/analysis.md)、机器汇总、逐任务审阅与复核 JSON 保存在同一分析目录。原始结果在 results/raw/exp001/siliconflow_round1_20261002，未纳入 Git；两任务预检与充值前余额不足记录单独保留。

同日完成区分性真实模型预检（6 个任务 × 4 条件，24 组合）与完整单轮（18 个任务 × 4 条件，72 组合）。原始目录分别为 `results/raw/exp001/siliconflow_discriminative_smoke_20261002` 和 `results/raw/exp001/siliconflow_discriminative_round1_20261002`。

完整运行中 Full Context、Summary、自动 CS 与候选参考状态分别成功 **16/18、16/18、15/18、18/18**；16 个配对实例中前三条件均为 **14/16**，两个 controls 中 Full Context、Summary 均为 **2/2**，自动 CS 为 **1/2**。候选参考状态仍为 `pending`、待独立研究者审核，不能作为人审 gold；结果只描述这一轮小型合成任务，不能证明 H1–H3 或 CS 优于摘要。

[区分性单轮分析报告](analysis/exp001_discriminative_round1_20261002/analysis.md)、`discrimination.json` 与 `task_diagnostics.json` 保存在同一目录。独立后处理入口为 `scripts/analyze_discriminative.py`，CLI 见 [脚本说明](../scripts/README.md)；重新分析须选择全新输出目录，已生成报告不覆盖。

## 第二轮结果索引

已完成四阶段计划及一个失败后单案例诊断，主入口为 [总报告](analysis/research_cycle2_20261002/analysis.md) 和 [机器汇总](analysis/research_cycle2_20261002/cycle_summary.json)。

- [执行器校准](analysis/executor_calibration_20261002/analysis.md)：两个 prompt 各 16 组合。
- [公平续做](analysis/fair_v02_20261002/analysis.md)：14 任务 × 4 条件，主任务与 controls 分开。
- [预算及消融](analysis/ablation_budget_v02_20261002/analysis.md)：140 网格组合，共享提取按实际账本计一次。
- [Frontier 单案例](analysis/frontier_case_v02_20261002/analysis.md)：5 次局部改动，观察失败后选择，不并入主基准。
- [连续四次交接](analysis/longitudinal_v01_20261002/analysis.md)：两场景 × 四段 × 四条件；表示错误后保存 skipped 段。

相应原始目录为 `results/raw/exp001/executor_calibration_v02_20261002`、`executor_calibration_v03_20261002`、`fair_v02_20261002`、`ablation_budget_v02_20261002`、`frontier_case_v02_20261002`，以及 `results/raw/exp003/longitudinal_v01_20261002`。它们被 Git 忽略，需另行转移才可在 Ubuntu 复核原始模型调用。公开合成输入、代码、配置与分析报告可随仓库同步，`.env` 不随仓库同步。

## 第三轮结果索引

[总报告](analysis/research_cycle3_20261003/analysis.md)、[机器汇总](analysis/research_cycle3_20261003/cycle_summary.json)、[复核记录](analysis/research_cycle3_20261003/verification.json)。原始预检为 `results/raw/cycle3/preflight_20261003` 和 `results/raw/cycle3/preflight_r2_20261003`；两版全部保留，后续四条件比较/连续交接没有运行。修订版[语义审阅](analysis/cycle3_preflight_r2_20261003/semantic_review.json)包含 24 份最终状态及公开输入，可随 Git 版本控制；完整调用原始目录仍需单独转移。

## 第四轮结果索引

2026-10-03—04 完成单独恢复实验的预检 96 组合、回归 56 组合、连续交接 32 段。[总报告](analysis/research_cycle4_20261004/analysis.md)、[机器汇总](analysis/research_cycle4_20261004/summary.json)分开保存原中断轮、探测和恢复运行的费用。

- [预检来源—行为关联](analysis/cycle4_preflight_recovery_v1/semantic_behavior_notes.md)：35 份具体来源错误状态，其中 32 份行为成功。
- [回归来源—行为关联](analysis/cycle4_regression_recovery_v1/semantic_behavior_notes.md)：旧 CS 额外查询导致两次预算失败。
- [连续交接案例](analysis/cycle4_longitudinal_recovery_v1/semantic_behavior_notes.md)：摘要丢失关键分支；两版 CS 成功但总 Tokens 更高。

各阶段分析目录均保存 `review.json`、`audit.json`、`gate.json` 和 `report/summary.json`。原始目录为 `results/raw/cycle4/preflight_v2_20261003`（中断）及 `{preflight,regression,longitudinal}_recovery_v1_20261003`（恢复）；longitudinal 实际在 10 月 4 日完成，目录名沿用事前计划。原始目录受 Git 忽略，Ubuntu 完整回放须另行转移；公开审阅包与分析可随仓库同步。

执行资产保持冻结，117 项离线测试记录见[验证 JSON](../docs/freezes/cycle4_offline_validation_v2.json)。离线 oracle 和新工作流可解性检查不作为模型成绩。

## 第五轮结果索引

2026-10-04 完成事前历史反事实子层诊断及六条件 72-cell 对照。优先审阅[总报告](analysis/research_cycle5_20261004/analysis.md)、[机器汇总](analysis/research_cycle5_20261004/summary.json)、[目标评分覆盖审计](analysis/research_cycle5_20261004/goal_coverage_audit.json)。

- [D 事前配对子层](analysis/cycle5_diagnostic_v1_20261004/prespecified_counterfactual_stratum.md)：Full 12/12、No History 5/12；原 D 全体未完成，不补跑或拼接。
- [A-v2 中断产物审计](analysis/cycle5_mechanism_v2_interrupted_20261004/preparation_audit.md)：31 份准备产物、一次未知用量，无执行器行为。
- [A-v3 完整主分析](analysis/cycle5_mechanism_v3_20261004/analysis.md)：六条件均为已实现检查点评分 12/12。
- [成本与来源交叉](analysis/cycle5_mechanism_v3_supplement_20261004/cost_and_source.md)：执行输入和完整部署成本分开；共享 CS 源真实账本计一次。
- [全部来源审阅](analysis/cycle5_mechanism_v3_sources_20261004/source_review.json)与[行为前封存](analysis/cycle5_mechanism_v3_sources_20261004/source_review_seal.json)。
- [archive/hotel 案例](analysis/cycle5_mechanism_v3_cases_20261004/hd01_02_notes.md)、[单位计算/凭据案例](analysis/cycle5_mechanism_v3_cases_20261004/hd05_06_notes.md)。

原始运行位于 `results/raw/cycle5/{diagnostic_v1,mechanism_v2,mechanism_v3}_20261004`，另有单独 service probe。原始目录受 Git 忽略，Ubuntu 完整回放需单独转移；公开输入、审阅和分析报告可随仓库同步。344 次真实尝试共 1,198,707 已知 Tokens、一次未知用量，完整总量未知，见[campaign.json](analysis/research_cycle5_20261004/campaign.json)。

重要限制：六配对共享一个旧事实选择机制；部分用户保留要求未进入世界/评分。当前满分不证明状态充分、完整目标达成或未来行为等价。

## 2026-10-08：原始记录现已归档

上述“原始目录需单独转移”的说明是归档前状态。现在 [experiments_20261008.zip](archives/experiments_20261008.zip) 与逐文件 SHA 清单随仓库版本控制，共 2,268 个实验记录文件，包含全部完成和中断轮。Git clone 后执行 `python scripts/restore_experiment_records.py` 即可恢复 `results/raw/`；现有不同文件不会被覆盖。详细范围、Ubuntu 路径限制见 [归档说明](archives/README.md)。历史实验及冻结原件未修改。
