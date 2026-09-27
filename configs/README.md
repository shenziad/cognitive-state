# Configuration convention

每个实验目录的 `config.json` 是该实验的默认配置。运行时必须在结果旁保存**实际使用的配置快照**，包括 `model`、`temperature`、`benchmark`、`prompt_version`，以及任务集、预算、采样参数等会影响复现的字段。不要把 API key 写入配置。

`base.json` 仅给出字段形状与占位值；具体模型和 benchmark 应在正式运行前确定并冻结。`null` 表示未选择，不得据此宣称实验已可运行。
