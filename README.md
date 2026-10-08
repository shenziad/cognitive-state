# Cognitive State Representation for Long-Horizon LLM Agents

本项目研究一种可外部保存、可供 Agent 继续行动的紧凑状态表示 **Cognitive State**。第一阶段建立可复现的 API-based LLM 实验框架，不训练模型。

## 核心研究问题

现代 LLM Agent 往往依赖不断增长的历史 Context：

\[
C_t = \{x_1, x_2, \ldots, x_t\}.
\]

随着任务持续，Context 长度增加、Attention 可能被无关内容稀释、Memory 检索成本上升，且大量历史信息与当前任务无关。人类通常不会逐字保存完整经历，而会维护与当前任务有关的认知状态。

本项目研究能否从历史 \(H_t\) 学习或生成紧凑的 Cognitive State：

\[
CS_t = f(H_t), \qquad |CS_t| \ll |H_t|,
\]

并使未来任务 \(T\) 上的行为能力满足：

\[
\operatorname{Behavior}(H_t,T) \approx \operatorname{Behavior}(CS_t,T).
\]

这里的等价性指未来任务的行为能力近似一致，**不是文本输出完全一致**。关键问题是：**什么信息构成 Agent 当前可继续行动的最小认知状态？** 因此 Cognitive State 不是普通摘要，也不以文字压缩率作为唯一目标。

## Cognitive State v0.3 设计与实现

状态由 \(CS=(G,W,F)\) 组成：

- **G — Goal State**：有来源的当前目标、可观察成功标准、约束与偏好。
- **W — World Model / Working State**：关键判断及依据、有效范围、重要操作的实际阶段和资源。
- **F — Frontier State**：尚未完成的义务、影响选择的未决问题，以及可选的候选行动。

2026-10-03 根据已有结果修订设计，并按用户后续授权实现最小运行器、恢复可靠性预检。核心规则是：判断有依据、操作阶段由真实观测推进、已解决问题只有在明确触发条件下重新打开。定义见 [Cognitive State v0.3](docs/cognitive_state_definition.md)，设计审阅见 [修订说明](docs/design_revision_v0.3.md)，另有 [更新协议](docs/state_update_protocol_v0.3.md) 和 [前后状态示例](docs/examples/cognitive_state_v0.3/README.md)。

v0.3 的独立实现、门槛、首次失败及修订过程见 [实现与第三轮协议](docs/v03_implementation_and_cycle3.md)。旧 Python 入口、状态 Schema 和历史实验继续使用 v0.2；旧定义已[归档](docs/versions/cognitive_state_v0.2.md)。执行 prompt v0.3 与状态设计 v0.3 是不同版本，旧配置及成绩未改写。

## 第一阶段实验

对同一段历史和同一未来任务比较三种输入：完整历史（Full Context）、普通摘要（Summary）、结构化 Cognitive State。评价任务成功率、最终目标完成度、工具使用正确性、决策一致性及 Token Reduction；完整方案见 [实验设计](docs/experiment_design.md)。

当前 exp001 已提供 12 个合成配置修复任务，并加入待审核候选状态作为诊断条件。审阅请从 [审阅指南](docs/review_guide.md) 开始，实施规则见 [试验协议](docs/exp001_protocol.md)。

首轮后新增 **8 组区分性配对任务和 2 个正对照**：检验目标更新、软硬要求、事实/信念/假设、在途调用、完成进度和信息缺口。2026-10-02 已完成真实模型预检（6 个任务 × 4 条件，24 组合）及完整单轮（18 个任务 × 4 条件，72 组合）。任务与候选参考状态仍待独立研究者审核，参考状态全部为 `pending`；审阅入口见 [任务设计](docs/discriminative_task_design.md) 和 [任务清单](datasets/exp001/discriminative_v0.1/README.md)。

```text
Historical Context
       ↓
State Extractor (API-based LLM)
       ↓
Cognitive State JSON
       ↓
Agent Executor
       ↓
Evaluation (JSON results)
```

后续才考虑自动 state extraction、state prediction、state evolution 和 learned compression。

## 仓库布局

- `docs/`：定义、问题、假设、实验设计及相关工作范围。
- `src/state/`：状态表示、提取与校验接口。
- `src/agents/`：执行器接口。
- `src/evaluation/`：指标及 benchmark 接口。
- `experiments/exp001_*` 等：逐实验方案与本地配置。
- `configs/`：模型、temperature、benchmark 和 prompt version 的配置。
- `datasets/`：数据说明；`results/`：JSON 结果说明；`scripts/`：构造、运行与后处理脚本。

## 复现约定

需要 Python >=3.10。使用 `pyproject.toml` 管理项目；离线 mock 不需要第三方运行时依赖，真实 SDK 调用使用可选 `[api]` 依赖。每次实验必须保存实际使用的配置快照；每次运行结果必须保存为 JSON，并记录任务 ID、条件、指标、Token 用量和配置版本。原始结果可放在 `results/raw/`，该目录不提交。API 凭据放在环境变量或 `.env`，不得写入配置或结果。

当前仓库包含可运行的受控试验框架、通用 API 适配器和离线 mock。默认运行只验证流程，不能证明 Cognitive State 的真实模型效果。

## 离线运行

在仓库根目录使用 Python >=3.10：

```bash
python scripts/run_experiment.py
python -m unittest discover -s tests -v
```

mock 无需第三方运行时依赖或 API key。结果保存在新建的 `results/raw/exp001/<UTC时间>/` 目录，包括实际配置、输入/提示副本、调用记录与 JSON 汇总。真实 API 配置及安装见 [exp001](experiments/exp001_context_equivalence/README.md)。

SiliconFlow OpenAI SDK 接入已配置为 deepseek-ai/DeepSeek-V4-Flash，读取根目录 .env；说明及首次连接状态见 [接入记录](docs/siliconflow_integration_20261002.md)。原配置修复任务的描述性分析入口为 `scripts/analyze_experiment.py`，区分性任务使用 `scripts/analyze_discriminative.py`；后处理只读冻结运行记录，遇到服务中断不发布性能结论。CLI 用法见 [脚本说明](scripts/README.md)。

## 首轮真实模型结果（2026-10-02）

12 个合成任务 × 4 种输入条件全部完成，成功率均为 12/12。自动 CS 的首次输入 Token 配对平均减少 41.0%，计入提取和全部执行后减少 9.3%；普通摘要分别减少 53.9% 和 27.3%。本轮没有显示 CS 优于摘要，任务存在天花板效应，也没有检验长期状态演化。详细成本、轨迹案例、字段问题与后续方案见 [首轮分析](results/analysis/exp001_siliconflow_round1_20261002/analysis.md)。

## 区分性任务真实模型单轮（2026-10-02）

完整 72 组合中，全部 18 个任务的成功数分别为 Full Context **16/18**、Summary **16/18**、自动 CS **15/18**、候选参考状态 **18/18**。16 个配对实例中，前三条件均为 **14/16**；两个 controls 中 Full Context、Summary 均为 **2/2**，自动 CS 为 **1/2**。候选参考状态仍为 `pending`，不能作为人审 gold。

这只是一轮小型合成续做任务的描述结果，不能证明 H1–H3 或 CS 优于摘要。分组成功、A/B joint success、配对变化、Token 成本及逐任务诊断见 [区分性单轮报告](results/analysis/exp001_discriminative_round1_20261002/analysis.md)。

## 第二轮：公平比较、预算与连续交接（2026-10-02）

已按冻结计划完成共同执行器校准、公平续做、预算/消融、连续四次交接，另完成一个失败后选取的局部诊断。**当前自动 CS 未显示优于任务导向普通摘要；主要瓶颈是表示协议可靠性和新增无依据的确认需求。**

| 实验 | Full Context | Summary | 自动 CS | No History |
|---|---:|---:|---:|---:|
| 公平续做主任务（每条件 12 个） | 10/12 | 11/12 | 10/12 | 6/12 |
| 连续交接（每条件 8 段） | 5/8 | 7/8 | 0/8 | 5/8 |

连续交接的 CS 0/8 来自两次首次提取错误和六个 skipped 段，没有启动执行器，不能判断长期状态漂移。Summary 与 Full 都完成 1/2 条完整链；Summary 在双方完成的 archive 链上计入更新成本后少用 23.8% 总 Tokens，但未缓存输入及累计调用耗时更高，实际金额未测量。

1400 UTF-8 bytes 预算下，主任务 Summary 成功 12/12，CS 为 2/12、其中 9 次表示失败；三个消融仅在 3 个主任务上获得有效源表示，删除字段后仍有跨字段语义残留。单案例的 5 个局部改动均未消除先查询 ledger 的行为，不能把问题归因于单个 Frontier 字段。

详情及下一步顺序见 [第二轮总报告](results/analysis/research_cycle2_20261002/analysis.md)，机器汇总见 [cycle_summary.json](results/analysis/research_cycle2_20261002/cycle_summary.json)。这些仍是小型合成、单轮探索结果，任务待研究者审核，没有确认 H1–H3。

## 第三轮：v0.3 最小实现与预检（2026-10-03）

已完成最小运行器及两版真实预检。首版 CS 成功 15/24、Full 24/24；修订版 CS 24/24、Full 23/24。修订版 Full 有一次执行旧目标后错误完成，CS 状态审阅还发现一次无对应完成回执的阶段升级，完整门槛未通过，因此四条件比较和四次交接未运行。两版共 228 次响应、349,224 Tokens；短历史上未体现成本节省。

优先审阅[第三轮总报告](results/analysis/research_cycle3_20261003/analysis.md)、[逐状态审阅](results/analysis/cycle3_preflight_r2_20261003/semantic_review.json)和[实现说明](docs/v03_implementation_and_cycle3.md)。全部失败保留，不据此宣称优于 Summary 或具有长期优势。

## 第四轮：生命周期与四条件恢复实验（2026-10-03—04）

[v0.3.1 生命周期规范](docs/operation_lifecycle_v0.3.1.md)明确 submission 请求返回、job 终态与目标验收的区别。[第四轮协议](docs/cycle4_protocol_20261003.md)将设施/编码可靠性门槛与模型行为、状态语义成绩分开；后两者保留为结果，不以零错误筛选进入比较。所有压缩条件采用相同编码有效性阈值。

`cycle4-execution-v2` 已实现并冻结，117 项离线测试通过。原预检在 19/96 处因 API 错误中断；按[独立恢复计划](docs/cycle4_recovery_v1.md)保留原轮，从头完成三个阶段，不拼接部分记录、不调整提示、不选择性重跑。

| 阶段 | Full Context | Summary | CS v0.2 | CS v0.3.1 |
|---|---:|---:|---:|---:|
| 预检 | 23/24 | 24/24 | 22/24 | 22/24 |
| 已知任务回归 | 14/14 | 14/14 | 12/14 | 14/14 |
| 连续四次交接 | 8/8 | 7/8 | 8/8 | 8/8 |

138 份压缩表示全部首次编码有效；来源审阅和实际输入、评分、世界继承、调用账本回放均完成。编码有效不代表语义正确：预检 35 份状态有具体来源错误，其中 32 份仍行为成功。

archive 链中 Summary 第三段丢失早期确认的 right 分支，第四段实际 blocked；Full 和两版 CS 保留身份并正确封存。两版 CS 均完成 2/2 整链，Summary 为 1/2。但计入维护与执行，连续实验 v0.2、v0.3.1 总 Tokens 比 Full 分别高 20.0%、60.0%，尚未实现总成本下降。小型已知任务和助手审阅不能确认普遍优势或 H1–H3。

优先审阅[第四轮总报告](results/analysis/research_cycle4_20261004/analysis.md)和[连续交接案例](results/analysis/cycle4_longitudinal_recovery_v1/semantic_behavior_notes.md)。整个流程包含原中断轮与探测，共 629 次尝试、1,320,918 已知 Tokens，另有一次未知用量，完整总量仍未知。执行资产与历史冻结文件保持原样，见[执行说明](docs/cycle4_execution_v2.md)和[执行清单](docs/freezes/cycle4_execution_v2.json)。

## 第五轮：历史必要性与六条件对照（2026-10-04）

从[12 条开发候选工作流](datasets/independent_workflows_v01/README.md)选取 checkpoint，并新增[六组历史批准值反事实配对](datasets/history_diagnostics_v01/README.md)。原 Full/No History 诊断因事前预算阈值停止于 45/48 cells；完整的事前配对子层为 Full 12/12、No History 5/12，双成员全成功分别为 6/6 和 0/6。原完整 gate 保持 failed。

按公开工程修订和完整恢复计划完成六条件 72-cell 比较：Full、Full+planner、强摘要 S1、两步强摘要 S2、CS1、同信息 CS-text 均为冻结检查点评分 **12/12**。60 份来源审阅先于全部行为执行，所有来源问题保留，当前任务仍有天花板效应。

CS1 的执行输入比 Full 少 24.4%，计入提取后总 Tokens 却高 30.1%；S1 对应为少 34.7%、总量高 12.1%。未观察到 CS 行为优势或端到端节省。另发现附带的证据/引用/脱敏等保留要求没有独立建模或评分，满分不代表完整用户目标达成。

审阅入口：[第五轮总报告](results/analysis/research_cycle5_20261004/analysis.md)、[成本分解](results/analysis/cycle5_mechanism_v3_supplement_20261004/cost_and_source.md)、[60 份来源审阅](results/analysis/cycle5_mechanism_v3_sources_20261004/source_review.json)。本轮共 344 次尝试、1,198,707 已知 Tokens，另有一次未知用量；中断轮和恢复轮不拼接。

[机制与完整成本草案](docs/mechanism_and_cost_plan_v01.md)中的语义消融和多轮成本曲线尚未执行。下一步先建立用户目标—可观察世界—评分的对应关系，补上有实际行为后果的生命周期、未知提交结果和证据失效任务，再另立版本检验最小状态。六组当前配对共享一个机制，不能视为独立长期泛化验证。

## 从远端恢复完整实验记录（2026-10-08）

代码、数据、协议、分析报告及原始实验归档均可随仓库获取。`results/raw/` 仍被忽略；其全部实验记录保存在 [归档](results/archives/README.md)，从仓库根目录执行：

```bash
python scripts/restore_experiment_records.py
```

恢复前会核验归档及逐文件 SHA256，不覆盖不同内容。`.env` 和环境凭据需在 Ubuntu 本地配置。历史 gate/review 保存的 Windows 绝对路径仍需单独映射后复核，完整 Ubuntu 行为回放尚未验证。
