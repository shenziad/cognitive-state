# 多次中断续做：小型预注册设计 v0.1

状态：构造、离线协议审查及 2026-10-02 真实模型运行完成（32/32）。历史边界、世界继承、轨迹、评分及实际 Token 已复核；结果见 [连续交接分析](../results/analysis/longitudinal_v01_20261002/analysis.md)。两条 CS 链均在首次提取失败，没有测得其多轮语义演化；协议及旧结果保留，后续修订使用新版本。

## 要回答的问题

当旧历史真正被丢弃，Agent 能否仅依靠上次保留的表示及新证据，在连续四个交接位置维持目标、更新被推翻的信念，并避免重复已完成动作？

这是一项两场景的小型机制试验，不是自然任务的长期能力基准。

## 固定条件

- 两个场景 × 四个交接位置 × 四条件 = 32 个交接结果，八条独立 chain。
- 条件：Full Context、任务导向普通 Summary、自动 Cognitive State、No History。
- 每个条件独立初始化同一场景的世界；同一 chain 内世界状态真实继承，阶段失败也不重置到正确状态。
- 每个位置最多六个执行调用。压缩条件各额外一次表示更新，理论最大 208 次响应；配置硬上限 320 次请求。
- 一次重复，temperature = 0；随机种子仅控制条件顺序。
- `deepseek-ai/DeepSeek-V4-Flash`，SiliconFlow OpenAI-compatible SDK。
- 使用 `prompts/v0.3` 的共同执行器及竞争性表示提示；Summary 与 CS 均为 2200 UTF-8 bytes 上限。该上限不是模型 Token 数。
- 不使用人工或候选参考状态，不训练模型，不隐式重试，不回退完整历史。

## 真实的历史边界

| 条件 | 本次执行输入 | 下次表示更新能读取的材料 |
|---|---|---|
| Full Context | 所有已公开历史与当前事件 | 累计公开历史、实际动作及实际观测、新事件 |
| Summary | 更新后的普通摘要 | 上次摘要、上一段真实动作及工具观测、新事件 |
| Cognitive State | 更新后的 G/W/F JSON | 上次 CS、上一段真实动作及工具观测、新事件 |
| No History | 原始共享公开目标及本段事件 | 原始公开目标及下一段事件；不保留之前更新与观测 |

压缩条件第一次更新读取原始目标与第一个阶段事件，此后原始材料从可用上下文中删除。没有可供压缩条件恢复原历史的归档字段。新执行器也只获得本次表示、公共工具定义和“继续任务”的共同指令。

原始 JSON 历史仍保存到研究结果中供人工审查，它不进入后续模型输入。

No History 是恢复基线，会失去此前公开的目标修改。因此它的失败可能来自 G、W 或 F，不能作为纯 W/F 消融。Full/Summary/CS 之间的竞争才是主比较。该基线没有每段从隐藏评分条件重建最新目标的额外优势。

## 两个场景与因果关系

### release_workflow

1. 公开诊断确认 cache；修复 cache。初始 public / remote 许可已公开。
2. 更正诊断将当前根因改为 queue；如果旧 cache 修复确实已接受，它仍有效，新消息不证明修复已执行。修复 queue 并验证 A/B。外部世界只更新诊断确认标志，已执行修复状态真实继承。
3. 用户取消公开交付，private 与 offline 成为硬要求；装包及选择传输。
4. 新事件只通知签名服务 ready，沿用最新要求交付；不重述 private/offline。保留之前的修复、测试及装包状态，不能重复。

### archive_workflow

1. left 只是 0.7 信念；花一 credit 查看现场诊断，证据推翻 left 并确认 right；再修复 right。
2. 只提交异步任务，真实工具返回 submitted / not complete，不提前轮询。
3. 外部公开事件使 backend ready；必须用真实上次提交状态轮询，并验证 A/B。ready 事件本身不证明已提交。
4. 按之前确认并修复的 branch 封存；不重述 right，不重复已验证阶段。

阶段外部 patch 仅包含公开更正诊断或 backend ready 对应状态。它不补写未执行动作、目标答案或未来工具结果。

操作目录提供名称、说明、credit 价格，不提供目标评分、旧诊断、最新用户 policy 或隐藏世界状态。最终 `finish` 只返回收到的状态，不返回得分。

## 评分和成本

- 每位置任务成功：实际目标状态、完成声明、阶段约束及 budget 全部满足；工具格式错误保留并计该段失败。
- 整条 chain 成功：四段全部成功；中间失败后继续的真实状态不能掩盖之前失败。
- 逐位置查看未满足状态检查、policy violations、工具格式错误、重复动作尝试和 unavailable resources。
- 重复动作尝试额外依据动作前真实状态统计，包括被 budget 拒绝的重复尝试；`ContinuationEnvironment` 原计数同时保留。
- 所有表示更新和所有执行调用的 provider input/output Tokens 都计入实际成本。failed provider 请求的总成本标为 unknown，不把已报告部分当总成本。
- 表示解析失败会终止该 chain，后续位置保存为 skipped，计 assigned chain 失败；其它独立 chain 可继续。provider/transport 失败立即停止整次运行。wrapper 和 SDK 都在发送请求前检查上限，触发本地上限时标明未发送并保留已知成本。
- 因表示错误而 skipped 的 chain 不公布对 Full 的节省比例。正常执行而失败的低成本 chain 同时显示失败表现，不能解释为能力保持。

未满足状态检查只是行为漂移代理；它不能单独证明表示遗漏了信息。原因需要人工读模型表示和实际动作。

## 保存与复核

`scripts/run_longitudinal_experiment.py` 保存每段公开 update 输入、表示、完整实际 fixture、模型 messages/response/usage、真实 trace、最终世界、下一段实际可用历史；config、输入、prompts、源码副本及 SHA256 也保存。attempted handoff 与取得 executor response 的 execution_started 分开；未进入执行的表示失败及 skipped 段，其行为诊断为 null，任务成功仍记 false。

`scripts/analyze_longitudinal_experiment.py` 只读原始结果，检查 frozen inputs/prompts、跨段世界、历史删除边界、实际模型输入、工具轨迹、评分及报告的 Tokens，输出新的分析目录。

```text
python scripts/run_longitudinal_experiment.py --config configs/exp003_longitudinal_pilot.json --output results/raw/exp003/<new-run> --progress
python scripts/analyze_longitudinal_experiment.py --run results/raw/exp003/<new-run> --output results/analysis/exp003/<new-analysis>
```

两条 chain、四个交接、一次重复不足以评估统计显著性或自然长任务泛化。已提供的 scripted client 仅验证协议，不是模型实验结果。
