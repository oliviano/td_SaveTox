# Plan: hash-based change detection (parked)

Status: **parked**. Nothing here is implemented. The stubs in `dev/saveOp_v2.py` and `saveUtils` are kept as the starting point.

## Why it was started

The TOX list shows TouchDesigner's native `comp.dirty` flag. That flag has gaps:

- It flips on changes that do not matter (moving a node, opening a viewer), so a COMP looks unsaved when nothing real changed.
- It cannot be dismissed. There is no way to say "I know, ignore this change".
- It says nothing about the file. Two machines cannot compare "is my COMP the same as that TOX".

A content hash per COMP would answer all three.

## What exists today

| Piece | Where | State |
|---|---|---|
| `gen_hash_from_op(op)` | `saveUtils` | Returns a list of dicts, not a hash. Skips nested external COMPs only at the first level, so deeper ones are walked into. Compares `par.page` (a Page object) to the string `"About"`, so About pars are never skipped. Appends the same child dict once per parameter. |
| `SaveOp.dirty_check()`, `SaveOp.op_hash` | `saveOp_v2.py` | Compare and store the hash. Never called. |
| `SaveOpManager.Dirty_check()` | `saveOp_v2.py` | Loops over tracked ops. Never called. |
| `SaveOpManager.Ignore_current_dirty_state(id)` | `saveOp_v2.py` | Re-baselines one op. Never called; the lister has an unused `ignore` column for it. |
| `SaveOpManager.Update_save_op_by_path()` | `saveOp_v2.py` | Empty hook, called after every save. This is where the baseline should be stored. |
| `check_hash_status()` | `saveOp_v2.py` | Empty placeholder. |

## Decision to make first

There are two different things a hash can describe. Pick one before writing code.

1. **Hash of the network content** (what the stubs attempt). Answers "did anything meaningful change since the last save". Needs a careful definition of "meaningful" and a full walk of the COMP on every check.
2. **Hash of the `.tox` file bytes.** Trivial and exact, but only describes saved files. It cannot detect unsaved edits. This is what the multi-host manifest plan needs (see `plan_multi_host_manifest.md`).

Recommendation: do option 2 first as part of the manifest work, since it is small and needed there. Treat option 1 as a separate, optional improvement to the dirty column.

## Plan for option 1 (content hash)

1. **Define the fingerprint.** For every operator inside the COMP, stopping at nested external COMPs: type, name, non-default parameter values and expressions, input wiring, DAT text, flags (bypass, lock, render, display). Exclude: node position and size, colour, viewer state, the About page, and anything listed in an ignore set.
2. **Rewrite `gen_hash_from_op`** to build that fingerprint as sorted tuples and return a `hashlib.sha1` hex digest. Stop at every nested external COMP, at any depth.
3. **Store the baseline** in `Update_save_op_by_path()` after each save, on the `SaveOp` (in memory only). Rebuild baselines on extension init; a COMP that is already dirty at init has no trustworthy baseline and stays on the native flag.
4. **Compute lazily.** Hashing is a main-thread walk. Run it only when the tool window opens or refresh is pressed, never per frame. Measure on a large COMP first; if a walk takes more than a few milliseconds, spread it over frames.
5. **Show both signals.** Keep the native flag, add a "changed" state from the hash. A row is tinted only when the hash differs, which removes the false positives.
6. **Wire up Ignore.** Give the existing `ignore` column an icon that calls `Ignore_current_dirty_state`, which re-baselines to the current content.

## Risks

- **Cost.** A full walk of a deep COMP is slow in Python. This is the main reason the work is parked.
- **False negatives.** Anything left out of the fingerprint is a change the tool will not see. Start broad and exclude deliberately.
- **Baselines do not survive a restart** unless persisted. Persisting them means writing to disk or to the COMP, both of which have side effects.

## If the decision is to drop it instead

Delete: `gen_hash_from_op` and `get_non_external_children` in `saveUtils`; `check_hash_status`, `dirty_ops`, `Dirty_check`, `Ignore_current_dirty_state`, `Update_save_op_by_path` in `SaveOpManager`; `dirty_check` and `op_hash` in `SaveOp`; `Ignore_current_changes` in `ExternalFiles`; the `ignore` column in `listerConfig/colDefine`.
