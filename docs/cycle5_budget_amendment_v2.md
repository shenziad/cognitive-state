# 第五轮预算停止后的 A-v2 工程 gate 修订

日期：2026-10-04。状态：**D 结束后的公开修订，A-v2 请求前生效须另行冻结**。这是新的探索性执行版本，不追溯修改 `cycle5-execution-v1`，也不将原 D 判为完成或原 gate 判为通过。元数据审查与来源 hash 见 [cycle5_budget_amendment_v2.json](cycle5_budget_amendment_v2.json)。

## 1. 原 D 的事实及修订原因

原 D 按冻结的 500,000 provider Tokens 停止阈值，完成 45/48 cells 后停止；113 个真实尝试均收到响应，已知总 Tokens 为 502,100，无 API 错误或未知用量。最后一次响应使累计用量跨过阈值，随后没有继续发送请求。这是事前预算规则的正常停止，不是模型行为失败触发的筛选。

缺少的是 `original_iw02_h4/no_history`、`original_iw06_h4/no_history`、`original_iw10_h2/no_history`；最后一项已产生三次执行响应，保存在 `interrupted_cell.json`，尚无完整 cell 结果。原 D 的完整 48-cell 比较 **未完成**，原 v1 gate **保持 failed**。不补最后三项，不拼接其他运行，不再次花费约 500,000 Tokens 重跑整个 D。

原协议在 D 之前已经单列六反事实 pair 的十二成员，并将它们全部固定为 A 的十二输入。D 中该事前子层的 Full/No History 共 24 cells 已完整记录。A 的输入、六条件、提示及预算不依 D 行为表现挑选或调整。因此允许另立 A-v2，以完整事前子层及整个原 D 账本的工程一致性作为新的进入依据。**改变的是进入 A 的工程完整性范围；变化发生在 D 之后，必须如实披露，不能称为原协议的完整执行。**

本修订审阅仅查看分配 ID、元数据、消息对应与文件 hash，没有读取或使用 task success/score 来决定子层。提案时 D 输出已经产生，故 A-v2 仍属于在已知开发运行之后建立的新执行版本；不把这次 gate 修订表述成 D 前的预注册判断。

## 2. 继承与变化

保持原先确定的 A：

- 全部 `hd01_a` 至 `hd06_b` 十二成员，来自六相关基础工作流；不删除任何失败成员。
- Full、Full+planner、S1、S2、CS1、CS-text 六条件，共 72 cells。
- 相同数据、评分、提示、表示预算 6000 UTF-8 bytes、至多一次编码修复、四次执行调用、planner/organizer 1024 输出 Tokens、其他步骤 4096 输出 Tokens。
- 相同 seed、顺序生成规则、模型、temperature、thinking 与工具/世界隔离。
- 批量预处理后完成全部 60 份来源审阅，才运行 A 执行器；来源错误不作为删样本或语义修复条件。
- 硬请求 cap 400，provider Tokens 停止阈值 750,000；共享 CS 真实调用只计一次，两种独立部署策略各包含源提取成本。

新增 A-v2 execution/config/release 身份及 gate：原先要求 D 全部 48 cells 完整，改为要求 **事前反事实子层 24 cells 完整，并回放原 D 所有已产生请求，包括中断 cell**。没有行为成功率、Full/No History 差异、来源零错误或 CS 优势阈值。

新版本路径：

| 资产 | 路径 |
|---|---|
| v2 运行器 | `experiments/exp004_mechanism/runtime_v2.py` |
| 原 D 到新 A 的工程审计 | `experiments/exp004_mechanism/budget_bridge.py` |
| v2 运行/分析入口 | `scripts/run_cycle5_v2.py`、`scripts/analyze_cycle5_v2.py` |
| v2 A 配置 | `configs/cycle5_mechanism_v2.json` |
| v2 冻结 | `docs/freezes/cycle5_execution_v2.json` |
| v2 子层 gate | `results/analysis/cycle5_diagnostic_v1_20261004/paired_scope_gate_v2.json` |

`runtime_v2.py` 从 v1 复制，仅改变 release 路径与进入准备的 gate 校验；v1 runtime/config/protocol/提示及全部 81 份冻结资产保持原字节。新的代码不能把旧 gate 改成 passed，也不能直接绕过 gate。v2 调用前重新产生工程 gate，与保存 gate 精确比较，并核对其 scope 与 v2 全部十二任务一致。

## 3. 新 gate 必须证明什么

1. 原 v1 冻结与快照未改变；旧 D 状态为 `aborted_token_threshold`，旧完整 gate 保持 failed，原 D 完整性为 false。
2. 子层恰好是 D 前 provenance/config 确定的十二反事实成员×两条件，共 24 cells；不依行为挑任务。
3. 所有完成 cell 的公开输入、实际请求、环境轨迹、最终 world、评分与成本索引可回放。六 pair 的真实 No History 首请求仍相同。
4. 原 D 的 113 个 incurred attempts 全部覆盖：110 个属于 45 个完整 cell，三个属于 `original_iw10_h2/no_history` 的中断 partial。中断的消息、response/metadata、trace、world 和 score 同样需核验；不得只丢弃 partial 后审查子层。
5. 113 个 response ID 唯一，来源是实际 API/SDK 与冻结模型；所有 input/output usage 已知，无 API 错误。请求 cap 和累计 Token 停止检查符合冻结规则。
6. 新 gate 保存旧 run 关键文件与旧 release 的 hash；之后若数据或原账本改变，重新核验不能通过。v2 资产另外冻结，且 A 预处理/执行在 v2 冻结前没有真实调用。

本次独立元数据检查已核实上述分配、用量、81 旧资产不变以及 110+3 的 attempt 覆盖；完整环境/评分回放由 `budget_bridge.py` 的独立工程审计负责。这里的元数据检查不代替评分回放，也不据任何成绩解锁 A。

## 4. 分母、费用及解释

原 D 继续保留 48 个分配的未完成事实，单列 45 个完成项、一个 partial 和两个未执行项；不把 45 当成完整 48 的替代结果。原十二候选层不作完整 Full/No History 主张。反事实 24-cell 子层可以单独作为它本来就事前声明的开发诊断报告，不能据此称原 D 全部通过。

A-v2 独立报告 72 个分配的全部结果及其新账本，不混入 D 作为 A 行为样本。整个研究活动的实际费用包括原 D 的 502,100 Tokens 与 A-v2 全部真实新请求；A 各策略部署成本另列，不把诊断 setup 的支出伪装成某策略执行费用，也不隐去它。

若 A-v2 再达到预算、出现 API/未知用量或设施失效，按同样规则停止并保留全部结果，不自动继续、补跑失败条件或扩大预算。重要正负结果直接报告。新的 gate 只能证明进入依据可审计，不证明 Cognitive State 正确、性能优越、成本更低或具有自然长期能力。

本版保留六 pair 共享一个“旧事实决定不可覆盖二选一提交”机制的限制，也保留助手构造、已知开发数据、单 checkpoint 与单次每条件的限制。后续若要改变任务难度、状态语义、提示或预算，须另立版本，不能写回本次继承的比较。
