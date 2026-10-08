# Recovery preflight: source semantics and behavior

The recovery run completed all 96 assigned cells and produced 72 compressed representations. Its 294 model requests all returned recorded usage, totaling 511,423 Tokens. Source-first assistant review marked 35 representations with at least one specific semantic error. Of these, 32 still received task_success=true. The annotations are not independent human gold, and neither tasks nor conditions were blinded. This is a complete development preflight, not a generalization or long-horizon result.

| Condition | Recorded task successes | Representations with a specific source error | Such errors with successful behavior | All-call Tokens | Unnecessary accepted / rejected actions |
|---|---:|---:|---:|---:|---:|
| full_context | 23/24 | not reviewed as a compressed representation | N/A | 91,743 | 16 / 1 |
| summary | 24/24 | 11 | 11 | 114,718 | 13 / 0 |
| cs_v02 | 22/24 | 15 | 13 | 142,598 | 17 / 2 |
| cs_v031 | 22/24 | 9 | 8 | 162,364 | 11 / 2 |

## A true goal can be achieved before an unnecessary action turns the run into failure

All five failures are p4_003, where attempt-1 timed out and acceptance is initially unknown. The recorded public trajectory is identical: read current/submission for 1 credit; receive accepted job-17; consume_job for the remaining credit; receive matching succeeded/result-v1 effects with job_done=true; attempt an unrequested validate_result at zero credits; receive Workspace credit budget exhausted; finish blocked. The real user goal was already satisfied after step 2. The final-goal-completion score remains 1, but the unnecessary budget violation and blocked finish correctly make frozen task_success false.

The source of that extra obligation differs. CS v0.2 r0/r1 and CS v0.3.1 r1 initially add independent validation to success criteria or frontier obligations, though p1 only requires job success/no resubmission. Their executor follows those extra obligations. CS v0.3.1 r0 has a correct initial state: unknown submission, no invented job handle, lookup then result obligations, and no validation requirement. Its executor adds validation anyway and fails identically. Full Context r1 also fails this way. Thus three failures align with state-added obligations; one occurs after a correct state; one occurs with Full Context. The result cannot be attributed entirely to state extraction.

Full Context r0 on the same p4_003 workflow and both Summary repetitions stop after lookup and consume_job. Summary r1 explicitly says no validation was requested. Summary r0 has a source-review resource-arithmetic error in its hypothetical not-accepted branch, yet the actual lookup returns accepted, so that bad branch is never exercised. Its successful execution does not validate the hypothetical continuation.

## High task success hides extra obligations and stale boundaries

Source review identifies 26 invented hard validation obligations: Summary 7, CS v0.2 12 and CS v0.3.1 7. All 26 are actually executed or attempted: 23 run legally, while the three p4_003 source-error cases are rejected for budget. The legally executed extra checks commonly leave task_success, tool_usage_correctness and decision_consistency equal to 1 because the genuine goal remains met and no explicit policy forbids optional verification. Those scores therefore do not establish source-faithful goal preservation.

A concrete typed-state example is p4_007 CS v0.3.1: G faithfully records only job success/no resubmission, W correctly records the job succeeded, but F adds mandatory validate_result tied to the success requirement. The executor runs that validation. At r0 it also consumes the already successful result first although its candidate was validation, demonstrating extra executor work beyond even the incorrect candidate.

All six compressed p4_010 representations treat already cancelled job-17 as still needing consume_cancellation. Some omit the matching terminal receipt; typed states retain it but leave job.running and current frontier stale. All execute a fresh cancellation-result retrieval and succeed. Both Full Context repetitions also retrieve that already observed terminal cancellation. Newly returned receipts allow the trajectory to finish but do not repair the initial representation or prove it used the prior receipt correctly.

Among the 35 source-error representations, 34 have matching invented-validation or reopened-result work in execution. The remaining one is Summary p4_003 r0: its erroneous not-accepted budget branch is dormant in this run. No semantic rating is revised from execution success. Ambiguous source labels stay ambiguous even when the actual path happens to be correct.

## A correct state does not ensure a correct executor

Both p4_006 CS v0.3.1 source states correctly retain accepted/pending job-17, reject job-18 success as evidence, and include only one consume_job obligation. Nevertheless both executions consume job-17 and then add unrequested validation. They finish successfully because two credits are available. Together with the p4_003 r0 failure, these show an executor tendency that can be harmless under spare budget and harmful under a tight budget. The recordings establish the extra actions; they do not reveal hidden reasoning or prove why the model selected them.

## Submission completion, job completion and user-goal completion remain distinct

All eight p4_002 condition/repetition cells finish without a paid operation, while actual final_settings.job_done stays false. p1 asks successful submission and retained accepted identity, explicitly stopping at acceptance. This is correct task completion with an asynchronous job still pending. Typed states preserve submission.completed/outcome=accepted separately from job.accepted. A goal_checks.job_done=true field means the current goal check passed, not that the world job has succeeded.

In contrast, p4_001/p4_004/p4_006 job-success goals require consume_job after an accepted-but-pending checkpoint; p4_006 job-18 success must not upgrade job-17. When p4_008 already has matching job success but explicitly requires one independent result-v1 validation, that validation remains necessary. Both Full and both typed v0.3.1 cells do only the single validation; the CS v0.2 cells and one Summary unnecessarily consume the already successful job first. Synchronous p4_011 success needs no repeat, whereas p4_012 plan-only history needs one actual apply_gold.

## Extra work has observed costs, without identifying counterfactual savings

Across all 96 trajectories, the current public goal and checkpoint receipts make 62 paid action attempts unnecessary: 40 unrequested validations, 13 successful-job result refreshes, 8 cancelled-job refreshes and 1 acceptance lookup despite already confirmed acceptance. Of these, 57 execute legally and 5 are budget-rejected validation attempts. Trace.cost assigns each attempt one nominal credit, including rejected budget attempts; the diagnostic sum is therefore 62 nominal attempted-work credits, not 62 successful balance debits.

The requests selecting these 62 actions actually report 108,982 Tokens. This is recorded usage, not an estimate of recoverable end-to-end Tokens or money. Removing an action changes later histories, output choices, finish calls and cache behavior, so simple subtraction is not a valid counterfactual savings calculation. All extraction, repair, execution and failure calls remain in the all-call totals above; source errors are not filtered out.

## Interpretation and next experimental need

The typed encoding is usable in all 24 produced v0.3.1 cells, but behavioral success is 22 and source review still finds 9 representations with a specific error. These are separate facts. Full also over-verifies and re-reads known terminal results, while task-oriented Summary can preserve the distinction and can also invent validation. A future mechanism test should distinguish source-grounded obligations from executor-added work and include cases where optional actions consume resources needed later. These observations justify the frozen bounded comparison already permitted by the engineering gate; they do not justify retrospective prompt tuning or a claim that Cognitive State is superior.

The complete per-cell traces, source assessments, error/behavior links, extra-action request usage and five failure traces are saved in [semantic_behavior_notes.json](semantic_behavior_notes.json). The source review and frozen scoring have not been modified. No regression behavior or score was read for this report.
