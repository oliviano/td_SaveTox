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

### In plain words

There are two ways `base_save` can write a TOX file. You pick with two toggles on the **Save Settings** page of `base_save`. The read-only **Current Save Mode** line right below them always tells you what the two toggles do together.

**Versioned Snapshots** (on by default, recommended)
Every save writes a *new* file with the version in its name: `myComp_v1-0-0.tox`, then `myComp_v1-0-1.tox`, and so on. The COMP always points at the newest one. Nothing is ever overwritten, so you can go back to any earlier save from the version history icon in the tool window. The cost is disk space: old versions stay until you prune them.

**Single File (Overwrite)** (off by default)
Every save overwrites the same file, `myComp.tox`. Simple and tidy, but the previous save is gone. You get a confirmation dialog before each overwrite.

| Versioned Snapshots | Single File | What a save does |
|---|---|---|
| on | off | Adds `myComp_v1-2-3.tox`. The COMP points at it. History is kept. **Default.** |
| off | on | Overwrites `myComp.tox`. No history. |
| on | on | Overwrites `myComp.tox` (the COMP points at it) and also keeps a versioned copy of every save. |
| off | off | Nothing is saved. `base_save` refuses and logs an error. |

You can switch modes at any time. The next save writes the right file name for the new mode.

### Details

- The toggles are the `Versionsave` and `Canonicalsave` pars. The `VERSION_SAVE` / `CANONICAL_SAVE` class constants in `saveTox.py` are only fallbacks for a copy of the tool that lacks the pars.
- Versioned filenames never compound: any existing `_vX-Y-Z` suffix is stripped before the new version is appended.
- A normal save bumps the patch number. If a higher version already exists on disk (for example after loading an older version), the save continues from the highest one, so an existing snapshot is never overwritten.
- After every save, the COMP is reloaded from its `externaltox` path via `reinitnet` so TD clears the dirty flag.

---

## Where TOX files go

Every external COMP always has a path. There is no "external but without a path" state, SudoTools included.

- **Default TOX Folder** (`Defaulttoxfolder`, default `tox`) is relative to the project folder.
- Externalizing with `ctrl+w` opens the folder chooser in that folder. A COMP named `myComp` saved into `tox` becomes `tox/myComp/myComp_v1-0-0.tox`.
- A COMP that is saved without any path (from a script, or a SudoTool) gets `<Default TOX Folder>/<name>/<name>.tox` automatically.
- Paths are stored relative to the project folder.

---

## Unsaved TOX check

With **Check Unsaved TOX** (`Checkunsaved`) on, `base_save` looks for external TOX with unsaved changes when you save the project (`ctrl+s`) and when you quit. If it finds any, it lists them and offers **Save All**.

Saving the project is the better moment. In versioned mode a save repoints the COMP to a new file, and that pointer lives in the `.toe`. A TOX saved at quit time is written to disk, but the `.toe` on disk still points at the previous version; load the newest one from the version history icon after reopening.

In the tool window, rows with unsaved changes are tinted (colour: `Dirtyrow` on the Colors page), and the **Save All** header icon saves all of them in one click. The dirty state is refreshed when the window opens and when you press the refresh icon.

---

## Sharing TOX versions between machines

When several people work on copies of the same project, each machine can publish which TOX versions it has, so the others can see it and decide when to update. Moving the `.tox` files themselves is not part of this; they travel by whatever channel you already use.

Turn on **Share TOX Versions** (`Manifestenable`) on the **Sync** page of `base_save`.

- Each machine writes one small text file, `tox_manifest/<machine name>.jsonl`, with one line per listed TOX: path, version, save time, TD build and a hash of the file. It is rewritten after every TOX save, and only when something changed.
- Commit, pull and push that folder with git yourself. `base_save` never runs git. Because every machine only writes its own file, there are no merge conflicts.
- The TOX list gains three columns and two row icons. **Remote** shows the highest version any other machine has, and whose it is. **Working On** shows claims (see below). **Sync** compares the remote version with yours:

| Sync | Meaning |
|---|---|
| in sync | Same version, same file. |
| update ready | They have a newer version and that file is already on your disk. A download icon appears on the row: click it to load that version. |
| newer, no file | They have a newer version; the file has not reached you yet. |
| newer, file differs | A file with that version is on your disk, but it is not the one they saved. |
| ahead | Your version is newer than theirs. |
| diverged | Same version number, different files. Two people saved the same version separately. |
| local only | No other machine lists this TOX. |
| remote only | Another machine lists a TOX that no COMP in your project uses. |

- The sync icon in the header publishes your file and re-reads the others. Use it after a `git pull`.
- Only the COMPs in the TOX list are published, so both machines should use the same filter tag.
- The machine name comes from the computer. To override it, create `tox_manifest/.local` containing `{"host": "kuro", "user": "Kuro"}`. This is a file and not a par because the `.toe` is shared between machines. Keep `.local` out of git.

In the project's own repository, add `tox_manifest/.local` to `.gitignore` and `tox_manifest/* text eol=lf` to `.gitattributes`.

### Updating to someone else's version

When a row says **update ready**, click its download icon. The COMP is pointed at the newer file and reloaded. You are asked first if the COMP has unsaved changes, or if the file was saved in a newer TouchDesigner build than yours.

The icon only appears when the file on your disk is exactly the one the other machine published. In the two "newer" states that are not ready, clicking the empty cell tells you why in the status bar.

### TOX that only someone else has

A TOX another machine lists, and that no COMP in your project loads, is shown as a row without a COMP: name, remote version and **remote only**. It is for information. The folder icon reveals the file if it is already on your disk; adding the COMP to the project is up to you.

A COMP that exists in your project but is hidden by the tag filter does not count as missing.

### "I'm working on this" claims

Click the flag icon on a row (or its **Working On** cell), type a short note and press **Claim**. Click again to change the note or **Release** it.

- The note is stored in your own manifest file, so the others see it after your next commit and push, and their next pull. It cannot prevent two people starting the same thing within the same hour.
- A claim never blocks anything. It is a message, not a lock.
- **Working On** shows every claim on the TOX, for example `me: camera rig  |  kenji: relighting (2d)`. The cell is blue when the claim is yours, amber when it is someone else's, and orange when both of you claim it.
- A claim older than a week is marked `stale` and loses its colour, since people forget to release them.
- After saving a new major or minor version of a TOX you claimed, you are asked whether to release the claim.

---

## Version history

The history icon on each row lists every versioned snapshot found on disk for that COMP, newest first, with the loaded one marked.

- Pick a version to point the COMP at that file and reload it. Unsaved changes are lost; you are asked first if there are any.
- **Prune old versions...** deletes old snapshot files, keeping the newest `Versions to Keep` (`Keepversions`, default 5) and always the loaded one. You are asked first. Nothing is ever deleted automatically.

---

## Filter Settings

On the **Save Settings** parameter page of `base_save`:

| Par | Type | Description |
|---|---|---|
| `Toplevel` | COMP | Search root — only this COMP and its children are scanned for external ops |
| `Filterpertag` | Toggle | When True, further filters to ops whose tags include `Tagtofilterinclude` |
| `Tagtofilterinclude` | String | Tag to match against (e.g. `Ext`) |
| `Autotag` | Toggle | When True, a COMP gets the filter tag automatically the first time it is externalized |
| `Includeext` | Toggle | **Unused.** The feature behind it was stripped from the code; no code reads this par. It is kept so older setups keep loading |

Changing these pars takes effect on the next `Rebuild_op_list()` call (the list-with-magnifier header icon).

The other pars on the page:

| Par | Type | Description |
|---|---|---|
| `Versionsave` | Toggle | Versioned Snapshots save mode (see Save Modes) |
| `Canonicalsave` | Toggle | Single File save mode (see Save Modes) |
| `Savemodeinfo` | String, read-only | Plain-language summary of the current save mode |
| `Defaulttoxfolder` | Folder | Default TOX folder, relative to the project folder |
| `Keepversions` | Int | Snapshots kept by "Prune old versions..." |
| `Checkunsaved` | Toggle | Offer to save unsaved TOX on project save and on quit |
| `Logtotextport` | Toggle | Also print messages to the textport |
| `Includeaboutpage` | Toggle | Maintain the About page (version, last saved) on saved COMPs. Needed for versioned snapshots |

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
# Incremental update — adds newly externalized ops and drops deleted ones.
# Does not re-apply filter changes to ops already tracked.

parent.save.Save_tox(op, save_loc=None)
# First externalization. Pass a folder to skip the folder chooser.

parent.save.Dirty_ops()          # tracked COMPs with unsaved changes
parent.save.Save_all_dirty()     # save all of them

parent.save.List_versions(op)    # ['2.0.0', '1.0.1', '1.0.0'], newest first
parent.save.Loaded_version(op)   # version the COMP currently points at
parent.save.Load_version(op, '1.0.1')   # repoint + reload
parent.save.Update_to_remote(op)        # load the newer version another machine published
parent.save.Remote_only()               # TOX other machines list that this project does not use
parent.save.Set_claim(op, 'relighting') # "I'm working on this"; '' releases it
parent.save.Claim_status(op)            # ('kenji: relighting (2d)', 'theirs')
parent.save.Prune_versions(op, keep=5)  # delete old snapshot files
```

Planned work is described in [docs/](docs/).

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
