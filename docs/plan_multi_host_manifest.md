# Plan: git-tracked TOX manifest for two hosts

Status: **phases 1 and 2 and the claims of phase 3 are implemented.** Not started: the collision-avoiding version bump across manifests and the `base` lineage check (rest of phase 3), and the optional git fetch helper (phase 4).

Decisions taken (2026-11-22):

- The `.toe` is shared by hand through cloud storage and each person works on a local copy, so per-machine settings live in `tox_manifest/.local`, never in a par.
- Usually two hosts, sometimes more: the Remote column shows the highest version among all other hosts.
- No host suffix in file names. The two people coordinate by talking; the `diverged` state catches accidents.
- The manifest lists only the tag-filtered COMPs, the same set as the TOX list.
- One header icon publishes and refreshes, instead of two.
- Claims ("I'm working on this") are wanted. Built as a note plus a `wip_since` time in the claimer's own manifest line, set from a row icon.
- Remote-only rows only inform. They do not offer to create the COMP from the file.
- Phase 2 before claims (order chosen 2026-11-22).

## Goal

Two people work on the same project from different machines. Each needs to see which TOX versions the other has, and decide when to update. A small text manifest per host is committed to git; `savetox` compares the other host's manifest with the local state.

Out of scope: moving the `.tox` files themselves.

## 1. Manifest

**One file per host, one JSON object per line: `<project folder>/tox_manifest/<host>.jsonl`.**

- Each host only writes its own file, so the two can never produce a merge conflict.
- One line per TOX, so saving one TOX changes one line in `git diff`.
- Stable output: fixed field order, rows sorted by key, UTF-8 without BOM, `\n` endings. Add `tox_manifest/* text eol=lf` to `.gitattributes`.
- No "generated at" stamp. If the new text equals the file on disk, nothing is written.

```
{"schema":1,"host":"kuro-mbp","user":"Kuro","os":"macOS"}
{"key":"tox/content/content","op":"/project1/content","file":"tox/content/content_v3-1-1.tox","version":"3.1.1","saved":"2026-11-22T03:01:00Z","td":"2025.33230","sha":"a1b2c3d4e5f6","base":"99887766aabb","size":202438,"wip":""}
```

| Field | Meaning |
|---|---|
| `key` | Join key: project-relative `externaltox` with `/` separators and the `_vX-Y-Z.tox` suffix stripped. Compared case-insensitively. |
| `op` | Operator path. Informational, never used for matching. |
| `file` | Project-relative path of the file `externaltox` points at. |
| `version` | `Toxversion` par. |
| `saved` | UTC time of the save (`Lastsaved` is local time, ambiguous across sites). |
| `td` | TD build that wrote the file. |
| `sha` | First 12 hex characters of the SHA-256 of the `.tox` bytes. Detects "same version number, different file". |
| `base` | `sha` of the file this save was made on top of. Recorded from phase 1, used in phase 3. |
| `size` | File size in bytes. |
| `wip` | Claim note, empty when unclaimed. One line, at most 60 characters. |
| `wip_since` | UTC time the claim was set. Used for its age and for marking it stale after 7 days. Added with claims; older files without it still load. |

The key is the TOX path, not the operator path, so a COMP renamed or moved in the network still matches on both hosts.

**Host identity:** the machine name, with an optional override in a gitignored `tox_manifest/.local` file. A par on `savetox` would be wrong: it is saved in the `.toe`, and if the `.toe` travels between machines one host would overwrite the other's manifest.

## 2. When it is written

- At the end of every TOX save (one hook in `_write_and_reload`). Writing is cheap and local; when to commit stays the user's decision.
- A "Publish" header icon does a full rescan, to catch deleted COMPs and changed filter pars.
- Both hosts need the same `Toplevel` and tag filter, otherwise "only on remote" gives false positives.

## 3. Comparison states

L is my live state, R the other host's manifest entry.

| State | Definition |
|---|---|
| `in_sync` | same version, same hash |
| `remote_newer` | R's version is higher, and R's file is on my disk with the matching hash |
| `remote_newer_missing` | R's version is higher, the file is not on my disk yet |
| `remote_newer_mismatch` | R's version is higher, the file exists but its hash differs |
| `local_newer` | my version is higher |
| `diverged` | same version, different hash |
| `remote_only` | in R's manifest, no tracked COMP here |
| `local_only` | tracked here, absent from R's manifest |
| `no_remote` | no other manifest found |
| `unknown` | no `Toxversion` par, or unparsable entry |

A dirty COMP keeps its state and gets an extra marker.

## 4. UI in the tool window

- **Remote** column: the other host's version and name, e.g. `3.1.1 kenji`.
- **Sync** column: one glyph coloured by state. Grey in sync, green update ready, amber file not arrived, blue he is behind, red diverged.
- **Update to remote** row icon, drawn only in `remote_newer`. It asks before discarding unsaved changes, warns if the file was written by a newer TD build, then repoints and reloads.
- **Remote-only rows**: a row without a COMP for each TOX only another host lists. A COMP hidden by the tag filter still counts as present.
- **Working On** column and a flag row icon for claims.
- One header icon publishes this host's manifest and re-reads the others.

## 5. Git

**The tool does not run git.** It only reads and writes files; pull, commit and push stay with the user.

Running git from inside TouchDesigner risks a frozen UI on a credential prompt, half-finished merges with no way to resolve them, and surprise commits. A read-only `git fetch` helper could come later, off the main thread.

## 6. Who is working on what

A `wip` note in the claiming host's own manifest line, toggled from the row. It is advisory and never blocks a save. The other host sees a badge such as `kenji: relighting (2d)`.

As built: the flag icon opens a small dialog with a text field (Claim / Release). The column shows all claims, coloured blue (mine), amber (theirs) or orange (both). After a major or minor save of a claimed TOX the tool offers to release the claim.

Limits: claims go stale (marked and uncoloured after 7 days), and a claim is only visible after commit, push and pull.

## 7. Edge cases

- **Version collision:** both hosts bump to `3.1.2` and produce the same file name with different bytes. Detected by the `diverged` states. The patch bump already skips past versions found on local disk; phase 3 extends that to versions seen in any manifest. A full fix needs a host suffix in the file name (open question).
- **TOX deleted on one host:** its line disappears, the other host sees `local_only`. No tombstones in the first version.
- **Different TD builds:** warn before updating to a file from a newer build, never block.
- **Paths:** store project-relative paths with `/`. A TOX outside the project folder is shown but excluded from the update action.
- **Single File save mode:** the file name carries no version, so the hash is the only discriminator.

## 8. Phases

1. **Publish and see.** Manifest writing, reading, comparison, the Remote and Sync columns, Publish and Refresh icons. New pure-Python module `saveManifest` so the logic can be tested outside TD. New "Sync" par page: enable toggle, manifest folder, compare-host menu, read-only host id.
2. **Act.** `Update_to_remote`, the update row icon, ghost rows for `remote_only`.
3. **Coordinate.** Claims, collision-avoiding bump across manifests, the `base` lineage check.
4. **Optional.** Read-only git fetch helper.

Testing: round-trip and state table in plain Python; in TD, a one-line diff per save and no write when nothing changed; a two-host simulation by copying the project folder with a different host override.

## 9. Open questions

Questions 1 to 4, 6 and 7 of the first draft are answered under "Decisions taken".

1. Should a remote-only row offer to create the COMP from the file? Today it only informs.
2. Should the patch bump skip versions seen in any manifest, so two hosts cannot produce the same version number? Today it only skips versions found on local disk.
