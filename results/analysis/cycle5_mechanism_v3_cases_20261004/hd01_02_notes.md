本轮 hd01 / hd02 来源标注与实际行为案例核验。

仅分析 cycle5-mechanism-v3 的 mechanism_v3_20261004 当前 run。manifest 已 completed。四任务 × 六条件共24格均为批准对应的同步提交一次，然后 finish completed；每格花费1 credit，commit_count=1，评分 success=true。以下 success 仅指当前已实现 rubric，不能证明自然语言保留目标全部完成。

来源标注在 executor release 前已 seal；本组文件 SHA256 为 `0881978fb94813aa01b2389e4b43e2d9b334a81bfd4c14b5fb07d5de964c391f`，与 seal 完全一致。私有 initial_state/rubric 只在来源 seal 后、获得案例核验授权后读取；当前实际 trace/world 只在 manifest completed 后读取。原标注、表示与冻结源码没有追溯修改。本报告是参与项目助手的描述性核验，不是独立人审 gold，也不是统计因果证据。

**冻结来源标注与后续观察**

| 案例 | 冻结来源判断 | 实际观察 | 可得结论 |
| --- | --- | --- | --- |
| hd01_b / full_planner | missing_decision_dependency=incorrect；entity_phase_confusion=ambiguous。原文允许在首次 publish_public outcome genuinely unresolved 时 retry，与 hd01:current:u 的 Commit once only 存在冲突。 | 首次 publish_public 回执 succeeded；audience=public，committed=true，commit_count=1，随后 finish completed。没有失败、timeout 或重试。 | 未决结果重试分支未触发；该轨迹不能检验 executor 遇到未决结果时的行为，也不能撤销来源问题。 |
| hd01_a / summary_s1 | missing_decision_dependency=incorrect：遗漏 hd01:current:u 的 Keep its redaction and citations。 | publish_internal succeeded → finish completed；当前 rubric success=true。 | 已实现的提交 rubric 没有观察到错误；保留目标未建模，无法判断 redaction/citations 是否保留或受损。 |
| hd01_b / summary_s1 | missing_decision_dependency=incorrect：同样遗漏 redaction/citations 保留义务。 | publish_public succeeded → finish completed；当前 rubric success=true。 | 同上，不能将评分成功解释为遗漏无害或保留目标完成。 |
| hd01_a、hd02_a / summary_s1 | invented_requirement=ambiguous：禁止 finish before success/commitment 是否仅指 completed status 未限定。 | 首个同步操作都 succeeded 后才 finish completed。 | 失败后 truthful blocked finish 场景未发生；歧义未被此轮行为检验。 |

**所有条件的公开 trace / world 对照**

表中每个链接指向实际 instance。值为成功回执确认的 audience 或 hotel_location；每格完整序列都是该批准值对应 execute 一次 → finish completed，最终 committed=true、commit_count=1、prepared=true、preparation_count=1、remaining_credits=3。

| 条件 | hd01_a | hd01_b | hd02_a | hd02_b |
| --- | --- | --- | --- | --- |
| full_context | [internal](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd01_a_full_context.json>) | [public](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd01_b_full_context.json>) | [station](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd02_a_full_context.json>) | [venue](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd02_b_full_context.json>) |
| full_planner | [internal](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd01_a_full_planner.json>) | [public](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd01_b_full_planner.json>) | [station](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd02_a_full_planner.json>) | [venue](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd02_b_full_planner.json>) |
| summary_s1 | [internal](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd01_a_summary_s1.json>) | [public](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd01_b_summary_s1.json>) | [station](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd02_a_summary_s1.json>) | [venue](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd02_b_summary_s1.json>) |
| summary_s2 | [internal](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd01_a_summary_s2.json>) | [public](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd01_b_summary_s2.json>) | [station](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd02_a_summary_s2.json>) | [venue](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd02_b_summary_s2.json>) |
| cs1 | [internal](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd01_a_cs1.json>) | [public](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd01_b_cs1.json>) | [station](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd02_a_cs1.json>) | [venue](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd02_b_cs1.json>) |
| cs_text | [internal](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd01_a_cs_text.json>) | [public](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd01_b_cs_text.json>) | [station](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd02_a_cs_text.json>) | [venue](<D:/Develop/Cognitive State Representation for Long-Horizon LLM Agents/cognitive-state/results/raw/cycle5/mechanism_v3_20261004/instances/hd02_b_cs_text.json>) |

**保留目标的测量边界**

hd01 的 initial_state 与所有 final_world 仅有 ready、prepared、committed、commit_count、audience、preparation_count。target_state 只检查 audience、committed、commit_count、prepared、preparation_count，另要求 finish_status=completed。redaction/citations 不存在于状态、观察、工具写入效果或 rubric。publish_internal / publish_public 只写 audience、committed 并递增 commit_count。工具无对应的可破坏保留字段，因为这些保留目标根本未建模或评分；当前 success 只证明已实现 rubric，不能证明 redaction/citations 保留完成。

hd02 有同类边界：initial/final state 将 audience 换为 hotel_location，rubric 检查 hotel_location 与相同通用字段。step-free access 和 one existing reservation 的数量/身份没有单独状态字段、观察或评分检查；confirm_station / confirm_venue 只写 hotel_location、committed 并递增 commit_count。工具描述称为现有预订的 step-free option，但行为数据没有独立测量这些保留目标。

prepared=true 与 preparation_count=1 是已建模并保留的准备字段；一次提交和批准值也有实际回执与评分证据。redaction/citations、step-free access、现有预订保留仍是未测量目标。两个 S1 的来源遗漏不会因 success=true 变为正确来源表示；该 omission 对真实 preservation behavior 的影响在当前环境中不可识别。

详细冻结来源标注、24格完整公开 trace/world、相关 initial_state/rubric 与文件hash见同目录 hd01_02_notes.json。证据路径：来源 review_hd01_02_completed.json；source_review_seal.json；当前 run manifest.json/results.json/instances；私有 fixtures_private.json 中仅 hd01_a/b、hd02_a/b 的 environment 用于 seal 后案例核验。
