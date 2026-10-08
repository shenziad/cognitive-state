# 多次中断续做试验：描述性结果

原始运行：`D:\Develop\Cognitive State Representation for Long-Horizon LLM Agents\cognitive-state\results\raw\exp003\longitudinal_v01_20261002`

32 个交接组合 = 两个场景 × 四个交接位置 × 四条件；每条件两条独立 chain。

完整运行：True；历史边界、世界状态、轨迹、评分和实际 Token 统计复核通过。

| 条件 | 成功交接 / 8 | 全部四段成功的 chain / 2 | API Tokens | 重复动作尝试 | 工作区 credits |
|---|---:|---:|---:|---:|---:|
| cognitive_state | 0 | 0 | 1407 | 0 | 0 |
| full_context | 5 | 1 | 41570 | 0 | 15 |
| no_history | 5 | 0 | 37570 | 2 | 13 |
| summary | 7 | 1 | 33835 | 0 | 15 |

## 逐链成本（含更新及执行）

| 场景 | 条件 | chain 成功 | API Tokens | 对 Full 降幅 |
|---|---|---:|---:|---:|
| release_workflow | no_history | False | 19595 | -11.9% |
| release_workflow | full_context | False | 17510 | 0.0% |
| release_workflow | cognitive_state | False | 696 | 不可用 |
| release_workflow | summary | False | 15494 | 不可用 |
| archive_workflow | full_context | True | 24060 | 0.0% |
| archive_workflow | no_history | False | 17975 | 25.3% |
| archive_workflow | summary | True | 18341 | 23.8% |
| archive_workflow | cognitive_state | False | 711 | 不可用 |

## 按交接位置成功数量（各位置两场景）

| 条件 | h1 | h2 | h3 | h4 |
|---|---:|---:|---:|---:|
| cognitive_state | 0 | 0 | 0 | 0 |
| full_context | 2 | 1 | 1 | 1 |
| no_history | 2 | 2 | 1 | 0 |
| summary | 2 | 2 | 2 | 1 |

## 限制与解释边界

- Two synthetic chains, four handoffs and one repetition; not evidence of natural long-horizon generalization.
- No-history deliberately loses prior public goal revisions and tool evidence; its failures are not a W/F-specific ablation.
- Unsatisfied goal checks and repeated actions are behavioral drift proxies, not semantic proof of state omission.
- Full/Summary/CS share new events and tools. Summary and CS update only retained representations plus genuinely new observations.
- Costs include every representation update and executor call. Local size is UTF-8 bytes, not model tokenization.
- Cost reductions are suppressed for chains with representation/executor errors or skipped handoffs; low-cost behavioral failures remain visible alongside their success outcomes.
- Workspace credit budgets differ by checkpoint; credit totals do not represent monetary API cost.
- Candidate reference states are absent. Completion claims do not expose scoring results to the model.

本报告不自动判断假设成立。`diagnostics.json` 提供各段失败状态检查、动作成本和原始证据路径，需结合轨迹人工判断原因。

## 独立轨迹审阅与解释

### 必须先区分协议可用性与续做能力

Cognitive State 的 **0/8 是 assigned 协议分母**：两条 chain 都在第一次提取失败，其余六段保存为 skipped；**0 次 executor 调用、0 段执行**。release 的输出缺少最后一个根对象闭合括号；archive 的 JSON 额外包含 `budget_counter` 根字段。两次均返回 `finish_reason=stop`，输出本身分别只有 1239/1500 bytes，未触及 2200-byte 上限。它们是生成/协议可靠性失败，尚未观察到 CS 的多次更新、状态漂移或长期行为表现。表中的 CS 重复动作/credit 聚合为零，实际“观察到的行为段数”同样为零，不能解读成没有重复动作。

Summary 的 release 第四段输出 **2461 bytes，超过 2200 bytes 上限 261 bytes**，没有进入 executor。文本仍明确保留 private audience、offline 硬约束及已接受修复、测试、装包；这里没有“忘掉目标”的证据。archive Summary 四段均成功，实际保留了 right 诊断、提交但未完成的 job、完成的 A/B 验证以及 pending seal，说明在这一个场景中，连续只读保留表示和新消息可以维持续做。

### 逐段失败的依赖关系

- Full release h2 只执行 `repair_queue` 就 `finish completed`，未完成请求中的 A/B 测试。h3 的装包前置条件失败、恢复超预算，h4 仍缺测试、装包及交付，均继承真实未完成的世界。不能把这三段当作三个独立的历史信息遗忘事件。
- No History release h4 连续六次读 catalog，未交付；输入确实缺少之前更新的 private/offline policy。该基线同时移除了目标修改与实际进度，不是纯 W/F 消融。
- No History archive h3 两次重复 `submit_archive`，真实世界已存在 `job_submitted=true`，因此均收到通用的 `Operational precondition not met` 错误，每次花一 credit；它未轮询或验证。h4 又只读 catalog，且真实世界仍有未完成 job/验证，并缺少此前确认的 right branch，不能单独隔离哪种信息导致失败。理论上不同的无历史策略（例如先 poll）可能成功，当前结果只描述实际策略。
- Summary release h2 曾尝试不存在的 `test_stage_A`，之后查询 catalog 并正确完成 A/B。该 well-shaped 错误不会触发 JSON 格式失败，但额外消耗一次响应，已计入成本。

### 实际调用与缓存成本

独立复核了 **32 个结果、102 个唯一 response ID**；manifest 的请求数、响应数与保存的调用一致，无 provider/transport 错误或未知请求 usage。共 **114,382 provider Tokens**：input **110,191**、output **4,191**；input 中 **29,696** 为 cached Tokens，reasoning Tokens 为 0。包括 10 次表示更新响应及 92 次 executor 响应。三次表示错误与六段 skipped 均保留；真正执行了 23 段。

唯一两条件均完整成功的比较是 archive chain：

| archive 条件 | 总 Tokens | 未缓存 input | cached input | output | 响应数 | 累计 API latency |
|---|---:|---:|---:|---:|---:|---:|
| Full Context | 24,060 | 12,835 | 11,008 | 217 | 15 | 20.71 s |
| Summary | 18,341 | 14,655 | 2,304 | 1,382 | 19 | 45.39 s |

Summary 的 **总 Token 降幅为 23.77%（5,719 Tokens）**，包含全部更新与执行。该数值只适用于这一条成功匹配链。Summary 的未缓存 input 反而增加 1,820，output 增加 1,165，累计请求 latency 也更长。没有测量实际账单金额或缓存/input/output 价格权重，因此**不能把 23.8% 写成实际 API 费用或时间下降**。CS 首段终止，以及 release Summary 未进入最后执行，都不计“省钱优势”。

### 复核范围与下一步

输入、提示及源码副本 SHA256 全部匹配；按保存动作重放全部工具轨迹并独立按 rubric 核对任务成功；真实跨段世界、compressed retained-only 边界、Full 累计历史及 No History 当前事件策略一致。102 个请求的模型 messages 未包含评分 `rubric` 或 `target_state` 字段。详细分段原因、实际成本和证据哈希见 `interpretation.json`。

下次先单独校准严格 JSON/schema 和表示预算合规性，随后再评估 CS 的多段更新行为。保留“实际操作接受证据”与“Agent 自称 finish”的区别。两场景、四次交接、一次重复不足以支持自然长期任务泛化；完整 chain 的重复与缓存感知计费仍需要追加测量。
