# Configuration convention

`cycle4_protocol_v1.json` 是第四轮冻结的**协议配置**，不是可运行配置；`execution_ready=false`。旧 runner 不兼容。门槛、语义及执行发布所需资产见[第四轮协议](../docs/cycle4_protocol_20261003.md)，不能据此直接启动 API 调用。

每个实验目录的 `config.json` 是该实验的默认配置。运行时必须在结果旁保存**实际使用的配置快照**，包括 `model`、`temperature`、`benchmark`、`prompt_version`，以及任务集、预算、采样参数等会影响复现的字段。不要把 API key 写入配置。

`base.json` 仅给出字段形状与占位值；具体模型和 benchmark 应在正式运行前确定并冻结。`null` 表示未选择，不得据此宣称实验已可运行。

`experiments/exp001_context_equivalence/config.json` 是可运行的离线 mock 配置。`exp001_api.example.json` 是真实服务接入模板，需明确填写模型、endpoint 和计数器。运行器保存完整配置，拒绝未知字段；密钥只使用配置指定的环境变量。

SiliconFlow SDK 接入配置为 exp001_siliconflow.json，两个任务的连通性配置为 exp001_siliconflow_smoke.json。真实运行读取仓库根目录 .env，使用 api_key_env 指定的变量名。extra_body 仅允许显式的思考模式参数，禁止夹带凭据或覆盖消息等实验设置。

区分性草案配置 `exp001_discriminative_siliconflow.json` 有 18 个任务、四条件一次重复；`exp001_discriminative_smoke.json` 选择 6 个任务预检。两者使用虚拟工作流执行器 prompt v0.2，已于 2026-10-02 分别完成真实模型完整运行 72 组合及预检 24 组合；候选参考状态仍为 `pending`、待独立审核。不能用只支持旧配置修复的 mock 运行新任务；离线构造验证请用校验脚本。

结果见 [区分性单轮报告](../results/analysis/exp001_discriminative_round1_20261002/analysis.md)，仅描述本轮小型合成任务，不能证明 CS 优于摘要。独立后处理使用 `scripts/analyze_discriminative.py`，CLI 见 [脚本说明](../scripts/README.md)；必须读取运行目录的配置快照，输出到全新分析目录。

## 第二轮冻结配置

| 配置 | 范围 |
|---|---|
| `exp001_executor_calibration_v0.2.json` / `v0.3.json` | 8 个独立校准任务，各重复两次，只用完整历史 |
| `exp001_fair_v02.json` | 12 个主任务、2 controls，Full / Summary / CS / No History |
| `exp001_ablation_budget_v02.json` | 800、1400、2200 UTF-8 bytes；三个 CS 消融在 1400 下共享提取 |
| `exp001_frontier_case.json` | 失败后选取的单案例诊断；锁定原状态，5 个版本各执行一次 |
| `exp003_longitudinal_pilot.json` | 两场景 × 四次交接 × 四条件，实际世界继承 |

上述配置均固定 SiliconFlow、DeepSeek-V4-Flash、temperature 0 和请求上限。v0.3 共同执行协议通过预声明校准门槛，但没有显示优于 v0.2；Summary 与 CS 的提取提示保持原竞争性版本内容。主比较不输入候选参考状态。所有格式/字节超限错误保留，不隐式修复或回退完整历史。

## 第三轮 v0.3

`cycle3_*_v03.json` 保留首版配置；`cycle3_*_v03r2.json` 为另行冻结的修订版。两版 preflight 均已真实运行；regression、longitudinal 已配置但未运行，修订版 gate failed。设置和条件边界见[实现说明](../docs/v03_implementation_and_cycle3.md)，结果见[第三轮报告](../results/analysis/research_cycle3_20261003/analysis.md)。不得将新标签预检当作独立模板测试。

## 第四轮实际执行配置

`cycle4_preflight_v1.json`、`cycle4_regression_v1.json`、`cycle4_longitudinal_v1.json` 是实际配置，当前 execution_version 为 `cycle4-execution-v2`（文件名 v1 表示任务/配置系列）。需匹配[执行清单](../docs/freezes/cycle4_execution_v2.json)。最初的协议规格 `cycle4_protocol_v1.json` 继续作为历史冻结记录，不传给运行器。

## 第五轮冻结配置

| 配置 | 范围 | 本轮状态 |
|---|---|---|
| `cycle5_diagnostic_v1.json` | 24任务 × Full/No History，192请求cap、500,000 Tokens阈值 | 45/48完成，预算停止 |
| `cycle5_mechanism_v1.json` | 原72-cell比较 | 原完整D gate未通过，未执行 |
| `cycle5_mechanism_v2.json` | 使用完整事前配对子层的工程修订 | preparation API中断 |
| `cycle5_mechanism_v3.json` | 相同十二成员六条件的完整恢复 | 72/72完成 |

A-v2/v3均使用400请求cap、750,000 Tokens停止阈值、6000 UTF-8 bytes表示上限、每cell最多四次执行调用；v3仅改变运行身份，不拼接旧准备产物。完整方案与成本见 [第五轮总报告](../results/analysis/research_cycle5_20261004/analysis.md)。
