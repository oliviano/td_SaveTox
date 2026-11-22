# base_save — tool window icons

`base_save` externalizes COMPs to `.tox` files, tracks them, and re-saves them
with semver versions. Its tool window ("All TOX Components") lists every
tracked external COMP. Open it with `ctrl+shift+w`; `ctrl+w` saves or
externalizes the COMP shown in the focused network pane.

All icons are Material Design Icons glyphs drawn by textCOMPs.

## Header icons (top right, left to right)

| Icon | Glyph | Operator | Action |
|---|---|---|---|
| List with magnifier | `F1647` | `container_header/text_icon_refresh_ext1` | Full rescan. Calls `parent.save.Rebuild_op_list()`: clears the tracked list and rebuilds it from the current filter pars (`Toplevel`, `Filterpertag`, `Tagtofilterinclude`). Use after changing a filter par. |
| Stacked floppy disks | `F0194` | `container_header/text_icon_save_all` | Save All. Calls `parent.save.Save_all_dirty()`: saves every listed COMP that has unsaved changes (the tinted rows). |
| Two arrows in a circle | `F04E6` | `container_header/text_icon_manifest` | Only shown when `Manifestenable` is on. Calls `parent.save.Sync_manifest()`: writes this machine's TOX manifest and re-reads the other machines' (fills the Remote and Sync columns). Does not run git. |
| Circular arrow | `F1377` | `container_header/text_icon_refresh` | Quick refresh. Calls `parent.save.Ops_manager.Check_external_ops()`: adds newly externalized COMPs, drops deleted ones, and updates the dirty states. Does not re-apply filter changes to rows already listed. |
| Boxed X | `F0158` | `container_header/text_icon_close` | Closes the window (`window1.par.winclose`). |
| Python logo (hidden) | `F0320` | `container_header/text_icon_refresh_ext` | `display` is off. Re-initializes base_save's own extensions. |

Each header icon is wired by a `panelexec_*` DAT in `container_header`. Their
left-to-right order is their `nodeX` in the network (`alignorder = me.nodeX`).

## Row icons (right end of each row, left to right)

| Icon | Colour | Glyph | Column | Action |
|---|---|---|---|---|
| Eye | purple | `F06D0` | `view` | Jumps the current network pane inside that COMP. |
| Save / pencil | green | `F0CFC` | `save` | `Save_over_tox`: bumps the patch version and saves according to the save mode, then reloads the COMP. |
| Clock with arrow | slate | `F02DA` | `versions` | Version history menu: lists the snapshots on disk (newest first, loaded one marked). Picking one calls `Load_version` (repoint `externaltox` + reload). "Prune old versions..." deletes old snapshot files after a confirmation. |
| Download arrow | slate | `F01DA` | `update` | Only with `Manifestenable` on, and only drawn when Sync is `update ready`. Calls `Update_to_remote`: repoints the COMP at the newer file another machine published and reloads it, after a confirmation if the COMP is dirty or the file comes from a newer TD build. |
| Flag (outline / filled) | slate | `F023D` / `F023B` | `claim` | Only with `Manifestenable` on. Opens the claim dialog (`popDialog` with a text field): Claim or Release an "I'm working on this" note via `Set_claim`. Filled when this machine holds a claim. |
| Open folder | orange | `F0DCF` | `show_file` | Reveals the TOX file in Finder / Explorer. |
| Reload arrow | blue | `F0453` | `reload` | Pulses `reinitnet`: reloads the COMP from its TOX on disk. Unsaved changes inside the COMP are lost. |
| Python logo | yellow-green | `F0320` | `reload_ext` | Pulses `reinitextensions` on that COMP. |

Row clicks go `listerConfig/callbacks` -> `parent.save.Lister_on_click` ->
`listerFuncs.parse_col`, which maps the column name to a function. Glyphs are
set in the `textFormat` row of `listerConfig/colDefine`; the looks are the
`view`, `save`, `versions`, `update`, `claim`, `show_file`, `reload`,
`reload_ext` textCOMPs (plus their `Roll` / `Press` variants) in
`listerConfig`. The `update` and `claim` glyphs are not in `textFormat`: they
come per row from `Sync_row()` through `script_external_ops`, because they
depend on the row's state.

## Row tint

A row whose COMP has unsaved changes (`dirty` = True) is tinted with the
`Dirtyrow` colour from base_save's Colors page. This is done in `onInitCell`
in `listerConfig/callbacks` and needs the lister's Advanced Callbacks par on.
The dirty state is only re-read when the window opens or a refresh icon is
pressed; it is not live.

## Remote, Sync and Working On columns

Hidden (width 0) unless `Manifestenable` is on; `Apply_sync_columns()` shows
them (with the `update` and `claim` icons) and widens the window. All are
filled by `Sync_row()` through `script_external_ops`.

- **Remote**: the highest version another machine lists, with its name.
- **Sync**: the comparison state from the `saveManifest` module (`in sync`,
  `update ready`, `newer, no file`, `newer, file differs`, `ahead`,
  `diverged`, `local only`, `remote only`), coloured by `SYNC_COLORS` in
  `listerConfig/callbacks`.
- **Working On**: the claims on the TOX, e.g.
  `me: rig  |  kenji: relighting (2d)`. Coloured by `CLAIM_COLORS` from the
  hidden `wipState` column (`mine`, `theirs`, `both`; `stale` has no colour).
  Clicking the cell opens the claim dialog, like the flag icon.

## Remote-only rows

A TOX another machine lists and no COMP in this project loads is added as a
row with an empty `toxPath` (and its manifest key in the hidden `toxKey`
column), from `Remote_only()`. `onInitCell` blanks its icons except the
folder. `listerFuncs.parse_col` routes every click on such a row to
`remote_only_info`, which reports where the TOX is, or reveals the file when
it is on disk and the folder icon was clicked.

## Other interactions

- Right-click a **TOX Version** cell: menu with Increment Major / Minor /
  Patch, then saves with that version. Cancel does nothing.
- **Search** field: filters rows by COMP name.
- **Tag** column shows the COMP's tags. With `Filterpertag` on, only COMPs
  carrying the `Tagtofilterinclude` tag (default `Ext`) are listed. That tag
  is added automatically on first externalization (`Autotag` toggle).
- **dirty** column: TD's native `comp.dirty` flag (unsaved changes).
- Both menus share one `popMenu` COMP, so each call to `Open` passes its own
  `items`.

## Hover help

- Header icons: while the mouse is over an icon, the window title is replaced
  by a one-line note. `text_header.par.text` is an expression that looks for
  a rolled-over icon in `container_header/table_icon_help` (icon operator
  name, note) and falls back to `ipar.Settings.Popupheadertext`.
- Rows: the `help` row of `listerConfig/colDefine` holds one tooltip per
  column, shown by TouchDesigner after a short hover. The Sync column's entry
  starts with `*`, so it is evaluated per cell and explains the cell's state.

When adding an icon, add its note in the same place.

## To add or change an icon

- Row icon: add a column to `listerConfig/colDefine`, add the matching look
  textCOMPs, add the column name to `col_name_func_map` in `listerFuncs`.
- Header icon: add a textCOMP in `container_header` with a panelexecuteDAT
  watching it, and set its `nodeX` to place it in the row.
