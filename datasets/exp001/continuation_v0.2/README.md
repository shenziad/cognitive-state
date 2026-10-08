# Continuation v0.2

14 个离线构造实例：6 个反事实配对和 2 个对照。任务内容、工具接口、预算及来源设计见 [设计说明](../../../docs/continuation_v02_design.md)。

- `tasks/`：历史、原始请求与公共信息构成的 `recovery_context`、进度 facts 消融关键词。
- `environments/`：当前世界、工具、credits 和评分 rubric；不能作为模型输入。
- `references/`：助手编写且待审核的候选 CS，仅供来源审核；不加入主比较。
- `review_cases/`：正确轨迹、无历史统一恢复策略及其逐实例分支结果；不能作为模型输入。
- `construction_audit.json`：14 个正确路径成功、12 个交换路径失败及恢复策略成本审核。

无历史恢复条件保留原始 user 请求与共同公开工具定义，但遗失后续目标更新和进度证据。前三组可付出额外成本恢复；后三组所示恢复策略超预算，不能据此断言所有无历史策略均不可能成功。已完成对照直接 finish 的成功也不能证明输入保留了完成证据。

构建器 `scripts/build_continuation_v02.py` 只写入新的不存在目录；冻结本版本后通过新版本迭代，不覆盖原文件。模型运行 config 和原始结果应在实验目录另存。
