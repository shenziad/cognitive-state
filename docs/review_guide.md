# 前四项工作的审阅入口

下一轮协议审阅：优先看 [请求与作业生命周期](operation_lifecycle_v0.3.1.md)、[第四轮门槛和冻结协议](cycle4_protocol_20261003.md)、[规范案例](examples/cognitive_state_v0.3.1/conformance_cases.json)。本次只冻结协议，不调用模型；完整执行资产仍待实现和单独锁定。

2026-10-03 最新审阅入口：[第三轮总报告](../results/analysis/research_cycle3_20261003/analysis.md)、[24 份状态及来源审阅](../results/analysis/cycle3_preflight_r2_20261003/semantic_review.json)、[实现说明](v03_implementation_and_cycle3.md)。v0.3 最小实现和两版真实预检已完成，门槛未通过，四条件比较及连续交接未运行。设计依据见 [修订说明](design_revision_v0.3.md)、[定义](cognitive_state_definition.md)、[更新协议](state_update_protocol_v0.3.md)；[手写示例](examples/cognitive_state_v0.3/README.md)仍非模型实验结果。下文保留历史审阅入口。

建议按下面的顺序阅读。研究协议、提示和参考状态目前均为待审阅版本。

1. [试验协议](exp001_protocol.md)：重点看输入边界、公平比较、评分口径与结论范围。
2. [任务总览](task_catalog.md)：包含全部 12 个任务和对应候选状态。先抽查 TLS、CSV 格式和请求超时，分别覆盖约束、多目标和失败尝试。
3. [提示词](../prompts/README.md)：普通摘要、G/W/F 提取及共享执行器；检查摘要公平性与状态字段。
4. [运行说明](../experiments/exp001_context_equivalence/README.md)：默认配置、mock 一键运行及结果结构。
5. [验证记录](verification_20261001.md)：已验证内容与真实模型验证范围。
6. [SiliconFlow 接入与连接记录](siliconflow_integration_20261002.md)：SDK、凭据加载、请求参数和首次连接状态；[首轮分析记录](../results/analysis/exp001_siliconflow_20261002/analysis.md) 区分服务错误与实验结论。

## 需要你判断的内容

- 任务是否体现“保持行为连续性”的初步测试价值？历史是否过于直白？
- facts、beliefs、assumptions 是否区分合理？是否混入截断后信息？
- Goal 约束和 Frontier 待办是否完整？是否缺少工具状态、失败尝试或依赖？
- 评分是否允许合理的不同路线？是否会误判已经正确完成的任务？
- 任务能否区分普通摘要与 CS，还是存在明显天花板效应？

每个参考文件有 `review` 和 `source_message_ids`。审核后可填写 reviewer，将状态改为 reviewed 并记录修改理由；内容修改建议升级数据版本。**当前候选状态不能被描述为已经人工审核的 ground truth。**

## 代码入口

- [运行入口](../scripts/run_experiment.py) 与 [编排器](../src/evaluation/runner.py)
- [虚拟环境与评分器](../src/evaluation/controlled.py)
- [提取器](../src/state/extractor.py)、[状态表示](../src/state/representation.py)、[校验器](../src/state/validator.py)
- [API 适配器](../src/llm/client.py) 与 [mock](../src/llm/mock.py)
- [关键验证](../tests/test_pilot.py)

协议、三个任务及对应参考状态足以开始提出修改意见，不必先读完全部代码。

## 当前第四轮实现审阅

优先看[执行说明](cycle4_execution_v2.md)和[117 项离线验证记录](freezes/cycle4_offline_validation_v2.json)。12 个预检实例、四条件提示及三阶段运行器已实现；v2 修正了行为失败与执行格式错误的区分。真实预检准备完成，尚未调用模型。
