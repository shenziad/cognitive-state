# exp001: Context Equivalence

对相同历史截断点的续做任务比较 Full Context、Summary、自动 Cognitive State，以及待审核候选状态。使用 12 个合成配置修复任务；规则见 [试验协议](../../docs/exp001_protocol.md)，任务见 [总览](../../docs/task_catalog.md)。

## mock 运行

在仓库根目录使用 Python >=3.10，无第三方依赖：

```bash
python scripts/run_experiment.py
# 或指定一个尚不存在的结果目录
python scripts/run_experiment.py --output results/raw/exp001/my-review-run
python -m unittest discover -s tests -v
```

默认 `config.json` 是 mock 配置：12 个实例 × 4 个条件 × 1 次重复，最多 8 步。mock 会读取公开工具返回的手册并按脚本完成操作，故成功分数仅表示协议可运行，不是模型表现。mock 使用 UTF-8 bytes，Token 指标为 null。

## 结果文件

- `config.json`：实际使用配置。
- `manifest.json`：版本、内容哈希、审核状态、运行状态和时间。
- `inputs/`、`prompts/`：冻结的任务/环境/参考状态及提示副本。
- `instances/*.json`：表示、每次调用的消息与响应、观察和行为轨迹。
- `results.json`、`summary.json`：实例记录与描述性聚合。

所有结果为 JSON；原始目录被 Git 忽略，现有输出目录不覆盖。失败不从分母移除。每次 API 输入/输出用量单独记录，初次输入和端到端成本分别比较。

## 真实 API 接入准备

复制 `configs/exp001_api.example.json`，填写 model、完整 HTTPS endpoint 和适合该模型的 `tiktoken:<encoding>`。示例缺少必要选择，因此不会直接运行。部分服务需调整输出上限字段或将 temperature 设为 null；说明见 [API 适配器](../../docs/api_adapter.md)。

```bash
python -m pip install -e ".[api]"
python scripts/run_experiment.py --config configs/exp001_api.local.json
```

真实 provider 会读取仓库根目录 .env，已有环境变量优先；凭据变量由 api_key_env 指定。通用示例选择两个任务、各三次重复，设置请求次数上限，接入前仍需确定货币预算。参考状态待研究者审阅；不能写成已审核的人类基线。

SiliconFlow 的具体 SDK 接入使用 `configs/exp001_siliconflow_smoke.json`（两个任务）及 `configs/exp001_siliconflow.json`（12 个任务、各一次重复）。模型为 deepseek-ai/DeepSeek-V4-Flash，思考模式关闭，表示上限为 2200 UTF-8 bytes，Token 成本取实际 usage。具体说明见 [API 适配器](../../docs/api_adapter.md)。
