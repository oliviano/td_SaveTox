# td_SaveTox

SudoMagic's external TOX file manager for TouchDesigner, extended with a versioned save system and scoped search filtering.

Original authors: Matthew Ragan & Ian Shelanskey (sudomagic.com)

---

## Overview

`base_save` is a devTool COMP (`tags: devTool, delete_on_build`) that sits at the root of your project and manages externalizing, tracking, and saving TouchDesigner COMP files (`.tox`). It is accessible from anywhere in the network via the parent shortcut `parent.save`.

Two keyboard shortcuts are registered globally:
- `ctrl+w` — save or externalize the COMP currently open in the active pane
- `ctrl+shift+w` — open the floating TOX finder window (shows all tracked external ops)

---

## Save Modes

Two class-level constants in `saveTox.py` control saving behaviour:

```python
VERSION_SAVE   = True   # also write a versioned snapshot on every save
CANONICAL_SAVE = True   # write the canonical myComp.tox (externaltox par points here)
```

| `CANONICAL_SAVE` | `VERSION_SAVE` | Result |
|---|---|---|
| `True` | `False` | Original behaviour — overwrites `myComp.tox` only |
| `True` | `True` | Overwrites canonical + writes `myComp_v2-2-2.tox` snapshot alongside it |
| `False` | `True` | Writes `myComp_v2-2-2.tox` only, updates `externaltox` par to point to it |

Versioned filenames never compound — `_versioned_path()` always strips any existing `_vX-X-X` suffix before appending the new version.

After every save, the COMP is reloaded from its `externaltox` path via `reinitnet` so TD clears the dirty flag. To disable this, comment out the `saveUtils.Reload_tox(current_loc)` lines in `Save_over_tox`, `Save_tox`, and `dialogChoice`.

---

## Filter Settings

On the **Save Settings** parameter page of `base_save`:

| Par | Type | Description |
|---|---|---|
| `Toplevel` | COMP | Search root — only this COMP and its children are scanned for external ops |
| `Filterpertag` | Toggle | When True, further filters to ops whose tags include `Tagtofilterinclude` |
| `Tagtofilterinclude` | String | Tag to match against (e.g. `Ext`) |

Changing these pars takes effect on the next `Rebuild_op_list()` call.

---

## Key API

All methods below are promoted on `base_save` and callable as `parent.save.Method()`:

```python
parent.save.Rebuild_op_list()
# Clears and fully rebuilds the tracked op list from scratch.
# Use after changing Toplevel / Filterpertag / Tagtofilterinclude.

parent.save.Save_versioned_tox(op)
# Writes a versioned snapshot for any op directly, without going through the
# normal save flow. Respects CANONICAL_SAVE (updates externaltox if False).

parent.save.Save_over_tox(op, version='')
# Re-saves an already-external COMP. Bumps patch version unless version is
# supplied explicitly (e.g. '2.0.0').

parent.save.Ops_manager.Check_external_ops()
# Incremental update — adds any newly externalized ops to the tracked list.
# Does not remove ops or respect filter changes.
```

---

## Save Flow

### ctrl+w (Prompt_to_save)

```
Prompt_to_save()
  ├── externaltox != ''
  │     ├── CANONICAL_SAVE=True  → confirm overwrite dialog → Save_over_tox()
  │     └── CANONICAL_SAVE=False → Save_over_tox() directly (no dialog)
  │
  └── externaltox == ''
        ├── parent is external   → offer "this COMP" or "this COMP + parent"
        │                              → Save_tox() [+ Save_over_tox(parent)]
        └── parent not external  → offer to externalize → Save_tox()
```

### Save_over_tox (re-save)

```
Save_over_tox(op, version)
  ├── update_version_pars()   bump patch semver (or apply explicit version)
  ├── update_save_time()
  ├── _save_tox()             write canonical file (skipped if CANONICAL_SAVE=False)
  ├── Save_versioned_tox()    write myComp_vX-X-X.tox  [if VERSION_SAVE=True]
  │     ├── disk version check — warns if a higher version already exists on disk
  │     ├── op.save(versioned_path)
  │     └── externaltox = versioned_path  [if CANONICAL_SAVE=False]
  └── Reload_tox()            reinitnet — clears dirty flag
```

### Save_tox (first externalization)

```
Save_tox(op)
  ├── ui.chooseFolder()
  ├── os.mkdir()
  │     └── on failure → dialogChoice() (user confirms replace)
  ├── externaltox = rel_loc
  ├── custom_page_setup()     creates About page pars (Toxversion=1.0.0, etc.)
  ├── _save_tox()
  ├── Save_versioned_tox()    [if VERSION_SAVE=True]
  ├── Reload_tox()
  └── Check_external_ops()    register new op in tracker
```

---

## Code Changes Summary

### `saveOp.py`

| What | Change |
|---|---|
| `SaveOpManager.__init__` | Now accepts `my_op` so it can read filter params directly |
| `external_ops` property | Reads `Toplevel`, `Filterpertag`, `Tagtofilterinclude` — scopes `findChildren` to the configured root and optionally filters by tag |
| `Rebuild_op_list()` | New method — clears `External_ops`, rebuilds from scratch, force-cooks the scriptDAT |
| `SaveOp.tags` property | Was a hardcoded two-case string check; now returns `', '.join(sorted(op.tags))` |
| `SaveOp.is_dirty` property | Was a `tdu.Dependency` that was never updated; now delegates to `self._ext_op.dirty` (TD native) |
| `dirty_check()`, `op_hash`, `check_hash_status`, `Dirty_check`, `Ignore_current_dirty_state` | Marked `# NOT CALLED` / `# NOT IMPLEMENTED` — foundation for a future hash-based dirty system, currently inactive |

### `saveTox.py`

| What | Change |
|---|---|
| `VERSION_SAVE`, `CANONICAL_SAVE` | New class constants — toggle the versioned/canonical save modes |
| `_versioned_path()` | New helper — derives `myComp_vX-X-X.tox` path, strips any existing version suffix to prevent compounding |
| `_version_tuple()` | New helper — converts `'2.3.1'` to `(2, 3, 1)` for semver comparison |
| `_find_latest_disk_version()` | New helper — scans the TOX directory for versioned snapshots, returns highest semver found |
| `Save_versioned_tox()` | New method — writes versioned snapshot, warns on higher-version-on-disk, updates `externaltox` when `CANONICAL_SAVE=False` |
| `Save_over_tox()` | Added `VERSION_SAVE` branch + `Reload_tox` after save |
| `Save_tox()` | Added `VERSION_SAVE` branch + `Reload_tox` after save |
| `_save_tox()` | Canonical write gated on `CANONICAL_SAVE`; log line gated on `CANONICAL_SAVE` |
| `Prompt_to_save()` | Overwrite dialog gated on `CANONICAL_SAVE` — skipped when only versioned files are being written |
| `dialogChoice()` | Full rewrite — now sets `externaltox` (was missing), routes through `_save_tox` / `Save_versioned_tox` / `Reload_tox`, removed broken `self.Flash_bg` call |
| `Rebuild_op_list()` | New public wrapper that delegates to `SaveOpManager.Rebuild_op_list()` |
