# History diagnostics v0.1

Pre-call development diagnostics, authored by an assistant familiar with the
project. This is not an independent benchmark or natural workflow dataset.

## Fixed allocation

- 12 original workflow checkpoints, selected by semantic rule before API calls.
  Histories replay the candidate canonical prior actions. Selected checkpoints:
  iw01 h2, iw02 h4, iw03 h4, iw04 h4, iw05 h4, iw06 h4, iw07 h2,
  iw08 h3, iw09 h4, iw10 h2, iw11 h4, iw12 h4.
- 6 separately authored historical counterfactual pairs (12 members), extending
  six business narratives with genuine two-option commitment operations. They
  do not mutate the original candidate files. Mechanism A is assigned ALL 12
  paired members before calls, never selected by model performance.
- Total: 24 checkpoint tasks; Full/No History diagnostic = 48 assigned cells.
  The paired subset represents 6 correlated workflows, not 12 independent cases.

## Model input boundary

`tasks_public.json` is an authoring container, NOT a whole model message. Send
only one task's historical_context (except No History), current_public_events,
and public_interface. Do not send task_id, family, source_workflow_id, checkpoint,
pair_id, variant, provenance, validation, answers, fixtures, or later events.
All event content values are strings. History action receipts are actual public
observations; private trace state_after and score are never copied to history.
The pair interface scope and event IDs are shared between members, so opaque
variant identifiers cannot leak an approved value. The order of task selection
must be independently randomized by the frozen runner.

`fixtures_private.json` contains evaluator-only world, rubric, and canonical
actions; never expose it to extractors, planners or actors. Canonical actions are
solvability evidence, not exact-match behavior answers. Evaluate final world,
budget, legal finish and user requirements via existing LifecycleEnvironment.

## Necessity evidence and limits

`offline_history_necessity.json` retains source selection, canonical routes,
allowed all-blocked earlier-history counterexamples, and finite route analysis.
Original 12 are marked not_proven: canonical multi-handoff success alone does
not show history is needed; later instructions/catalogs may already give the
answer or required facts. An alternate failed world that cannot finish within
four calls is not accepted as a clean necessity pair. Tool-dependent adaptive
recovery remains a separate question on original tasks.

For each new pair exactly one early fact differs, while current events and
interface are byte-equivalent canonical JSON. Both choices are technically
executable in both worlds; no hidden approved-value precondition, current
resource or receipt discloses the answer. The explicit user rule allows one
commitment; commit_count records duplicates. Wrong followed by correct fails
world/constraint acceptance, rather than matching an exact action string.
All finite named-action routes up to four calls including finish are enumerated.
No sequence succeeds for both members. Each has a two-call, one-credit solution.
Random No History guesses may still succeed; the result is a missing-fact control,
not a claim that No History can never succeed or that CS has an advantage.

All single-checkpoint environments have four credits and at most four actor
calls including finish. The model runner must enforce the call limit; environment
alone records credits. Earlier canonical history is fixed across conditions;
these diagnostics do NOT test actual multi-handoff error propagation or evolving
state. Pending-job distractors are not claimed to prove lifecycle mechanisms.

`provenance.json` locks source hashes, selection, members, and builder/data hashes.
This data version is ready for review, not itself a model-experiment protocol.
The builder refuses overwriting by default. --refresh-unfrozen is allowed only
while provenance status remains reviewable_pre_call_diagnostics; after protocol
freeze, preserve this release and make a new version for corrections.
