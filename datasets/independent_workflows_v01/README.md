# Independent workflow candidates v0.1

These are **assistant-authored development candidates**, not a formally held-out
or researcher-independent benchmark. No real model has been called on them.
Read `docs/independent_workflow_design_v01.md` before selecting experiments.

- `public_workflows.json`: 12 business workflows with four checkpoint packages
  each. At checkpoint h expose only its `new_public_events` and `public_interface`,
  plus that condition's actual retained context/action observations. Do not send
  the full workflow object: it contains later checkpoints and diagnostic tags.
- `public/iwXX/hN.json`: 48 standalone current-checkpoint packages, with no later
  checkpoint or diagnostic tags. These are the safer source for a future adapter.
- `evaluator_fixtures.json`: hidden state, external patches and behavior rubric.
  Never send it to extractors or executors. A stage's canonical `initial_state`
  supports offline replay only; replace it with the condition's actual inherited
  world plus the declared external patch in any live execution.
- `offline_trajectories.json`: privileged one-route solvability evidence, never
  condition inputs or a model baseline. Actions are not an exact-match scoring key.
- `offline_validation.json`: successful replay and negative checks via the existing
  `LifecycleEnvironment`; no model Tokens or performance claims.
- `provenance.json`: prior factor exposure, development relation and review hashes.

All conditions must receive the same public materials and business acceptance
criteria. Summary may express every relevant fact, identity, obligation and
dependency in prose. Behavior scoring reads actual world/action receipts, never
whether the output has G/W/F, JSON fields or a dependency graph. Semantic review
needs the same content rules for prose and structured conditions.

The 48 checkpoints are correlated within 12 workflows. They are not 48 independent
samples. One canonical replay cannot establish recoverability after every possible
model error; failure recovery rules still need protocol design before live calls.

The builder refuses to overwrite by default. `--refresh-unfrozen` explicitly
refreshes this development draft only while provenance still marks it unfrozen;
formal releases need a new version. The builder reads no `.env`.
