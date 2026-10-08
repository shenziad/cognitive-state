# exp001-pilot-v0.1

12 个由助手离线构造的合成配置修复任务，仓库 MIT 许可证适用。实例路径见 `manifest.json`，设计范围见 [试验协议](../../../docs/exp001_protocol.md)。

- `tasks/`：公开的截断前历史，唯一提取信息来源。
- `environments/`：运行环境、后续工具证据和评分 rubric，只进入环境/评分侧。
- `references/`：候选 G/W/F、来源消息和 pending 审核标记。

`python scripts/build_pilot_dataset.py` 可重建当前候选数据，并覆盖本版本任务和参考文件。审阅修改后请先升级数据版本，以免重建命令覆盖审核意见。
