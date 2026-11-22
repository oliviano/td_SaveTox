"""
TOX manifest - format and comparison logic for sharing "which TOX version
does each host have" through git.

Pure python on purpose (no TouchDesigner globals), so it can be tested
outside of TD. The TD side lives in saveTox.ExternalFiles.

Format: one file per host, `<manifest folder>/<host>.jsonl`
    line 1   {"schema":1,"host":"kuro-mbp","os":"macOS"}
    line 2+  one TOX per line, sorted by key, fixed field order
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone

SCHEMA = 1
FILE_EXT = '.jsonl'
VERSION_SUFFIX = re.compile(r'_v\d+-\d+-\d+(?=\.tox$)')
ENTRY_FIELDS = ('key', 'op', 'file', 'version', 'saved', 'td',
                'sha', 'base', 'size', 'wip', 'wip_since')
TIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

# claims ("I'm working on this") older than this are shown as stale
STALE_DAYS = 7
CLAIM_MAX_LENGTH = 60

# claim states of one TOX
CLAIM_MINE = 'mine'
CLAIM_THEIRS = 'theirs'
CLAIM_BOTH = 'both'
CLAIM_STALE = 'stale'

# comparison states
IN_SYNC = 'in sync'
REMOTE_NEWER = 'update ready'
REMOTE_NEWER_MISSING = 'newer, no file'
REMOTE_NEWER_MISMATCH = 'newer, file differs'
LOCAL_NEWER = 'ahead'
DIVERGED = 'diverged'
LOCAL_ONLY = 'local only'
REMOTE_ONLY = 'remote only'
UNKNOWN = 'unknown'

_sha_cache = {}


def host_id(name: str) -> str:
    """Machine name reduced to a safe file name: 'Kuro-MBP.local' ->
    'kuro-mbp'"""
    name = name.strip().lower()
    name = re.sub(r'\.(local|lan|home)$', '', name)
    return re.sub(r'[^a-z0-9]+', '-', name).strip('-') or 'host'


def posix(path: str) -> str:
    return path.replace('\\', '/')


def tox_key(rel_path: str) -> str:
    """Join key of a TOX: its project-relative path without the version
    suffix and extension. 'tox/a/a_v1-2-3.tox' -> 'tox/a/a'"""
    path = VERSION_SUFFIX.sub('', posix(rel_path))
    return path[:-4] if path.lower().endswith('.tox') else path


def version_tuple(version: str) -> tuple:
    try:
        return tuple(int(x) for x in str(version).split('.'))
    except ValueError:
        return ()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def time_stamp(moment: datetime = None) -> str:
    """UTC time as written in the manifest: '2026-11-22T03:01:00Z'"""
    return (moment or utc_now()).strftime(TIME_FORMAT)


def parse_time(stamp: str):
    """datetime of a manifest time stamp, None when it does not parse"""
    try:
        return datetime.strptime(str(stamp), TIME_FORMAT).replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None


def age_text(stamp: str, now: datetime = None) -> str:
    """Short age of a time stamp: 'now', '25m', '3h', '2d'. '' when the
    stamp does not parse."""
    then = parse_time(stamp)
    if then is None:
        return ''
    minutes = int(((now or utc_now()) - then).total_seconds() // 60)
    if minutes < 1:
        return 'now'
    if minutes < 60:
        return f'{minutes}m'
    if minutes < 60 * 24:
        return f'{minutes // 60}h'
    return f'{minutes // (60 * 24)}d'


def is_stale(stamp: str, now: datetime = None, days: int = STALE_DAYS) -> bool:
    """True when a claim is older than `days`. A claim without a readable
    time is not treated as stale."""
    then = parse_time(stamp)
    if then is None:
        return False
    return ((now or utc_now()) - then).total_seconds() > days * 86400


def clean_claim(note: str) -> str:
    """A claim note reduced to one short line"""
    return ' '.join(str(note or '').split())[:CLAIM_MAX_LENGTH]


def claim_summary(my_note: str, remote_claims: list,
                  now: datetime = None) -> tuple:
    """(text, state) of the claims on one TOX.

    remote_claims is a list of (host, note, since). Example:
    ('me: rig  |  kenji: relighting (2d)', 'both')
    """
    parts = []
    if my_note:
        parts.append(f'me: {my_note}')

    fresh = False
    for host, note, since in sorted(remote_claims):
        if not note:
            continue
        age = age_text(since, now)
        if is_stale(since, now):
            parts.append(f'{host}: {note} ({age}, stale)')
        else:
            fresh = True
            parts.append(f'{host}: {note} ({age})' if age
                         else f'{host}: {note}')

    if my_note and fresh:
        state = CLAIM_BOTH
    elif my_note:
        state = CLAIM_MINE
    elif fresh:
        state = CLAIM_THEIRS
    elif parts:
        state = CLAIM_STALE
    else:
        state = ''
    return ('  |  '.join(parts), state)


def file_sha(abs_path: str) -> tuple:
    """(first 12 hex chars of the SHA-256, size in bytes) of a file, or
    ('', 0) when it does not exist. Cached by path + mtime + size."""
    try:
        stat = os.stat(abs_path)
    except OSError:
        return ('', 0)

    cache_key = (abs_path, stat.st_mtime_ns, stat.st_size)
    if cache_key not in _sha_cache:
        digest = hashlib.sha256()
        with open(abs_path, 'rb') as tox_file:
            for chunk in iter(lambda: tox_file.read(1 << 20), b''):
                digest.update(chunk)
        _sha_cache[cache_key] = digest.hexdigest()[:12]

    return (_sha_cache[cache_key], stat.st_size)


def dump(header: dict, entries: list) -> str:
    """Manifest text. Deterministic: the same state always gives the same
    bytes, so git only shows real changes."""
    def line(data: dict) -> str:
        return json.dumps(data, separators=(',', ':'), ensure_ascii=False)

    lines = [line(header)]
    for entry in sorted(entries, key=lambda each: each['key'].lower()):
        lines.append(line({field: entry.get(field, '')
                           for field in ENTRY_FIELDS}))
    return '\n'.join(lines) + '\n'


def load(text: str) -> tuple:
    """(header, {lower-cased key: entry}) from manifest text. Lines that do
    not parse (bad merge, hand edit) are skipped."""
    header, entries = {}, {}
    for raw_line in text.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            data = json.loads(raw_line)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        if 'key' in data:
            entries[str(data['key']).lower()] = data
        elif 'schema' in data:
            header = data
    return header, entries


def read_file(path: str) -> tuple:
    """load() of a manifest file; ({}, {}) when it cannot be read"""
    try:
        with open(path, 'r', encoding='utf-8-sig') as manifest_file:
            return load(manifest_file.read())
    except OSError:
        return {}, {}


def write_file(path: str, text: str) -> bool:
    """Writes manifest text unless the file already holds exactly that.
    Returns True when the file was written."""
    try:
        with open(path, 'r', encoding='utf-8', newline='') as manifest_file:
            if manifest_file.read() == text:
                return False
    except OSError:
        pass

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as manifest_file:
        manifest_file.write(text)
    return True


def best_remote(candidates: list):
    """Of several hosts' entries for one TOX, the one with the highest
    version (latest save time on a tie). Each candidate is (host, entry)."""
    if not candidates:
        return None
    return max(candidates, key=lambda each: (
        version_tuple(each[1].get('version', '')),
        str(each[1].get('saved', ''))))


def compare(local_version: str, local_sha: str, remote: dict,
            remote_file_sha: str) -> str:
    """State of my TOX against another host's manifest entry.

    remote_file_sha is the hash of the remote entry's file as found on MY
    disk ('' when that file is not here).
    """
    if remote is None:
        return LOCAL_ONLY

    mine = version_tuple(local_version)
    theirs = version_tuple(remote.get('version', ''))
    if not mine or not theirs:
        return UNKNOWN

    if theirs > mine:
        if not remote_file_sha:
            return REMOTE_NEWER_MISSING
        if remote_file_sha != remote.get('sha', ''):
            return REMOTE_NEWER_MISMATCH
        return REMOTE_NEWER

    if mine > theirs:
        return LOCAL_NEWER

    return IN_SYNC if local_sha == remote.get('sha', '') else DIVERGED
