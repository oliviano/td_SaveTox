"""
SudoMagic | sudomagic.com
Authors   | Matthew Ragan, Ian Shelanskey
Contact   | contact@sudomagic.com
"""

# td python mods
import saveUtils


class SaveOpManager:
    """Keeps the list of tracked external COMPs (as SaveOp objects) that
    feeds the TOX list of the tool window.
    """

    def __init__(self, ext_ops_DAT, my_op) -> None:
        """
        Args
        ---------------
        ext_ops_DAT (`scriptDAT`)
        > DAT that renders External_ops as a table - force cooked on change

        my_op (`COMP`)
        > savetox, read for the filter settings
        """
        self.Ext_ops_DAT = ext_ops_DAT
        self._my_op = my_op
        self.External_ops: list = []
        self._build_op_list()

    def _log(self, msg: str) -> None:
        logger = getattr(self._my_op, 'Logtotextport', None)
        (logger or print)(msg)

    def add_save_op(self, td_operator) -> None:
        """Starts tracking a COMP"""
        self.External_ops.append(SaveOp(td_operator))

    # NOT IMPLEMENTED — placeholder for future hash-based status check
    def check_hash_status(self) -> None:
        pass

    @property
    def external_ops(self) -> list:
        """Returns a list of all external comps, respecting filter settings."""
        filter_per_tag = self._my_op.par.Filterpertag.eval()
        top_level = self._my_op.par.Toplevel.eval()
        tag_filter = self._my_op.par.Tagtofilterinclude.eval().strip()

        search_root = top_level if top_level else root

        children = search_root.findChildren(type=COMP)
        external_ops = [c for c in children if c.par.externaltox.eval() != '']

        if filter_per_tag and tag_filter:
            external_ops = [c for c in external_ops if tag_filter in c.tags]

        return external_ops

    # NOT CALLED — kept as foundation, relies on is_dirty which now uses op.dirty natively
    @property
    def dirty_ops(self) -> list:
        return [each for each in self.External_ops if each.is_dirty]

    def _build_op_list(self) -> None:
        """Tracks every external COMP matching the filter settings"""
        for each in self.external_ops:
            self.add_save_op(each)

    def Check_external_ops(self) -> None:
        """Incremental update - drops COMPs that no longer exist and adds
        newly externalized ones. Does not re-apply filter changes to ops
        that are already tracked (see Rebuild_op_list)."""
        # a reload can give a COMP a new op id, so ids are read live and
        # de-duplicated here
        tracked_ids = set()
        still_tracked = []
        for each in self.External_ops:
            if each.td_op.valid and each.id not in tracked_ids:
                tracked_ids.add(each.id)
                still_tracked.append(each)
        self.External_ops = still_tracked

        for each_external in self.external_ops:
            if each_external.id not in tracked_ids:
                self.add_save_op(each_external)
                self._log(f"adding new tracked external op {each_external}")

        # force cook DAT with list of all ops
        self.Ext_ops_DAT.cook(force=True)

    def Rebuild_op_list(self) -> None:
        """Clears and fully rebuilds External_ops from the current filter settings."""
        self.External_ops.clear()
        self._build_op_list()
        self.Ext_ops_DAT.cook(force=True)

    # NOT CALLED — hash-based dirty check, unfinished. is_dirty now uses op.dirty natively
    def Dirty_check(self) -> None:
        self.Check_external_ops()
        for each_op in self.External_ops:
            each_op.dirty_check()

    # NOT CALLED — depends on hash system, unfinished
    def Ignore_current_dirty_state(self, target_op_id: int) -> None:
        target_op: SaveOp = self.get_save_op_by_id(target_op_id)
        target_op.op_hash = saveUtils.gen_hash_from_op(target_op.td_op)

    def get_save_op_by_id(self, op_id: int):
        """Returns the tracked SaveOp with a matching op id, or None"""
        for each_op in self.External_ops:
            if each_op.id == op_id:
                return each_op
        return None

    # NOT IMPLEMENTED — was the hash-system hook called after every save
    def Update_save_op_by_path(self, path: str, value: bool) -> None:
        pass


class SaveOp:
    """A tracked external COMP - one row of the TOX list"""

    def __init__(self, td_operator) -> None:
        """
        Args
        ---------
        td_operator (`COMP`)
        > A TouchDesigner operator this save_op is built from
        """
        self._ext_op = td_operator
        self._op_hash = None

    @property
    def id(self) -> int:
        """Live op id - it changes when the COMP is reloaded from disk"""
        return self._ext_op.id

    # NOT CALLED — hash-based dirty detection, unfinished
    def dirty_check(self) -> None:
        old_hash = self._op_hash
        new_hash = saveUtils.gen_hash_from_op(self._ext_op)
        if new_hash != old_hash:
            debug(f"{self._ext_op} is dirty")

    # NOT USED — part of unfinished hash system
    @property
    def op_hash(self):
        return self._op_hash

    @op_hash.setter
    def op_hash(self, new_hash) -> None:
        self._op_hash = new_hash

    @property
    def td_op(self):
        return self._ext_op

    @property
    def is_dirty(self) -> bool:
        return self._ext_op.dirty

    @property
    def last_saved(self):
        return self._ext_op.par['Lastsaved'] or None

    @property
    def version(self):
        return self._ext_op.par['Toxversion'] or None

    @property
    def ext_path(self):
        return self._ext_op.par.externaltox

    @property
    def tags(self) -> str:
        return ', '.join(sorted(self._ext_op.tags))
