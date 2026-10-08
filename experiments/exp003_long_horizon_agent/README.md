# exp003: Long-Horizon Agent

研究多轮续做中的 Cognitive State 更新、过时状态修正和行为连续性。每轮应记录输入状态、行动、观察、更新后状态及 Token 用量；保存配置快照与 JSON 结果。

2026-10-03：v0.3 连续交接运行器和配置已准备，真实调用尚未开始；两版可靠性预检未通过完整门槛，见[第三轮报告](../../results/analysis/research_cycle3_20261003/analysis.md)。[旧先导结果](../../results/analysis/longitudinal_v01_20261002/analysis.md)中两条 CS 链均在首次提取失败，不能作为新设计的多轮结果。协议见 [v0.3 更新协议](../../docs/state_update_protocol_v0.3.md)。
