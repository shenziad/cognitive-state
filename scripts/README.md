# Scripts

`python scripts/check_cycle4_protocol.py` 离线检查第四轮协议的 SHA256、配置/规模一致性、12 个生命周期示例的编码与引用以及 20 个门槛决策案例。它不调用模型，也不证明运行器已支持第四轮；见[冻结协议](../docs/cycle4_protocol_20261003.md)。

实验构造、运行与后处理入口脚本放在此目录。运行脚本应读取实验 `config.json`、保存实际配置快照、输出 JSON 结果，并禁止隐式使用未记录的模型或 prompt 设置。

- `run_experiment.py`：从任何工作目录运行 exp001，默认读取仓库内配置。
- `build_pilot_dataset.py`：从离线定义重建合成 v0.1 数据；会覆盖该版本的任务与参考状态。
- `analyze_experiment.py`：从冻结运行目录导出 JSON/Markdown 描述性报告；服务中断不报告性能结论。
- `analyze_discriminative.py`：独立分析冻结的区分性任务运行，分开汇总配对实例与 controls，导出 G/W/F 成功率、A/B joint success 与变化、Full Context discordances、Token 宏平均/总量和逐任务执行诊断。只读 JSON，不调用 API、不读取凭据；服务中断不发布性能或降幅，输出目录已存在则拒绝覆盖。
- `build_discriminative_dataset.py`：离线构造 8 组配对和 2 个正对照，只写新目录，不覆盖审阅数据。
- `validate_discriminative_dataset.py`：重放候选方案及配对交换，核对预算、来源、目录边界；只验证构造一致性，不评价模型。

建议在仓库根目录运行；所有相对配置/输出命令参数以当前工作目录为准，配置中的 dataset 路径以仓库根目录为准。

2026-10-02 已完成区分性真实模型预检 24 组合及完整单轮 72 组合；候选参考状态仍为 `pending`。已发布 [单轮报告](../results/analysis/exp001_discriminative_round1_20261002/analysis.md) 只描述本轮小型合成任务，不能证明 CS 优于摘要。

重新分析完整运行时指定全新目录：

```powershell
.venv/Scripts/python.exe scripts/analyze_discriminative.py --run results/raw/exp001/siliconflow_discriminative_round1_20261002 --output results/analysis/exp001_discriminative_round1_20261002_reanalysis
```

输出包含 `discrimination.json`、`task_diagnostics.json` 和中文 `analysis.md`。任务失败与提取错误保留成功率分母；未启动 executor 的样本执行诊断为 null。实际已报告花费包含提取失败，Token 降幅仅计算两侧都非 error 且可观测的配对，不按任务成功筛选。候选参考状态制作成本未测量，不计算其端到端优势。

## 第二轮：校准、公平续做、预算与连续交接

- `build_executor_calibration.py`：构造独立的 8 个执行协议校准任务。
- `analyze_executor_calibration.py`：重放两个 prompt 的校准结果，检查预先规定的进入门槛。
- `build_continuation_v02.py`：构造 6 组历史差异配对及 2 个控制任务，同时提供公开的恢复信息。
- `run_staged_experiment.py`：按冻结配置运行公平比较或字节预算/消融网格；相同 CS 提取供多个消融共享，实际调用账本只计一次。
- `analyze_staged_experiment.py`：输出分开统计主任务与 controls 的 JSON/Markdown；`verify_staged_run.py` 独立重放并核对唯一请求及用量。
- `run_frontier_case.py`：对已观察到的一个失败状态做预声明的 5 种局部改动。它属于观察失败后的单案例诊断，不替换主实验成绩。
- `run_longitudinal_experiment.py`：运行两场景、四次交接；压缩条件只读取上次保留表示、真实动作观测和新事件。
- `analyze_longitudinal_experiment.py`：只读复核世界继承、历史删除边界、轨迹和成本。

以下真实运行会产生 API 费用；每次应选择新的输出目录。密钥读取 `.env`，不写入命令或结果。`utf8_bytes` 是表示约束，不是 provider Token。

```bash
python scripts/run_staged_experiment.py --config configs/exp001_fair_v02.json --output results/raw/exp001/<new-fair-run> --progress
python scripts/run_staged_experiment.py --config configs/exp001_ablation_budget_v02.json --output results/raw/exp001/<new-budget-run> --progress
python scripts/analyze_staged_experiment.py --run results/raw/exp001/<run> --output results/analysis/<new-analysis>
python scripts/verify_staged_run.py --run results/raw/exp001/<run> --output results/analysis/<analysis>/verification.json
python scripts/run_longitudinal_experiment.py --config configs/exp003_longitudinal_pilot.json --output results/raw/exp003/<new-run> --progress
python scripts/analyze_longitudinal_experiment.py --run results/raw/exp003/<run> --output results/analysis/<new-analysis>
```

Frontier 案例配置锁定第二轮原始 artifact 的 SHA256；需持有该原始运行目录才能复现。原始目录受 Git 忽略，Ubuntu 单纯 clone 只会获得代码、公开合成数据及分析报告；复核原始调用需要另外转移 `results/raw/`。冻结计划见 [第二轮计划](../docs/next_experiment_plan_20261002.json)。

`summarize_research_cycle.py --output results/analysis/<new-cycle-summary>` 汇总固定的第二轮已核验报告和实际账本，输出 `analysis.md` 与 `cycle_summary.json`。只读本地记录，不调用模型、不读取凭据；原始运行及独立解释 JSON 必须齐全，已有输出目录不覆盖。

## 第三轮 v0.3

- `build_v03_cycle.py` / `build_v03_cycle_r2.py`：构造独立版本的六类预检模板及已知回归/四次交接输入。
- `run_v03_cycle.py` / `run_v03_cycle_r2.py`：保留全部请求、显式修复、状态和轨迹；比较阶段必须提供经过审核且匹配冻结 hash 的 passed gate。
- `analyze_v03_cycle.py`：离线核对输入、代码快照、实际请求、世界/表示继承及轨迹评分，导出 JSON 与 Markdown；输出目录不可覆盖。

运行方式见[实现说明](../docs/v03_implementation_and_cycle3.md)。两版预检均已完成，当前 gate failed，后两阶段未运行。原始文件受 Git 忽略，Ubuntu 复核须另外转移；见[第三轮报告](../results/analysis/research_cycle3_20261003/analysis.md)。

## 第四轮实现入口

- `build_cycle4.py`：重建固定实例与运行顺序；拒绝覆盖现有目录。
- `freeze_cycle4.py`：全量离线测试后锁定当前执行版本；已有版本拒绝覆盖。
- `run_cycle4.py`：预检/回归/四次交接运行，API 调用前验证发布清单，后两阶段还验证真实审阅 gate。
- `audit_cycle4.py`：生成无后续评分的来源审阅包，或离线重建输入/轨迹/账本并生成 gate。

`cycle4-execution-v2` 保持冻结；已按独立恢复计划完成三个真实阶段。完整命令和审阅流程见[执行说明](../docs/cycle4_execution_v2.md)，结果见[第四轮报告](../results/analysis/research_cycle4_20261004/analysis.md)。重新运行不是继续现有结果，需新的实验计划；已有输出目录不可覆盖。

- `report_cycle4.py`：只读指定运行、审阅和 audit，导出阶段 JSON/Markdown；包含提取、修复、执行及失败费用。
- `summarize_cycle4_campaign.py`：核对恢复计划 hash，汇总原中断轮、独立探测及恢复阶段，未知用量保留为未知，不调用模型。
- `check_siliconflow_service.py`：一次小型诊断请求，零隐式重试，只输出安全的错误类别和用量；本轮已探测成功，不需重复调用。
- `build_independent_workflows_v01.py`：离线构造 12 条新工作流及 48 个公开 checkpoint，重放合法/负面路径并保存 provenance。已有版本拒绝覆盖；特权评分 fixture 和离线轨迹不得发送给模型。

离线重新分析时选择新输出目录，例如：

```bash
python scripts/report_cycle4.py --run results/raw/cycle4/longitudinal_recovery_v1_20261003 --review results/analysis/cycle4_longitudinal_recovery_v1/review.json --audit results/analysis/cycle4_longitudinal_recovery_v1/audit.json --output results/analysis/<new-stage-report>
python scripts/summarize_cycle4_campaign.py --output results/analysis/<new-campaign-report>
```

第二条命令需同时持有恢复计划引用的原始文件。新机制矩阵和成本曲线运行器尚未实现，见[准备草案](../docs/mechanism_and_cost_plan_v01.md)。

## 第五轮：历史必要性与六条件机制矩阵

最新完成结果见 [总报告](../results/analysis/research_cycle5_20261004/analysis.md)，代码入口见 [exp004](../experiments/exp004_mechanism/README.md)。

- `run_cycle5.py`：原 v1 冻结运行；D 预算中断保留。
- `run_cycle5_v2.py`：配对子层工程修订；A-v2 API 中断保留。
- `run_cycle5_v3.py`：一次完整恢复，prepare → review_packet → 保存全部来源标注 → execute → audit。不能覆盖旧目录或直接续跑中断目录。
- `analyze_cycle5_v3.py`：完整消息、轨迹、世界、评分与账本回放；分析输出须为新目录。
- `report_cycle5_campaign.py`：D、中断 A、探测、恢复 A 全部实际成本；未知用量保持未知。
- `audit_cycle5_interrupted_preparation.py`：中断 preparation 的逐项回放，不能代替完整行为比较。

真实运行需要本地环境凭据和完整冻结资产。原始记录在被 Git 忽略的 `results/raw/cycle5/`；Ubuntu 迁移需转移记录、匹配依赖，并处理保存的 Windows source_run 路径，不修改原冻结原件。

## 实验归档恢复

`restore_experiment_records.py` 使用标准库，验证归档及每个成员的SHA256后恢复原始记录，拒绝替换已有不同内容。

```bash
python scripts/restore_experiment_records.py --verify-only
python scripts/restore_experiment_records.py
```

可用 `--destination <directory>` 指定恢复副本的仓库根目录，文件始终写到其 `results/raw/` 下；这不会改写记录中的绝对路径。归档范围见 [说明](../results/archives/README.md)。
