# Cycle5 preparation controls

These prompts are new assets; previous frozen cycles are unchanged. `conditions.load_prompt(name)` appends `semantic_common.txt` verbatim to planner, organizer, summary, CS1 and executor prompts. Full and CS-text have no preparation model call, and receive that same guidance through the common executor.

The strong summary can preserve every task-relevant detail. Extra reasoning is controlled by Full plus planner and the two-stage summary. No prompt requests a new paid verification obligation. Source validity checks concern shape, references, allowed operation kind/phase and byte size; semantic mistakes remain measured outcomes.

CS-text is deterministic field-path text, not a generated summary. Every object/array/scalar is rendered in original preorder; container metadata retains empty structures and key/element order. `restore_state_text` reconstructs the exact source value, and preparation checks compact serialized equality. The text control has no additional extraction request and no truncation or independent byte cap. Independent deployment cost includes its shared source CS extraction/repair; actual study request totals count that source once.
