# exp001-discriminative-v0.1（草案）

16 个配对实例 + 2 个正对照。针对 Cognitive State v0.2 的 G/W/F 设计，2026-10-02 已完成真实模型预检 24 组合及完整单轮 72 组合。候选参考状态全部仍为 `pending`、待独立审核，不能作为人审 gold。先阅读 [设计与评分说明](../../../docs/discriminative_task_design.md)。

| 组 | A 历史 | B 历史 |
| --- | --- | --- |
| G01 目标变更 | [改为私有审计](tasks/disc_g01_a.json) | [公开交付仍授权](tasks/disc_g01_b.json) |
| G02 约束与偏好 | [离线硬要求](tasks/disc_g02_a.json) | [离线仅软偏好](tasks/disc_g02_b.json) |
| W01 信念更新 | [证据确认缓存原因](tasks/disc_w01_a.json) | [证据推翻缓存原因](tasks/disc_w01_b.json) |
| W02 事实与信念 | [诊断已确认](tasks/disc_w02_a.json) | [诊断未执行](tasks/disc_w02_b.json) |
| W03 假设更新 | [握手为 v1](tasks/disc_w03_a.json) | [握手为 v2](tasks/disc_w03_b.json) |
| F01 在途调用 | [提交已发出](tasks/disc_f01_a.json) | [提交仅计划](tasks/disc_f01_b.json) |
| F02 剩余工作 | [A 完成](tasks/disc_f02_a.json) | [B 完成](tasks/disc_f02_b.json) |
| F03 信息缺口 | [A 已知、B 未知](tasks/disc_f03_a.json) | [B 已知、A 未知](tasks/disc_f03_b.json) |

正对照：[全部证据可重新获取](tasks/disc_control01_a.json)、[已经完成、只需结束](tasks/disc_control02_a.json)。

- `tasks/`：公开截断前历史，只有 history 进入提取器。
- `environments/`：内存环境定义、初始状态及评分规则；禁止将整份文件输入模型。
- `references/`：候选 G/W/F 与块级来源 ID，不是人审 gold。
- `review_cases/`：离线可接受轨迹，可能含截断后选择；只供审核和构造校验，禁止进入模型输入。
- `manifest.json`：任务清单、配对与控制标记。

每组目录/工具定义与干扰记录相同；涉及真实执行进度的组，初始环境状态也随历史对应变化。在同一实例内比较表示时必须复用相同初始环境。

复现构造：`python scripts/build_discriminative_dataset.py --output <全新目录>`。脚本拒绝覆盖既有目录。离线审计见 [JSON 记录](../../../results/analysis/discriminative_construction_v0.1.json)；它验证脚本方案，不是模型成功率。

完整真实运行的 18 个任务中，Full Context、Summary、自动 CS 与候选参考状态分别成功 **16/18、16/18、15/18、18/18**；16 个配对实例中前三条件均为 **14/16**，两个 controls 中 Full Context、Summary 均为 **2/2**，自动 CS 为 **1/2**。这只描述一轮小型合成任务，不能证明 H1–H3 或 CS 优于摘要。

真实模型结果见 [单轮分析报告](../../../results/analysis/exp001_discriminative_round1_20261002/analysis.md)。`scripts/analyze_discriminative.py` 从冻结原始记录导出配对汇总与逐任务诊断；CLI 见 [脚本说明](../../../scripts/README.md)。
