# SiliconFlow 接入记录：2026-10-02

## 实现

- provider=openai_sdk 使用 OpenAI Python SDK，模型固定为 deepseek-ai/DeepSeek-V4-Flash。
- base_url=https://api.siliconflow.cn/v1；Chat Completions 路径为 /chat/completions。
- 读取 Git 仓库根目录 .env，不覆盖已存在的环境变量。该文件实际变量名为 apikey，因此配置引用 api_key_env=apikey；变量名不包含密钥值。
- .env 已被 .gitignore 忽略且未跟踪；没有把密钥写入源码、配置、报告或请求日志。
- SDK 禁止自动重试；服务/网络错误停止轮次并保存中断状态；错误正文只用于生成允许列表中的诊断分类，不保存原文。
- 统一 temperature=0、max_tokens=2048、enable_thinking=false、最多 8 个行动步骤。
- 表示上限为 2200 UTF-8 bytes，不冒充 DeepSeek Token；真实输入/输出成本取服务 usage。

官方协议参考：[SiliconFlow Chat Completions](https://docs.siliconflow.cn/docs/api/chat-completions-post)。SDK 参数见 [API 接入说明](api_adapter.md)。

## 首次连接结果（充值前）

两个任务的预检计划 8 个组合。首个 Full Context 请求返回 HTTP 402，轮次立即停止，没有模型响应。随后使用最多 16 输出 Token 的一次诊断请求，服务返回错误码 30001，消息分类确认为 insufficient_balance（账户余额不足）。

共进行了两个被拒绝的真实请求，没有进行完整的 12 任务轮次。服务没有返回 Token usage，因此不能报告实际消耗量或成功率，也不能检验 H1–H3。它是账户计费阻塞，不是状态提取或任务能力失败。

原始轮次保留在 results/raw/exp001/siliconflow_smoke_20261002，脱敏诊断在同目录父级 siliconflow_diagnostic_20261002.json。原始旧版本汇总含初始化环境的机械评分；[分析报告](../results/analysis/exp001_siliconflow_20261002/analysis.md) 明确将不完整轮次的性能置为 null，禁止将该分数当作模型结果。

## 配置与复现

- [两个任务预检配置](../configs/exp001_siliconflow_smoke.json)：最多 68 次请求。
- [完整 12 任务配置](../configs/exp001_siliconflow.json)：48 个组合，最多 408 次请求；各条件一次重复。
- 请求数上限只是技术限制，不是人民币预算。首次尝试的 SDK 成功响应为 0；充值后的运行记录见下节。

```bash
python -m pip install -e ".[api]"
python scripts/run_experiment.py --config configs/exp001_siliconflow_smoke.json --progress
python scripts/run_experiment.py --config configs/exp001_siliconflow.json --progress
python scripts/analyze_experiment.py --run results/raw/exp001/<新轮次目录> --output results/analysis/<新分析目录>
```

输出必须使用新目录，以保留既有失败证据。真实轮次不与 mock 或预检记录合并。

## 验证与分析准备

本地检查覆盖 .env 优先级、SDK 地址/模型/参数、敏感错误脱敏、服务错误停止、成本统计、失败分母和中断轮次不发布性能结论。API 可选依赖已安装在项目 .venv 中；SDK 实测安装版本为 2.54.0，python-dotenv 为 1.2.4，运行 Python 为 3.12.14。后续运行 manifest 会保存实际依赖版本、Git 状态与代码/输入/提示哈希。

分析器会输出任务成功率、工具/决策分数、表示大小、实际 Token 统计、配对结果和失败案例列表。候选参考状态仍需研究者审核。

## 充值后首轮实验

2026-10-02 用户确认补足余额并授权开始实验后，使用相同配置重新运行：

- 两任务预检：8/8 个组合成功，40 个 API 响应，35,956 Token，保存于 results/raw/exp001/siliconflow_smoke_funded_20261002。
- 完整轮次：12 × 4 × 1 = 48/48 个组合成功，253 个 API 响应，224,969 Token，保存于 results/raw/exp001/siliconflow_round1_20261002。
- 完整轮次无服务错误或表示校验失败；从 19:47:01 运行到 19:56:16（Asia/Hong_Kong）。两轮实际已报告用量合计 260,925 Token；没有将预检并入正式比较。
- 自动 CS 的首次输入/端到端 Token 配对平均降幅为 41.0%/9.3%；Summary 为 53.9%/27.3%。本轮任务成功率相同，未证明 CS 优于普通摘要。
- 核对冻结输入/提示/代码哈希，重放全部 48 个动作轨迹并核对评分。原始余额错误仍保留。没有修改提示或挑选性重跑。

详细解释、个别任务成本增加、偏好分类问题及下一轮建议见 [首轮分析](../results/analysis/exp001_siliconflow_round1_20261002/analysis.md)。这是短历史合成先导试验，不能外推到长期真实任务或认定 H1–H3 成立。
