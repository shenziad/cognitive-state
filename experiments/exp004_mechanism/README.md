# 历史必要性与最小机制对照

本目录的代码属于第五轮。放在 `src/` 之外，以保留第四轮冻结资产。研究规范见 [cycle5_protocol_v01](../../docs/cycle5_protocol_v01.md)，历史必要性输入见 [history_diagnostics_v01](../../datasets/history_diagnostics_v01/README.md)。

## 比较范围

先做 Full / No History 的历史必要性诊断，再比较 Full、Full+planner、强摘要 S1、整理后强摘要 S2、自动 CS1、同信息 CS-text。十二配对成员来自六相关基础工作流；这些是助手构造的已知开发任务，六组共享旧事实决定不可覆盖二选一提交的机制，不是六种长期更新机制。

CS-text 保留 CS1 所有语义、字段路径、来源和结构，确定性可逆，不是普通摘要。它只检验本次 JSON 与字段路径文本编码的差异。

## 运行版本与中断

- v1 D 因事前 Token 停止阈值结束，45/48 cells 保存。事前配对层 24 cells 完整，原完整 gate 保持 failed。
- [v2 预算修订](../../docs/cycle5_budget_amendment_v2.md)使用全部事前配对层及原 D 完整账本回放作为 A 的工程进入条件。A-v2 在预处理阶段因 API 错误停止，31/72 preparation，无行为比较。
- [v3 完整恢复](../../docs/cycle5_recovery_v3.md)建立新目录，重新准备全部 72 分配，不拼接旧表示；继承相同模型、任务、提示和预算。若再次中断则停止并保留，不自动再次重启。

## 文件入口

| 文件 | 用途 |
|---|---|
| `conditions.py` | 六条件预处理、公共输入投影、CS-text 无损转换 |
| `runtime.py` / `runtime_v2.py` / `runtime_v3.py` | 各冻结版本运行器、来源优先审阅、实际账本与回放审计 |
| `budget_bridge.py` | 保留原 D 未完成状态的事前配对子层工程审计 |
| `reporting.py` | 完整运行的补充描述性成本和来源交叉分析 |

## v3 显式分阶段入口

以下命令会发出真实请求，必须具备已经冻结的执行资产和本地环境凭据。不能对已存在或中断目录再次 prepare；示例目录仅作演示。

```bash
python scripts/run_cycle5_v3.py --phase prepare --config configs/cycle5_mechanism_v3.json --run results/raw/cycle5/new_run
python scripts/run_cycle5_v3.py --phase review_packet --run results/raw/cycle5/new_run --output results/analysis/new_run/source_packet.json
```

review packet 只包含公开历史、接口和实际表示。为全部 60 条填写 reviewer、六维 assessment 与 evidence_notes，并保存审阅文件；不能修改输入/表示，不能从当前行为或隐藏 fixture 标注，不能依据错误筛除或语义修复状态。

```bash
python scripts/run_cycle5_v3.py --phase execute --run results/raw/cycle5/new_run --review results/analysis/new_run/source_review.json
python scripts/analyze_cycle5_v3.py --run results/raw/cycle5/new_run --output results/analysis/new_run_report
```

实际调用全账本只计共享 CS 提取一次，CS1 与 CS-text 独立部署成本各包含该提取。中断/服务探测成本单列，未知用量不能填零。完整运行的条件分母各 12，基础配对组数为 6，不能把 72 cells 当作 72 个独立任务。
