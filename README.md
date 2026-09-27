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

## Cognitive State v0.2

状态由 \(CS=(G,W,F)\) 组成：

- **G — Goal State**：目标、成功标准、约束与偏好。
- **W — World Model / Working State**：已确认事实、带不确定性的信念、任务假设。
- **F — Frontier State**：当前焦点、信息缺口、下一步行动。

定义及示例见 [Cognitive State 定义](docs/cognitive_state_definition.md)。

## 第一阶段实验

对同一段历史和同一未来任务比较三种输入：完整历史（Full Context）、普通摘要（Summary）、结构化 Cognitive State。评价任务成功率、最终目标完成度、工具使用正确性、决策一致性及 Token Reduction；完整方案见 [实验设计](docs/experiment_design.md)。

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
- `datasets/`：数据说明；`results/`：JSON 结果说明；`scripts/`：未来运行脚本。

## 复现约定

需要 Python >=3.10。使用 `pyproject.toml` 管理项目，当前没有第三方运行时依赖。每次实验必须保存实际使用的配置快照；每次运行结果必须保存为 JSON，并记录任务 ID、条件、指标、Token 用量和配置版本。原始结果可放在 `results/raw/`，该目录不提交。API 凭据放在环境变量或 `.env`，不得写入配置或结果。

当前仓库是第一阶段研究骨架，接口尚未接入具体 LLM 服务或 benchmark，不应把占位接口当作已有实验结果。
