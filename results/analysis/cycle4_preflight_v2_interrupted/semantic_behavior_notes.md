# 第四轮中断预检：状态语义与执行行为的关联

本报告分析已保存的部分数据，不提供条件成功率比较。96 个预定组合只保存了 19 条：18 条执行完成（16 份压缩表征、2 条 Full），第 19 条在 Summary 提取请求发生 API 错误，没有可审阅表示；其语义结果为 `not_observed`。其余 77 个组合未开始。来源审阅先于轨迹/评分揭示，以下标注由助手完成，非独立人类 gold，也非条件盲法。

最值得关注的证据是：9 份有具体来源语义错误的表示，后续执行均记录 `task_success=true`。执行者都实际遵循了相应错误义务或过期边界；未观察到其纠正或忽略这些错误。成功检查因此没有证明表示足以准确维护当前认知状态。

## 无依据的验证义务被执行

7 份表示把 public_interface 提供的 `validate_result` 工具变成硬验收条件，而 p1 只要求 job-17 成功及不重复提交。它们分别来自 CS v0.2（p4_006 r1、p4_001 r0/r1、p4_005 r0）、Summary（p4_001 r0、p4_007 r1）和 CS v0.3.1（p4_004 r0）。七条轨迹均实际调用验证，每条多消耗 1 credit；合法工具执行并不会自动意味着它是当前任务必要工作。

例如 p4_004 CS v0.3.1 的 p2 已确定超时请求被接受、结果待完成，G 只有成功完成/不重提要求；Frontier 却增加独立验证义务 o2。执行轨迹是 `consume_job → validate_result → finish completed`。新对象类型与来源引用均编码有效，但仍没有防止工具契约被误当作目标义务。

p4_007 Summary 更直接：p2 已给同一 job-17 成功及 result v1 已保存，p1 没有验证要求，摘要却说验证是“explicit validation requirement”。执行者先验证再完成，来源支持的当前目标原本已经满足。

对照性事实必须同时保留：已保存的两条 Full（p4_001 r0、p4_006 r0）也在 consume_job 后执行无明确要求的验证。这提示执行模型/公共目录可能同样诱发额外验收倾向，不能把上述机制归因于压缩状态本身。相反，p4_008 的 p1 明确要求独立验收；其 Summary 与 CS v0.3.1 都只执行一次验证，属于必要行动。

## 新终态未进入当前边界

p4_010 的 p2 先叙述取消请求已接受、作业运行，再明确补充 matching job-17 terminal cancelled 回执。Summary 删除了后半段终态，CS v0.3.1 保留终态 claim c3 却仍令 c2/j1 为当前 running，并让候选行动依赖 c1/c2。两条轨迹都执行 `consume_cancellation → finish completed`，各多花 1 credit。得到新正确回执使轨迹能完成，但没有证明最初表征正确更新了已知终态。

p4_005 CS v0.2 同时保留旧 pending 和新 matching succeeded/result v1 saved，却继续执行 `consume_job → validate_result → finish completed`。已知终态被重新获取，且验证义务并无来源；这一条包含两种错误、两次不必要付费行动。

这些 3 条轨迹的 `repeated_work_count=0`，相关 9 条的 `tool_usage_correctness=1`、`decision_consistency=1`。字段反映冻结任务检查所得成绩；它们在本组记录中未捕捉跨检查点已有终态的重复获取，也未惩罚新增且合法的非必要工作。原评分没有被追溯更改，诊断与成绩并列报告。

## 已观察到的正确阶段区别

两份 p4_002 CS v0.3.1 将 `submission.completed / outcome=accepted` 与 `job.accepted` 分开，保留 job-17 身份和 pending。p1 明确要求到接受即停止，执行者直接 `finish completed`，实际 `final_settings.job_done=false`。这属于正确目标完成；评分内 `goal_checks.job_done=true` 是“该目标检查通过”，不能误解为世界中作业已成功。

p4_011 的同步成功回执使执行者直接完成，未重复 apply_gold；p4_009 真正尚未取消完成，则准确保留 pending 并必要地 consume_cancellation。生命周期区分在这些已观察实例中是可用的，但部分前缀数据不能建立条件总体差异。

## 成本与证据范围

9 个错误表示合计导致 10 次当前用户目标和已知回执不需要的付费 execute（7 次无要求验证、3 次终态重复获取），花费 10 credits。对应选择这些行动的 10 个执行请求实际报告 17,307 Tokens；这是这些已记录请求的用量，不是估计的端到端节省量、反事实差值或金额。后续 finish 消息的上下文也因额外行动改变，不能简单相减得到可节省总成本。

已产生的 16 份表示都完成编码且记录行为成功，仍有上述 9 份来源错误及 2 份包含歧义。这个描述性计数不得写成完整预检有效率/成功率，亦不能以可观察样本筛选形成优越性结论。一次提取 API 错误没有表示，无法判断语义；未知用量意味着总成本未知，audit 的 100,764 Tokens 仅为已知报告量。

完整逐项动作、原始来源标注、指标、具体多余请求与哈希保存在 [semantic_behavior_notes.json](semantic_behavior_notes.json)。所有原始结果和冻结资产保持原样。

| 表征 | 来源诊断 | 实际执行 | 当前目标下不必要付费行动数 |
|---|---|---|---:|
| p4_006_cs_v02_r1_h1 | 新增验证义务 | consume_job → validate_result → finish | 1 |
| p4_001_summary_r0_h1 | 新增验证义务 | consume_job → validate_result → finish | 1 |
| p4_010_summary_r0_h1 | 过期阶段/重开终态 | consume_cancellation → finish | 1 |
| p4_001_cs_v02_r1_h1 | 新增验证义务 | consume_job → validate_result → finish | 1 |
| p4_004_cs_v031_r0_h1 | 新增验证义务 | consume_job → validate_result → finish | 1 |
| p4_001_cs_v02_r0_h1 | 新增验证义务 | consume_job → validate_result → finish | 1 |
| p4_007_summary_r1_h1 | 新增验证义务 | validate_result → finish | 1 |
| p4_005_cs_v02_r0_h1 | 新增验证义务；过期阶段/重开终态 | consume_job → validate_result → finish | 2 |
| p4_010_cs_v031_r1_h1 | 过期阶段/重开终态 | consume_cancellation → finish | 1 |
