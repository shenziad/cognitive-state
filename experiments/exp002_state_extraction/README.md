# exp002: State Extraction

检查 Goal、World Model、Frontier 的提取完整性、事实与信念区分、置信度和过时信息。先确定人审标注协议，再运行 API-based extractor；保存实际配置与 JSON 结果。

2026-10-03：已实现独立 v0.3 提取与校验入口并完成两版真实预检。修订版首次有效 22/24、修复后有效 24/24；来源审阅发现 1 份操作阶段升级缺乏对应回执。见[第三轮报告](../../results/analysis/research_cycle3_20261003/analysis.md)。旧入口继续使用旧协议，数值置信度不是新设计必填项。
