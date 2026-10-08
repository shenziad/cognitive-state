# Four-handoff pilot v0.1

Two assistant-constructed synthetic workflow scenarios, pending independent review.
Each has four checkpoints with public events and private scoring rules. No gold or candidate
reference Cognitive States are provided. Real model invocation is deferred until the preceding
calibration, fairness and ablation stages have been reviewed.

- `release_workflow.json`: confirmed repair, corrected diagnosis, goal cancellation,
  retained validation/bundle progress, final delivery under the latest historical policy.
- `archive_workflow.json`: belief refutation through an actual diagnostic call,
  submitted-versus-completed asynchronous work, preserved validations, final branch selection.

`initial_state` appears only at scenario level. Stage `initial_state` is empty and replaced
by the actual preceding world. `external_state_patch` represents only a newly announced
external diagnostic correction or backend readiness event, never successful prior work.

The runner gives models only `public_goal`, `public_events`, prior condition-retained
representations, and actual action observations. Operations and observations are made
available through the same public tool catalog for all conditions. Hidden `rubric` rules
are saved for replay but are never model context.

No-history means the original shared objective plus current checkpoint events. It loses
prior public goal changes as well as tool observations; this is a recovery diagnostic,
not a component-specific W/F ablation.

See `docs/longitudinal_pilot_design.md` for the fixed budget, accounting and failure policy.
