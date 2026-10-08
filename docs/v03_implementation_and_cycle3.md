# v0.3 最小实现与第三轮实验

2026-10-03，用户授权推进实现、可靠性预检、通过门槛后的比较。该授权恢复了此前暂停的实验。本轮仍不训练模型。

## 实现边界

- `src/state/v03.py`：minimal-1 状态解析、来源类别、引用和预算检查；保留用于复核首次失败。
- `src/state/v03r2.py`：minimal-2；明确区分用户要求、运行时资源和可信公共工具契约，反馈包含出错字段路径。没有自动移动字段、截断状态或补写事实。
- `src/evaluation/evidence_interface.py`：所有条件共享公开的操作前提、效果定义和真实效果回执。工具定义不是已经执行的证明；未读取的 observation 值和评分目标仍隐藏。
- `scripts/run_v03_cycle_r2.py`：状态更新只读取实际保留表示、新观测和当前公共接口；保存结构变更记录、全部修复和实际请求账本。结构差分不等于已证明问题被正确解决。
- `docs/schemas/cognitive_state_v0.3r2.schema.json`：编码形状；动态来源、引用和资源规则由运行时另外检查。

局部校验不能证明语义真值。它不会检查模型是否真正理解证据、是否编造语义要求或把同一信息重复放在多个字段。因此进入比较还需要逐状态的来源审阅。该审阅由助手完成，不称为独立研究者 gold。

## 冻结设置

SiliconFlow `deepseek-ai/DeepSeek-V4-Flash`，temperature 0，禁用 thinking，max output 4096 Tokens。所有压缩条件采用 6000 UTF-8 bytes 上限、最多一次有记录的模型修复；执行最多六步。字节上限不是 Token 等预算。

| 阶段 | 分配组合 | 请求硬上限 |
|---|---:|---:|
| 首次预检 | 12 案例 × 2 条件 × 2 次 = 48 | 350 |
| 修订版预检 | 完整同规模；新标签、同六类模板 | 350 |
| 四条件续做 | 14 任务 × 4 条件 = 56 | 450 |
| 四次连续交接 | 2 场景 × 4 条件 × 4 段 = 32 | 260 |

预检门槛：v0.3 最终有效至少 23/24、任务成功至少 22/24，Full 成功至少 23/24；不得过早宣告完成或执行禁止/缺证据操作。语义审阅要求没有虚构已完成操作或新增硬性用户要求，最多两份状态出现无依据重开问题。

Full、任务导向 Summary、旧状态格式 CS v0.2、新状态 CS v0.3 共用新版接口。Summary 获得同样的证据/进度保留原则及修复机会。CS v0.2 条件保留旧提取提示，但使用本轮公共接口、预算和修复协议；不能把它称为旧整个系统的原样重跑。

所有比较输入此前已经审阅过，属于已知任务回归，不是未见任务测试。预检六类模板包括目标修订、接受但未完成、已完成、只有计划、假设被推翻、明示独立验证。

## 首次预检及透明修订

minimal-1 首次预检中 Full 24/24 成功，CS 15/24 有效且成功，未通过门槛。CS 首次有效 5/24，19 次修复后仍有 9 次表示失败：5 次 candidate_action 放到根部、1 次 frontier 放进 world、1 次非法 JSON、1 次 target 字符串、1 次有依据的工具契约约束被来源规则误拒。

这些结果保存在 [首次预检报告](../results/analysis/cycle3_preflight_20261003/analysis.md)，不能被后续结果替换。提示没有完整示范可选字段的嵌套位置，通用错误提示也不利于修复，属于此次实现需要承担的问题。

单独的 [minimal-2 修订计划](cycle3_r2_plan_20261003.json)在第二次调用前冻结：增加明确的嵌套示例及路径反馈，允许公共工具契约支持约束；门槛、预算、修复次数保持一致。重跑完整预检并更换标签/工作区值，但复用模板，不声称它是独立泛化验证。比较任务和连续交接尚未用于这些调试。

如果 minimal-2 再次失败，本轮停止在预检，不继续调门槛或反复调提示直到成功。若通过，审阅结果和原始结果 hash 共同解锁比较；代码、输入、配置、schema 或提示发生变化会使旧 gate 失效。

## 运行与复核

从仓库根目录使用已配置的 Python 环境；以下命令会产生真实 API 用量。凭据仅从 `.env` 或环境读取，日志不记录凭据。

```text
python scripts/run_v03_cycle_r2.py --config configs/cycle3_preflight_v03r2.json --output results/raw/cycle3/<new-preflight> --progress
python scripts/analyze_v03_cycle.py --run results/raw/cycle3/<run> --output results/analysis/<new-analysis>
python scripts/run_v03_cycle_r2.py --config configs/cycle3_regression_v03r2.json --gate <reviewed-gate.json> --output results/raw/cycle3/<new-comparison> --progress
python scripts/run_v03_cycle_r2.py --config configs/cycle3_longitudinal_v03r2.json --gate <reviewed-gate.json> --output results/raw/cycle3/<new-chain-run> --progress
```

API 错误立即停止当前运行，未知用量不记零；表示错误保留在分母，连续链表示错误后的段标为 skipped。全部实际调用、初次输出、修复及提取成本计入。比较是整个实现组合的探索结果，不能将提升归因于某一个字段。正式统计等价和自然长期泛化需要另行设计。

## 已完成结果与当前停止点

两版真实预检已结束；[第三轮总报告](../results/analysis/research_cycle3_20261003/analysis.md)汇总全部 228 次响应与 349,224 Tokens。minimal-2 CS 24/24 成功、首次有效 22/24；Full 23/24，其中一次过早完成。另有一份 CS 将 accepted 阶段写为 completed 而缺少对应回执。完整 gate 为 failed，比较和四次交接没有模型调用。以上比较命令仅说明接口，当前 gate 不能解锁。
