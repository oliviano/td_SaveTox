"""
SudoMagic | sudomagic.com
Authors   | Matthew Ragan, Ian Shelanskey
Contact   | contact@sudomagic.com
"""

# pure python
import json
import os
import platform
import re
import socket
from datetime import datetime, timezone

# td python mods
import saveOp
import saveUtils
import saveManifest
import listerFuncs


class ExternalFiles:
    """Externalizes COMPs to TOX files, tracks them, and re-saves them
    with semver versioning.

    Promoted on savetox, so every Capitalized member is reachable as
    `parent.save.<Member>` from anywhere inside the tool.
    """
    FLASH_DURATION = 14
    UNLOCK_TAGS = ["unlockOnSave"]
    DEFAULT_VERSION = "1.0.0"
    DEFAULT_TOX_FOLDER = "tox"
    DEFAULT_KEEP_VERSIONS = 5
    VERSION_SUFFIX = re.compile(r'_v(\d+)-(\d+)-(\d+)(?=\.tox$)')

    # Fallbacks for the save mode toggles on the Save Settings page
    # (`Versionsave` / `Canonicalsave`), used when savetox lacks the par.
    #   VERSION_SAVE   - every save writes a new myComp_v1-2-3.tox and the
    #                    externaltox par follows the newest one
    #   CANONICAL_SAVE - every save overwrites the single myComp.tox
    VERSION_SAVE = True
    CANONICAL_SAVE = False

    # About-page pars: name -> label
    ABOUT_PARS = {
        "Tdversion": "TD Version",
        "Tdbuild": "TD Build",
        "Toxversion": "Tox Version",
        "Lastsaved": "Last Saved",
    }

    def __init__(self, my_op) -> None:
        """Stands in place of an execute dat - ensures all elements start-up
        correctly

        Args
        ---------
        my_op (COMP):
        > the operator that is loading the current extension
        """
        self.my_op = my_op
        self._log_label = "--> SAVE COMP |"
        self.Defaultcolor = self.my_op.parGroup.Defaultcolor
        self.op_none_color = (0.545, 0.545, 0.545)
        self.Ext_ops_DAT = my_op.op('script_external_ops')

        self._ops_manager = saveOp.SaveOpManager(self.Ext_ops_DAT, self.my_op)

        self.Colors_map = self._colors_map()
        self.Tag_to_color_map = self._tag_to_color_map()
        self.Title_text_to_tag_map = self._title_text_to_tag_map()

        self._lister_COMP = my_op.op("widget_tox_finder/lister")
        self._search_text_COMP = my_op.op(
            "widget_tox_finder/container_search/text_search")

        # other hosts' manifests: {host: {lower-cased key: entry}}
        self._remote_manifests = {}
        # this host's own manifest lines: {lower-cased key: entry}
        self._my_manifest = {}

        self._setup()

        # display only - the host name is per machine, the .toe is shared
        if self.my_op.par['Hostid'] is not None:
            self.my_op.par.Hostid = self.Host_id

        if self.Manifest_enabled:
            self.Read_remote_manifests()

        self.Logtotextport(f"Start up and Init at {absTime.frame}")

    def _setup(self) -> None:
        """All set-up procedures for UI"""
        # resets lister
        self._lister_COMP.par.Refresh.pulse()

        # sets filter col for correct behavior
        self._lister_COMP.par.Filtercols = 0

        # set sort col
        self._lister_COMP.par.Sortcols = 3

    # ------------------------------------------------------------------
    # color / tag maps
    # ------------------------------------------------------------------

    def _colors_map(self) -> dict:
        """A map of colors
        Structure of this dict is:
            Classification (TouchDesigner | Python | Comments)
            -> Color type (e.g. python_extension or comment_note)
                -> tags and colors for type
        """
        par_group = self.my_op.parGroup
        return {
            "TouchDesigner": {
                "external_op": {
                    "color": par_group.Externalop,
                    "tags": []
                }
            },
            "Python": {
                "default": {
                    "color": par_group.Pythondefault,
                    "tags": []
                },
                "python_extension": {
                    "color": par_group.Pythonextension,
                    "tags": ["EXT"]
                },
                "python_module": {
                    "color": par_group.Pythonmodule,
                    "tags": ["MOD"]
                }
            },
            "Comments": {
                "bug": {
                    "color": par_group.Commentbug,
                    "tags": ["comment_bug"],
                    "title_text": "#BUG"
                },
                "hack": {
                    "color": par_group.Commenthack,
                    "tags": ["comment_hack"],
                    "title_text": "#HACK"
                },
                "fix": {
                    "color": par_group.Commentfix,
                    "tags": ["comment_fix"],
                    "title_text": "#FIXME"
                },
                "note": {
                    "color": par_group.Commentnote,
                    "tags": ["comment_note"],
                    "title_text": "#NOTE"
                }
            }
        }

    def _tag_to_color_map(self) -> dict:
        """Builds a map of colors by tag"""
        tag_to_color_map = {}
        for classification_vals in self.Colors_map.values():
            for type_vals in classification_vals.values():
                for each_tag in type_vals.get("tags"):
                    tag_to_color_map[each_tag] = type_vals.get("color")
        return tag_to_color_map

    def _title_text_to_tag_map(self) -> dict:
        """Builds a map of comment tags by annotate title text (#BUG, ...)"""
        return {
            type_vals.get("title_text"): type_vals.get("tags")[0]
            for type_vals in self.Colors_map.get("Comments").values()
        }

    @staticmethod
    def _rgb(color_group) -> tuple:
        """Evaluates an RGB parGroup to a plain (r, g, b) tuple"""
        return tuple(color_group[i].eval() for i in range(3))

    def _external_op_color(self) -> tuple:
        return self._rgb(
            self.Colors_map["TouchDesigner"]["external_op"]["color"])

    # ------------------------------------------------------------------
    # properties
    # ------------------------------------------------------------------

    @property
    def Ops_manager(self):
        return self._ops_manager

    def _setting(self, par_name: str, default):
        """Value of a savetox settings par, or `default` when this copy
        of the tool does not have that par."""
        par = self.my_op.par[par_name]
        return default if par is None else par.eval()

    @property
    def Version_save(self) -> bool:
        """True when every save writes a versioned snapshot"""
        return bool(self._setting('Versionsave', self.VERSION_SAVE))

    @property
    def Canonical_save(self) -> bool:
        """True when every save overwrites the single canonical TOX"""
        return bool(self._setting('Canonicalsave', self.CANONICAL_SAVE))

    @property
    def Default_tox_folder(self) -> str:
        """Project-relative folder used when no save location is given"""
        folder = str(self._setting('Defaulttoxfolder', '') or '').strip()
        folder = tdu.collapsePath(folder) if folder else self.DEFAULT_TOX_FOLDER
        return folder.replace('\\', '/').rstrip('/')

    @staticmethod
    def _abs_path(path: str) -> str:
        """Absolute form of a project-relative path"""
        expanded = tdu.expandPath(path)
        if not os.path.isabs(expanded):
            expanded = os.path.join(project.folder, expanded)
        return expanded

    def _can_save(self) -> bool:
        """False (with a log line) when both save modes are switched off"""
        if self.Version_save or self.Canonical_save:
            return True
        self.Logtotextport(
            "ERROR: nothing saved - both save modes are off. Turn on "
            "'Versioned Snapshots' or 'Single File' on savetox")
        return False

    @property
    def get_current_location(self):
        """The COMP shown in the currently focused network pane, or None
        when the focused pane is not a network editor."""
        pane = ui.panes.current
        if pane is None or pane.type != PaneType.NETWORKEDITOR:
            return None
        return pane.owner

    # ------------------------------------------------------------------
    # save entry points
    # ------------------------------------------------------------------

    def Prompt_to_save(self) -> None:
        """Saves the COMP of the focused network pane (ctrl+w).

        Already-external COMPs are re-saved; anything else is offered for
        externalization, optionally re-saving its external parent too.
        """
        current_loc = self.get_current_location

        # nothing to save from a non-network pane or the project root
        if current_loc is None or current_loc.path == '/':
            return

        # already external - save over it
        if current_loc.par.externaltox.eval() != '':
            # only warn about overwriting when the canonical file is
            # actually being written
            if self.Canonical_save:
                confirmation = ui.messageBox(
                    "TOX Save",
                    "Replacing External\n\n"
                    "You are about to overwrite an external TOX",
                    buttons=["Cancel", "Continue"])
                if not confirmation:
                    return

            self.Save_over_tox(current_loc)
            return

        # not external yet - ask about externalizing
        title = "Externalize Tox"
        msg = ("This TOX is not yet externalized\n\n"
               "Would you like to externalize this TOX?")
        parent_comp = current_loc.parent()

        if parent_comp.par.externaltox.eval() != '':
            choice = ui.messageBox(
                title, msg,
                buttons=["No", "This COMP Only", "This COMP and the Parent"])

            if choice in (1, 2):
                self.Save_tox(current_loc)

            if choice == 2:
                self.Save_over_tox(parent_comp)

        else:
            choice = ui.messageBox(title, msg, buttons=["No", "Yes"])

            if choice == 1:
                self.Save_tox(current_loc)

    def Save_over_tox(self, current_loc, specify_version: str = '',
                      reload: bool = True) -> None:
        """Re-saves an already-external COMP.

        Bumps the patch version unless `specify_version` (e.g. '2.0.0')
        is supplied. A COMP without an externaltox path is given one in the
        default TOX folder first.
        """
        if not self._can_save():
            return

        self._ensure_external_path(current_loc)

        # allow user to opt out of about page
        if self.my_op.par.Includeaboutpage:
            self.update_version_pars(current_loc, specify_version)
            self.update_save_time(current_loc)

        self._write_and_reload(current_loc, reload)
        self._manifest_changed()

    def Save_tox(self, current_loc, save_loc: str = None) -> None:
        """Externalizes a COMP for the first time.

        Creates `<save_loc>/<comp name>/<comp name>.tox`. When `save_loc`
        is omitted the user is asked to choose a folder, starting in the
        default TOX folder.
        """
        if not self._can_save():
            return

        if save_loc is None:
            start = self._abs_path(self.Default_tox_folder)
            save_loc = ui.chooseFolder(
                title="TOX Location",
                start=start if os.path.isdir(start) else project.folder)

        # user cancelled the folder dialog
        if not save_loc:
            return

        new_path = f"{save_loc}/{current_loc.name}"

        try:
            os.mkdir(new_path)
        except FileExistsError:
            # ask before reusing a directory that may already hold this TOX
            self.alert_failed_dir_creation(
                new_path=new_path, current_loc=current_loc)
            return
        except OSError as e:
            self.Logtotextport(f"ERROR: could not create {new_path} - {e}")
            return

        self._externalize(current_loc, save_loc)

    def _externalize(self, current_loc, save_loc: str,
                     replacing: bool = False) -> None:
        """Shared first-externalization steps for Save_tox and dialogChoice.

        `replacing` is True when the target directory already existed and
        the user chose to replace its contents.
        """
        # every externalized COMP gets a path - SudoTools included
        current_loc.par.externaltox = self._relative_tox_path(
            current_loc, save_loc)
        current_loc.par.savebackup = False

        # tag the COMP so it shows up in the (tag filtered) TOX list
        self._auto_tag(current_loc)

        # setup about page - allow user to supress about page at creation
        if self.my_op.par.Includeaboutpage:
            if replacing:
                self.update_version_pars(current_loc)
                self.update_save_time(current_loc)
            else:
                self.custom_page_setup(current_loc)

        self._write_and_reload(current_loc)

        # track new SaveOp
        self._ops_manager.Check_external_ops()
        self._manifest_changed()

    @staticmethod
    def _relative_tox_path(current_loc, save_loc: str) -> str:
        """Project-relative externaltox path for a COMP saved into save_loc"""
        name = current_loc.name
        rel_path = tdu.collapsePath(save_loc)

        # the location is the root of the project folder structure
        # (collapsePath returns the folder unchanged in that case)
        in_project_root = (os.path.normpath(save_loc)
                           == os.path.normpath(project.folder))
        if in_project_root or rel_path in ("$TOUCH", "", "."):
            return f"{name}/{name}.tox"

        return f"{rel_path}/{name}/{name}.tox"

    def _auto_tag(self, current_loc) -> None:
        """Adds the filter tag (Tagtofilterinclude, e.g. 'Ext') to a COMP
        that is being externalized, so it is listed without manual tagging.

        Can be switched off with the optional `Autotag` toggle on savetox.
        """
        auto_tag_par = self.my_op.par['Autotag']
        if auto_tag_par is not None and not auto_tag_par.eval():
            return

        tag = self.my_op.par.Tagtofilterinclude.eval().strip()
        if tag and tag not in current_loc.tags:
            current_loc.tags.add(tag)
            self.Logtotextport(f"{current_loc} tagged '{tag}'")

    def _ensure_external_path(self, current_loc) -> None:
        """Gives a COMP without an externaltox path the default one:
        `<Default TOX Folder>/<name>/<name>.tox`, creating the folder."""
        if current_loc.par.externaltox.eval() != '':
            return

        name = current_loc.name
        rel_path = f"{self.Default_tox_folder}/{name}/{name}.tox"
        os.makedirs(os.path.dirname(self._abs_path(rel_path)), exist_ok=True)

        current_loc.par.externaltox = rel_path
        current_loc.par.savebackup = False
        self._auto_tag(current_loc)
        self.Logtotextport(f"{current_loc} had no TOX path - using {rel_path}")

    def _canonical_path(self, current_loc) -> str:
        """externaltox path with any _vX-Y-Z version suffix removed"""
        return self.VERSION_SUFFIX.sub('', current_loc.par.externaltox.eval())

    def _write_and_reload(self, current_loc, reload: bool = True) -> None:
        """Writes the TOX file(s) to disk, then reloads the COMP from its
        externaltox path so TD clears the dirty flag."""
        self._save_tox(current_loc)

        if self.Version_save:
            self.Save_versioned_tox(current_loc)

        # RELOAD: clears the dirty flag
        if reload:
            saveUtils.Reload_tox(current_loc)

    def _save_tox(self, current_loc) -> None:
        """Writes the canonical TOX (in Single File mode) and refreshes all
        save related UI feedback."""
        self.preToxSave(current_loc)

        if self.Canonical_save:
            # always the un-versioned file name, also right after switching
            # over from versioned mode
            external_path = self._canonical_path(current_loc)
            current_loc.par.externaltox = external_path
            current_loc.save(external_path)

        self.postToxSave(current_loc)

        # set color for COMP
        current_loc.color = self._external_op_color()

        # flash color
        saveUtils.flash_bg(
            self._rgb(self.my_op.parGroup.Bgcolor),
            ExternalFiles.FLASH_DURATION)

        self.Set_external_file_colors()
        self.Set_annotate_colors()

        self._ops_manager.Update_save_op_by_path(current_loc, False)

        if self.Canonical_save:
            self.Logtotextport(
                f"{current_loc} saved to {project.folder}/{external_path}")

    # ------------------------------------------------------------------
    # versioning
    # ------------------------------------------------------------------

    @staticmethod
    def _version_tuple(version_str: str) -> tuple:
        """Convert '2.3.1' to (2, 3, 1) for comparison."""
        try:
            return tuple(int(x) for x in version_str.split('.'))
        except ValueError:
            return (0, 0, 0)

    def _find_latest_disk_version(self, current_loc) -> str:
        """Scans the TOX directory for versioned snapshots and returns the
        highest semver found, or '' if none."""
        versions = self.List_versions(current_loc)
        return versions[0] if versions else ''

    def _tox_directory(self, current_loc) -> str:
        """Absolute directory holding the COMP's TOX files, '' if none"""
        ext_path = current_loc.par.externaltox.eval()
        if not ext_path:
            return ''
        return os.path.dirname(self._abs_path(ext_path))

    def _version_file_name(self, current_loc, version: str) -> str:
        return f"{current_loc.name}_v{version.replace('.', '-')}.tox"

    def List_versions(self, current_loc) -> list:
        """Versions of a COMP found as snapshots on disk, newest first.
        e.g. ['2.0.0', '1.0.1', '1.0.0']"""
        directory = self._tox_directory(current_loc)
        pattern = re.compile(
            rf'{re.escape(current_loc.name)}_v(\d+)-(\d+)-(\d+)\.tox$')
        found = []
        try:
            for fname in os.listdir(directory):
                m = pattern.match(fname)
                if m:
                    found.append(tuple(int(x) for x in m.groups()))
        except (FileNotFoundError, NotADirectoryError):
            return []
        return ['.'.join(str(x) for x in ver)
                for ver in sorted(found, reverse=True)]

    def Loaded_version(self, current_loc) -> str:
        """Version of the snapshot the COMP currently points at, read from
        the externaltox file name. '' when it points at a canonical TOX."""
        m = self.VERSION_SUFFIX.search(current_loc.par.externaltox.eval())
        return '.'.join(m.groups()) if m else ''

    def Load_version(self, current_loc, version: str) -> bool:
        """Points a COMP at an existing snapshot (e.g. '1.0.1') and reloads
        it from disk. Unsaved changes inside the COMP are lost."""
        directory = self._tox_directory(current_loc)
        file_name = self._version_file_name(current_loc, version)

        if not os.path.isfile(os.path.join(directory, file_name)):
            self.Logtotextport(
                f"ERROR: {file_name} not found in {directory}")
            return False

        rel_dir = os.path.dirname(current_loc.par.externaltox.eval())
        current_loc.par.externaltox = (
            f"{rel_dir}/{file_name}" if rel_dir else file_name)
        saveUtils.Reload_tox(current_loc)

        self.Logtotextport(f"{current_loc} loaded v{version}")
        self._ops_manager.Check_external_ops()
        self._manifest_changed()
        return True

    def Prune_versions(self, current_loc, keep: int = None) -> list:
        """Deletes old snapshots from disk, keeping the newest `keep`
        (default: the `Keepversions` par) and always the loaded one.
        Returns the deleted file names."""
        if keep is None:
            keep = int(self._setting(
                'Keepversions', self.DEFAULT_KEEP_VERSIONS))
        keep = max(1, keep)

        directory = self._tox_directory(current_loc)
        loaded = self.Loaded_version(current_loc)
        removed = []

        for version in self.List_versions(current_loc)[keep:]:
            if version == loaded:
                continue
            file_name = self._version_file_name(current_loc, version)
            os.remove(os.path.join(directory, file_name))
            removed.append(file_name)

        self.Logtotextport(
            f"{current_loc} pruned {len(removed)} old version(s)")
        return removed

    def _versioned_path(self, current_loc) -> str:
        """Derives a versioned snapshot path from the externaltox path.
        e.g. $TOUCH/myComp/myComp.tox -> $TOUCH/myComp/myComp_v2-2-2.tox
        Strips any existing _vX-X-X suffix first so versioned paths never
        compound.
        """
        ext_path = current_loc.par.externaltox.eval()
        version_par = current_loc.par['Toxversion']
        if not version_par:
            return ext_path
        version_str = 'v' + version_par.eval().replace('.', '-')
        base = self._canonical_path(current_loc).rsplit('.tox', 1)[0]
        return f"{base}_{version_str}.tox"

    def Save_versioned_tox(self, current_loc) -> None:
        """Saves a versioned snapshot.
        Unless Single File mode is on, also updates externaltox to point to
        the versioned file. Warns if a higher version already exists on disk.
        """
        current_ver = (current_loc.par['Toxversion'].eval()
                       if current_loc.par['Toxversion'] else '0.0.0')
        latest_on_disk = self._find_latest_disk_version(current_loc)
        if latest_on_disk and (self._version_tuple(latest_on_disk)
                               > self._version_tuple(current_ver)):
            self.Logtotextport(
                f"WARNING: {current_loc.name} - disk has v{latest_on_disk}, "
                f"saving v{current_ver}")

        versioned_path = self._versioned_path(current_loc)
        current_loc.save(versioned_path)

        if not self.Canonical_save:
            current_loc.par.externaltox = versioned_path

        self.Logtotextport(
            f"{current_loc} versioned -> {project.folder}/{versioned_path}")

    # ------------------------------------------------------------------
    # save events
    # ------------------------------------------------------------------

    def preToxSave(self, tox) -> None:
        """pre tox save event handling"""
        for child in tox.findChildren(tags=self.UNLOCK_TAGS):
            child.lock = False

    def postToxSave(self, tox) -> None:
        """post tox save event handling"""
        for child in tox.findChildren(tags=self.UNLOCK_TAGS):
            child.lock = True

    def alert_failed_dir_creation(self, **kwargs) -> None:
        op.TDResources.op('popDialog').Open(
            title="OVERWRITE WARNING",
            text="""It looks like there is an existing
TOX in this directory.

Please check to make sure
this TOX does not already exist.
""",
            buttons=["Cancel", "Replace"],
            # the dialog is shared (the claim dialog turns the text entry on)
            textEntry=False,
            enterButton=False,
            escButton=1,
            callback=self.dialogChoice,
            details=kwargs
        )

    def dialogChoice(self, info: dict) -> None:
        """Callback of the overwrite warning - externalizes into the already
        existing directory when the user picks 'Replace'."""
        if info.get('button') == 'Cancel':
            return

        details = info.get('details')
        self._externalize(
            details.get('current_loc'),
            os.path.dirname(details.get('new_path')),
            replacing=True)

    # ------------------------------------------------------------------
    # about page
    # ------------------------------------------------------------------

    def update_custom_str_par(self, targetOp, par, value, par_label=None):
        """Sets a read-only string par, creating it on the About page first
        when it does not exist yet."""
        if targetOp.par[par] is None:
            about_page = targetOp.appendCustomPage("About")
            about_page.appendStr(
                par, label=par_label or self.ABOUT_PARS.get(par, par))
            targetOp.par[par].readOnly = True

        targetOp.par[par] = value

    def update_version_pars(self, target_op, new_version: str = '') -> None:
        """Updates semver of TOX: an explicit `new_version` wins, otherwise
        the patch number is bumped (or the par is created at 1.0.0)."""
        if target_op.par['Toxversion'] is None:
            version = new_version or self.DEFAULT_VERSION
        else:
            version = new_version or self._patch_update(target_op)

        self.update_custom_str_par(target_op, "Toxversion", version)
        self.update_custom_str_par(target_op, "Tdversion", app.version)
        self.update_custom_str_par(target_op, "Tdbuild", app.build)

    def _patch_update(self, target_op) -> str:
        """Returns the current Toxversion with the patch number bumped.
        An unreadable version falls back to 1.0.0 before bumping.

        In versioned mode the bump starts from the newest snapshot on disk
        when that is higher (e.g. after loading an older version), so an
        existing snapshot is never overwritten."""
        try:
            parts = [int(x) for x in target_op.par.Toxversion.eval().split('.')]
        except ValueError:
            parts = [1, 0, 0]
        parts = (parts + [0, 0, 0])[:3]

        if self.Version_save:
            latest = self._find_latest_disk_version(target_op)
            if latest and list(self._version_tuple(latest)) > parts:
                self.Logtotextport(
                    f"{target_op.name} - newer v{latest} on disk, "
                    f"saving as the next version after it")
                parts = list(self._version_tuple(latest))

        major, minor, patch = parts
        return f"{major}.{minor}.{patch + 1}"

    def update_save_time(self, target_op) -> None:
        self.update_custom_str_par(
            target_op, "Lastsaved", saveUtils.current_save_time())

    def custom_page_setup(self, target_op) -> None:
        """Creates / resets the About page of a freshly externalized COMP"""
        self.update_custom_str_par(target_op, "Tdversion", app.version)
        self.update_custom_str_par(target_op, "Tdbuild", app.build)
        self.update_custom_str_par(
            target_op, "Toxversion", self.DEFAULT_VERSION)
        self.update_save_time(target_op)

    # ------------------------------------------------------------------
    # logging / colors
    # ------------------------------------------------------------------

    def Logtotextport(self, logMsg) -> None:
        ui.status = f"{self._log_label} {logMsg}"
        if self.my_op.par.Logtotextport:
            print(f"{self._log_label} {logMsg}")

    def Set_ext_tox_colors(self) -> None:
        color = self._external_op_color()
        for each_op in saveUtils.find_external_ops():
            each_op.color = color

    def Set_external_file_colors(self) -> None:
        """Sets colors for external files"""
        default_color = self.Colors_map["Python"]["default"]["color"]

        for each_dat in saveUtils.find_all_dats():
            dat_color = default_color
            for each_tag in each_dat.tags:
                dat_color = self.Tag_to_color_map.get(each_tag, dat_color)
            each_dat.color = self._rgb(dat_color)

    def Set_annotate_colors(self) -> None:
        for each_comment in saveUtils.find_all_comments():
            # update tag on annotates from the first word of their title
            first_word = each_comment.par.Titletext.eval().split(" ")[0]
            target_tag = self.Title_text_to_tag_map.get(first_word)
            if target_tag:
                each_comment.tags.add(target_tag)

            # set color by tag
            for each_tag in each_comment.tags:
                tag_color = self.Tag_to_color_map.get(each_tag)
                if tag_color is not None:
                    each_comment.color = self._rgb(tag_color)

    # ------------------------------------------------------------------
    # navigation / window
    # ------------------------------------------------------------------

    def Open_network_location(self, network_location) -> None:
        """Moves network to save location"""
        ui.panes.current.owner = network_location
        ui.panes.current.home()

    def Rebuild_op_list(self) -> None:
        """Rebuilds the tracked external op list from scratch, respecting
        current filter settings."""
        self._ops_manager.Rebuild_op_list()

    def Ignore_current_changes(self, op_id: int) -> None:
        self._ops_manager.Ignore_current_dirty_state(op_id)

    def Open_floating_external_tox_window(self) -> None:
        """Opens window for tox files"""
        # refresh the list so the dirty and sync states are current
        if self.Manifest_enabled:
            self.Read_remote_manifests()
        self._ops_manager.Check_external_ops()
        self.my_op.op('script1').cook(force=True)
        self.my_op.op('window1').par.winopen.pulse()

    # ------------------------------------------------------------------
    # manifest - sharing TOX versions between hosts through git
    # ------------------------------------------------------------------

    # widths of the list columns that only show while sharing is on
    SYNC_COLUMN_WIDTHS = {'remote': 110, 'sync': 115, 'wip': 230,
                          'update': 30, 'claim': 30}
    WINDOW_WIDTH = 791

    # Material Design Icons used in the per-row sync cells
    UPDATE_ICON = chr(0xF01DA)      # download
    CLAIM_ON_ICON = chr(0xF023B)    # flag
    CLAIM_OFF_ICON = chr(0xF023D)   # flag outline

    @property
    def Manifest_enabled(self) -> bool:
        return bool(self._setting('Manifestenable', False))

    @property
    def Manifest_folder(self) -> str:
        """Absolute folder holding one manifest file per host"""
        folder = str(self._setting('Manifestfolder', '') or '').strip()
        return self._abs_path(folder or 'tox_manifest')

    def _local_settings(self) -> dict:
        """Per-machine settings from `<manifest folder>/.local` (a small
        JSON file kept out of git), e.g. {"host": "kuro", "user": "Kuro"}.
        They cannot be pars: the .toe is shared between the hosts."""
        try:
            with open(os.path.join(self.Manifest_folder, '.local'),
                      'r', encoding='utf-8') as local_file:
                data = json.load(local_file)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    @property
    def Host_id(self) -> str:
        """Name of this machine in the manifest: the `host` of the .local
        file when set, else the machine name"""
        name = self._local_settings().get('host') or socket.gethostname()
        return saveManifest.host_id(str(name))

    def Manifest_path(self, host: str = None) -> str:
        return os.path.join(
            self.Manifest_folder, (host or self.Host_id) + saveManifest.FILE_EXT)

    def _project_relative(self, path: str) -> str:
        """Project-relative posix form of a TOX path, '' when the file is
        outside the project folder (it cannot be shared by path)"""
        absolute = self._abs_path(path)
        try:
            relative = os.path.relpath(absolute, project.folder)
        except ValueError:
            return ''
        if relative.startswith('..'):
            return ''
        return saveManifest.posix(relative)

    def _tox_key(self, comp) -> str:
        """Lower-cased manifest key of a COMP, '' when its TOX is outside
        the project folder"""
        rel_file = self._project_relative(comp.par.externaltox.eval())
        return saveManifest.tox_key(rel_file).lower() if rel_file else ''

    def _manifest_entry(self, comp, previous: dict, claims: dict) -> dict:
        """Manifest line of one tracked COMP, or None when it has no TOX
        file inside the project folder.

        `claims` holds the claim notes being changed by this write:
        {lower-cased key: note}, '' releases a claim."""
        rel_file = self._project_relative(comp.par.externaltox.eval())
        if not rel_file:
            return None

        abs_file = self._abs_path(rel_file)
        sha, size = saveManifest.file_sha(abs_file)
        if not sha:
            return None

        key = saveManifest.tox_key(rel_file)
        old = previous.get(key.lower(), {})
        unchanged = old.get('sha') == sha

        # the save time is only taken when the file changed, so a file
        # merely touched by a sync tool does not alter the manifest
        if unchanged and old.get('saved'):
            saved = old['saved']
        else:
            saved = saveManifest.time_stamp(datetime.fromtimestamp(
                os.path.getmtime(abs_file), timezone.utc))

        wip = old.get('wip', '')
        wip_since = old.get('wip_since', '')
        if key.lower() in claims:
            wip = saveManifest.clean_claim(claims[key.lower()])
            wip_since = saveManifest.time_stamp() if wip else ''

        return {
            'key': key,
            'op': comp.path,
            'file': rel_file,
            'version': (comp.par['Toxversion'].eval()
                        if comp.par['Toxversion'] is not None else ''),
            'saved': saved,
            'td': (comp.par['Tdbuild'].eval()
                   if comp.par['Tdbuild'] is not None else ''),
            'sha': sha,
            # the file this save was made on top of
            'base': old.get('base', '') if unchanged else old.get('sha', ''),
            'size': size,
            'wip': wip,
            'wip_since': wip_since,
        }

    def Write_manifest(self, claims: dict = None) -> bool:
        """Writes this host's manifest: one line per tracked COMP (the same
        set as the TOX list). Returns True when the file changed.

        `claims` changes claim notes: {lower-cased key: note}."""
        path = self.Manifest_path()
        _, previous = saveManifest.read_file(path)

        entries = []
        for each in self._ops_manager.External_ops:
            if not each.td_op.valid:
                continue
            entry = self._manifest_entry(each.td_op, previous, claims or {})
            if entry is not None:
                entries.append(entry)

        header = {'schema': saveManifest.SCHEMA, 'host': self.Host_id,
                  'os': platform.system()}
        user = self._local_settings().get('user')
        if user:
            header['user'] = str(user)

        self._my_manifest = {each['key'].lower(): each for each in entries}

        written = saveManifest.write_file(
            path, saveManifest.dump(header, entries))
        if written:
            self.Logtotextport(
                f"manifest updated - {len(entries)} TOX -> {path}")
        return written

    def Read_remote_manifests(self) -> dict:
        """Loads the manifests of all other hosts found in the manifest
        folder (and this host's own, for its claims).
        Returns {host: {key: entry}}."""
        my_file = os.path.basename(self.Manifest_path())
        remote = {}
        try:
            file_names = sorted(os.listdir(self.Manifest_folder))
        except OSError:
            file_names = []

        for file_name in file_names:
            if (not file_name.endswith(saveManifest.FILE_EXT)
                    or file_name == my_file):
                continue
            header, entries = saveManifest.read_file(
                os.path.join(self.Manifest_folder, file_name))
            host = header.get('host') or file_name[:-len(saveManifest.FILE_EXT)]
            remote[str(host)] = entries

        self._remote_manifests = remote
        _, self._my_manifest = saveManifest.read_file(self.Manifest_path())
        return remote

    def _best_remote(self, key: str):
        """(host, entry) of the highest version any other host has of a
        TOX, or None"""
        return saveManifest.best_remote([
            (host, entries[key])
            for host, entries in self._remote_manifests.items()
            if key in entries])

    def _remote_file(self, entry: dict) -> str:
        """Absolute path on THIS machine of the file a remote entry names,
        '' when the entry points outside the project folder"""
        rel_file = saveManifest.posix(str(entry.get('file', '')))
        if not rel_file.lower().endswith('.tox'):
            return ''
        absolute = os.path.normpath(
            os.path.join(project.folder, *rel_file.split('/')))
        return absolute if self._project_relative(absolute) else ''

    def _sync_state(self, comp) -> tuple:
        """(host, entry, state) of a COMP against the other hosts.
        host and entry are None when no other host lists this TOX."""
        key = self._tox_key(comp)
        if not key:
            return (None, None, '')

        best = self._best_remote(key)
        if best is None:
            return (None, None, saveManifest.LOCAL_ONLY)

        host, entry = best
        local_sha, _ = saveManifest.file_sha(
            self._abs_path(comp.par.externaltox.eval()))
        remote_file = self._remote_file(entry)
        remote_file_sha = (saveManifest.file_sha(remote_file)[0]
                           if remote_file else '')

        state = saveManifest.compare(
            (comp.par['Toxversion'].eval()
             if comp.par['Toxversion'] is not None else ''),
            local_sha, entry, remote_file_sha)
        return (host, entry, state)

    def Sync_status(self, comp) -> tuple:
        """(remote text, state) of a COMP against the other hosts, e.g.
        ('3.1.1 kenji', 'update ready'). ('', '') when the manifest is off
        or no other host lists this TOX."""
        if not self.Manifest_enabled or not self._remote_manifests:
            return ('', '')

        host, entry, state = self._sync_state(comp)
        if entry is None:
            return ('', state)
        return (f"{entry.get('version', '?')}  {host}", state)

    def Remote_version(self, comp):
        """(host, entry) of the newest version another host has of a COMP's
        TOX, or None. entry holds version, file, td, saved, sha, ..."""
        host, entry, _ = self._sync_state(comp)
        return None if entry is None else (host, entry)

    def Update_to_remote(self, comp) -> bool:
        """Points a COMP at the newer version another host published and
        reloads it. Only when that file is on this machine and matches the
        published hash ('update ready'). Unsaved changes are lost."""
        host, entry, state = self._sync_state(comp)
        if state != saveManifest.REMOTE_NEWER:
            self.Logtotextport(
                f"{comp.name} not updated - state is '{state or 'unknown'}'")
            return False

        comp.par.externaltox = saveManifest.posix(str(entry['file']))
        saveUtils.Reload_tox(comp)

        self.Logtotextport(
            f"{comp} updated to v{entry.get('version', '?')} from {host}")
        self._ops_manager.Check_external_ops()
        self._manifest_changed()
        # the row state changed with the manifest - redraw the list
        self._ops_manager.Check_external_ops()
        return True

    def Remote_only(self) -> list:
        """TOX files other hosts list that no COMP in this project uses.
        One dict per TOX: name, key, host, version, file, file_here,
        remote, wip, wip_state."""
        if not self.Manifest_enabled or not self._remote_manifests:
            return []

        remote_keys = set()
        for entries in self._remote_manifests.values():
            remote_keys.update(entries)

        remote_keys -= {self._tox_key(each.td_op)
                        for each in self._ops_manager.External_ops
                        if each.td_op.valid}
        if not remote_keys:
            return []

        # a COMP hidden by the tag filter still counts as "here"
        remote_keys -= {self._tox_key(each)
                        for each in root.findChildren(type=COMP)
                        if each.par.externaltox.eval() != ''}

        found = []
        for key in sorted(remote_keys):
            host, entry = self._best_remote(key)
            remote_file = self._remote_file(entry)
            wip, wip_state = self._claim_status(key)
            found.append({
                'name': str(entry.get('key', key)).split('/')[-1],
                'key': key,
                'host': host,
                'version': str(entry.get('version', '?')),
                'file': str(entry.get('file', '')),
                'file_here': bool(remote_file and os.path.isfile(remote_file)),
                'remote': f"{entry.get('version', '?')}  {host}",
                'wip': wip,
                'wip_state': wip_state,
            })
        return found

    # claims - "I'm working on this" notes, advisory only

    def _claim_status(self, key: str) -> tuple:
        """(text, state) of the claims on a TOX key, e.g.
        ('kenji: relighting (2d)', 'theirs')"""
        mine = str(self._my_manifest.get(key, {}).get('wip', '') or '')
        others = [
            (host, str(entries[key].get('wip', '') or ''),
             str(entries[key].get('wip_since', '') or ''))
            for host, entries in self._remote_manifests.items()
            if key in entries]
        return saveManifest.claim_summary(mine, others)

    def Claim_status(self, comp) -> tuple:
        """(text, state) of the claims on a COMP. state is 'mine',
        'theirs', 'both', 'stale' or ''."""
        key = self._tox_key(comp)
        if not self.Manifest_enabled or not key:
            return ('', '')
        return self._claim_status(key)

    def My_claim(self, comp) -> str:
        """This host's claim note on a COMP, '' when it has none"""
        return str(self._my_manifest.get(
            self._tox_key(comp), {}).get('wip', '') or '')

    def Set_claim(self, comp, note: str = '') -> bool:
        """Marks a COMP as "I'm working on this" with a short note; an
        empty note releases the claim. The note lives in this host's
        manifest, so the others see it after commit, push and pull."""
        key = self._tox_key(comp)
        if not self.Manifest_enabled or not key:
            self.Logtotextport(
                f"{comp.name} not claimed - 'Share TOX Versions' is off "
                "or the TOX is outside the project folder")
            return False

        note = saveManifest.clean_claim(note)
        self._ops_manager.Check_external_ops()
        self.Write_manifest(claims={key: note})
        self._ops_manager.Check_external_ops()
        self.Logtotextport(
            f"{comp.name} claimed: {note}" if note
            else f"{comp.name} claim released")
        return True

    def Sync_row(self, comp) -> dict:
        """Everything the TOX list shows about a COMP and the other hosts:
        remote, sync, update (icon), claim (icon), wip, wip_state"""
        remote, state = self.Sync_status(comp)
        wip, wip_state = self.Claim_status(comp)
        claimed = wip_state in (saveManifest.CLAIM_MINE,
                                saveManifest.CLAIM_BOTH)
        return {
            'remote': remote,
            'sync': state,
            'update': (self.UPDATE_ICON
                       if state == saveManifest.REMOTE_NEWER else ''),
            'claim': self.CLAIM_ON_ICON if claimed else self.CLAIM_OFF_ICON,
            'wip': wip,
            'wip_state': wip_state,
        }

    def Sync_manifest(self) -> None:
        """Header icon: publish my manifest, re-read the other hosts' and
        refresh the list. Git pull / commit / push stay manual."""
        if not self.Manifest_enabled:
            return
        self._ops_manager.Check_external_ops()
        self.Write_manifest()
        self.Read_remote_manifests()
        self._ops_manager.Check_external_ops()

    def _manifest_changed(self) -> None:
        """Called after anything that changes which TOX file a COMP uses"""
        if self.Manifest_enabled:
            self.Write_manifest()

    def Apply_sync_columns(self) -> None:
        """Shows / hides the sharing columns of the TOX list to match the
        `Manifestenable` toggle, and resizes the window."""
        enabled = self.Manifest_enabled
        col_define = self.my_op.op('widget_tox_finder/listerConfig/colDefine')
        for column, width in self.SYNC_COLUMN_WIDTHS.items():
            col_define['width', column] = width if enabled else 0

        self.my_op.op('widget_tox_finder').par.w = self.WINDOW_WIDTH + (
            sum(self.SYNC_COLUMN_WIDTHS.values()) if enabled else 0)

        if enabled:
            self.Sync_manifest()
        else:
            self._ops_manager.Check_external_ops()
        self._lister_COMP.par.Refresh.pulse()

    # ------------------------------------------------------------------
    # unsaved (dirty) TOX handling
    # ------------------------------------------------------------------

    def Dirty_ops(self) -> list:
        """Tracked external COMPs with unsaved changes, deepest first so
        children are saved before the parents that contain them."""
        dirty = [each.td_op for each in self._ops_manager.External_ops
                 if each.td_op.valid and each.is_dirty]
        return sorted(dirty, key=lambda comp: comp.path.count('/'),
                      reverse=True)

    def Save_all_dirty(self, reload: bool = True) -> list:
        """Saves every tracked COMP that has unsaved changes.
        Returns the saved COMPs."""
        dirty = self.Dirty_ops()
        for each_comp in dirty:
            self.Save_over_tox(each_comp, reload=reload)

        self._ops_manager.Check_external_ops()
        self.Logtotextport(f"saved {len(dirty)} unsaved TOX")
        return dirty

    def Check_unsaved(self, event: str = 'save') -> None:
        """Offers to save unsaved TOXes when the project is saved or closed
        (`event` is 'save' or 'exit'). Switched by the `Checkunsaved` par."""
        if not self._setting('Checkunsaved', False):
            return

        dirty = self.Dirty_ops()
        if not dirty:
            return

        names = '\n'.join(f"  {each.name}" for each in dirty[:12])
        if len(dirty) > 12:
            names += f"\n  ... and {len(dirty) - 12} more"

        when = ("Before the project is saved" if event == 'save'
                else "Before you leave")
        choice = ui.messageBox(
            "Unsaved TOX",
            f"{when}: {len(dirty)} external TOX "
            f"have unsaved changes.\n\n{names}\n\nSave them now?",
            buttons=["Skip", "Save All"])

        if choice == 1:
            self.Save_all_dirty(reload=(event != 'exit'))

    def Keyboard_input(self, shortcut: str) -> None:
        """Keyboard input handler"""
        shortcut_lookup = {
            'ctrl.w': self.Prompt_to_save,
            'ctrl.shift.w': self.Open_floating_external_tox_window
        }

        func = shortcut_lookup.get(shortcut)
        if func is not None:
            func()

    # NOTE - utils for search
    def Edit_search(self, search_val: str) -> None:
        """Updates filter string par"""
        self._lister_COMP.par.Filterstring = search_val

    def _clear_search(self) -> None:
        """Clears filter string"""
        self._search_text_COMP.par.text = ''

    # NOTE - lister utils
    def Lister_on_click(self, info: dict) -> None:
        """Uses the listerFuncs module to run any onClick functions"""
        listerFuncs.parse_col(info)

    def Lister_on_click_right(self, info: dict) -> None:
        """Uses the listerFuncs module to run any onRightClick functions"""
        listerFuncs.parse_right_click(info)
