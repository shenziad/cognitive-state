**Cycle5 A-v3：hd05 / hd06 完整运行案例核对**

本轮 manifest 在 2026-10-04T03:31:49.340556+00:00 标记 completed 后才读取相关 cells。分析对象为 4 个任务 × 6 个条件，共 24 个完整实例。审核者为项目参与助手；本记录是后行为描述性案例审阅，不是独立人审 gold，也不作统计或因果结论。行为前的来源标注保持封存。

两组历史变体均被六种条件区分。hd05 的 `hd05:approved_fact` 给出 pack-r2：a 为 10 units/carton，b 为 12 units/carton；均为已经移动一次的 10 cartons，因此批准报告分别为 100 和 120。hd06 的 `hd06:approved_fact` 为 rotation-81 分别批准新凭据 k9 和 k10；两候选均已测试这一事实不替代批准对象的选择。

| 条件 | hd05_a | hd05_b | hd06_a | hd06_b | 已实现 rubric 成功 |
|---|---:|---:|---|---|---|
| Full context | report_100 → 100 | report_120 → 120 | record_k9 → k9 | record_k10 → k10 | 4/4 |
| Full+planner | report_100 → 100 | report_120 → 120 | record_k9 → k9 | record_k10 → k10 | 4/4 |
| S1 | report_100 → 100 | report_120 → 120 | record_k9 → k9 | record_k10 → k10 | 4/4 |
| S2 | report_100 → 100 | report_120 → 120 | record_k9 → k9 | record_k10 → k10 | 4/4 |
| CS1 | report_100 → 100 | report_120 → 120 | record_k9 → k9 | record_k10 → k10 | 4/4 |
| CS-text | report_100 → 100 | report_120 → 120 | record_k9 → k9 | record_k10 → k10 | 4/4 |

24 个实际表示均保留决定选择的批准内容；24 个 trace 均只执行一次对应 commitment，再 `finish(completed)`。commit receipt 为 succeeded sync_operation，返回正确的 reported_units 或 recorded_new_credential、committed=true 与 commit_count=1。所有 final_world 均保留 prepared=true、preparation_count=1；实际消耗 1/4 credits，剩余 3，重复工作和违规均为 0。CS-text 的批准内容也保留在确定性路径文本中。这些案例观察支持本轮所有条件使用了正确历史选择，没有区分 CS 相对其他表示的独有优势。

hd06 的来源问题与行为结果需按实际执行输入解释。下表保留行为前标注，不据成功结果回改。

| 来源审阅条目 | 封存问题 | 实际执行输入与行为 |
|---|---|---|
| hd06_a Full+planner / planner | unsupported_completion=incorrect：宣称三类 evidence 都已留在 history | 输入仍含原 history 和该计划；提交 k9 一次，rubric success=true；没有验证三类 evidence 留存的回执 |
| hd06_a S1 / final | missing_decision_dependency=incorrect：遗漏 retain 三类 evidence 义务 | 最终摘要确实缺 client-switch / old-k8 保留内容；提交 k9 一次，rubric success=true |
| hd06_a S2 / organizer | missing_decision_dependency=ambiguous：Dependencies 仅写 catalog preconditions，范围不清 | 最终摘要明确保留批准与三类 evidence 义务；提交 k9 一次，rubric success=true |
| hd06_b Full+planner / planner | missing_decision_dependency=incorrect：planner 稿遗漏保留义务 | 实际执行输入包含完整 history，其中 hd06:current:u 仍保留原义务；提交 k10 一次，rubric success=true |
| hd06_b S1 / final | missing_decision_dependency=incorrect：遗漏保留义务 | 最终摘要确实缺该义务；提交 k10 一次，rubric success=true |
| hd06_b S2 / organizer 与 final | 两份均 missing_decision_dependency=incorrect：遗漏保留义务 | 最终摘要仍缺该义务；提交 k10 一次，rubric success=true |

实际 executor 表示中，hd06_a 的 Full context、Full+planner、S2、CS1、CS-text 保留 evidence-retention 目标，S1 缺失；hd06_b 的 Full context、Full+planner、CS1、CS-text 保留，S1/S2 缺失。Full+planner 的原 history 可以补足 planner 单稿的遗漏，故 planner 审阅错误数不能直接当作执行输入丢失次数。CS goal 中保存义务只证明内容被保留，不能证明证据文件或状态完成。

hd06 当前 measurement 对 evidence-retention 目标不敏感。12 个 hd06 final_world 的键均只有 `ready`、`prepared`、`committed`、`commit_count`、`recorded_new_credential`、`preparation_count`。对应 goal_checks 只检查后五项（不含 ready）；没有 test、client-switch 或 old-k8 revocation evidence 的留存字段。两种 public operations 仅要求 ready=true，成功 effects 只设置 recorded_new_credential 与 committed，并增加 commit_count；resources 为空，返回回执也没有三类留存 evidence 的内容或标识。父任务在行为释放后核对本轮初态/private rubric，另确认初态和 rubric 也未建模三类 evidence 字段；本案例审阅未读取 private rubric。

因此这里没有可被工具破坏后再被评分检出的三类留存状态；目标根本没有对应的状态和评分检查。**当前 success 仅证明已实现 rubric 被满足，不能证明 test/client-switch/old-k8 evidence 保留目标完成。** 这些来源遗漏与无依据完成说法没有伴随错误的已评分 commitment；对留存目标是否造成损害，本轮没有可观测判据。相同 success 不能证明遗漏无害，或各条件在完整用户目标上等价。

hd06_b CS1 关于 commit_count=0 的封存来源备注也不回改。行为后的回执明确显示实际 commitment 后 count=1，这不能把行为前缺少计数回执的推断追溯变成观测证据。

证据均来自本轮 `results/raw/cycle5/mechanism_v3_20261004/manifest.json`、`results.json` 及 24 个 `instances/hd05_*`、`instances/hd06_*` 文件；JSON 版本逐 cell 保存 artifact SHA256、批准引用、实际动作、commit/finish 回执、final_world、goal_checks 和来源问题映射。原 source reviews、freeze 和源码未修改；未调用 API 或读取 .env。
