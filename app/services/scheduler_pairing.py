"""Phase 2 — CORE/Supervisor pairing.

Per spec 00-master-overview.md branches M4-M6, CORE events are paired with
Supervisor events that represent the same product/event. In production data
the authoritative pairing key is the parenthesized unique event ID that
appears near the end of the project name (e.g. `(260209543468)`), which is
stable across CORE and Supervisor variants even when the rest of the name
differs (e.g. `- V2.1-CORE` vs `- V2-Supervisor`).

If a name has no parenthesized unique ID (legacy / test fixtures), the
pairer falls back to "6-digit number + name prefix up to the CORE/SUPERVISOR
keyword" — which is looser but works when both events use the same name
template.

Unpaired CORE events process alone (no Supervisor in the output).
Unpaired Supervisor events are logged as warnings and excluded from the
output — a Supervisor with no matching CORE in the current run's event
pool is still handled downstream by `_process_orphan_supervisors`, which
looks up the CORE's posted Schedule by pairing key.

This module is pure (no DB, no Flask). Caller passes in any iterable of
Event-like objects that expose `event_type`, `project_name`,
`project_ref_num`, and `id` attributes.
"""
import logging
import re
from typing import Iterable, Mapping, Optional

logger = logging.getLogger(__name__)


# Matches a parenthesized 9-12 digit unique event ID anywhere in the name
# (e.g. `(260209543468)`). This is the authoritative pairing key in real
# production data and is stable across CORE/Supervisor variants of the
# same product.
_PAREN_ID_RE = re.compile(r'\((\d{9,12})\)')

# Legacy fallback: `<6-digit><sep><prefix><sep>(CORE|Supervisor)` at the
# start of the project name. Used only when the name has no parenthesized
# unique ID (e.g. in some older test fixtures).
_PAIRING_RE = re.compile(
    r'^\s*(?P<six_digit>\d{6})[-\s]+'
    r'(?P<prefix>.+?)\s*'
    r'(?P<separator>[-–\s]+)'
    r'(?P<kind>CORE|SUPERVISOR)',
    re.IGNORECASE,
)

# Matches the leading 6-digit event number only. Used by plan 02 (Juicer
# Production ↔ Juicer Survey pairing) where the project_name does not end
# in CORE/SUPERVISOR and the 6-digit prefix alone is the matching key.
_SIX_DIGIT_RE = re.compile(r'^\s*(\d{6})\b')


def extract_six_digit_prefix(project_name: str) -> Optional[str]:
    """Return the 6-digit event number at the start of `project_name`, or None.

    Used to pair a Juicer Production with its matching Juicer Survey (spec
    02-juicer-production.md branches JP15/JP16). Unlike `extract_pairing_key`,
    this does NOT require a trailing CORE/Supervisor keyword — the 6-digit
    prefix is sufficient identification for production/survey pairing.
    """
    if not project_name:
        return None
    m = _SIX_DIGIT_RE.match(project_name)
    if not m:
        return None
    return m.group(1)


def extract_pairing_key(project_name: str):
    """Return a key tuple that uniquely identifies a CORE/Supervisor pair.

    Preference order:
      1. `('paren', <unique_id>)` — the parenthesized 9-12 digit event ID
         (e.g. `('paren', '260209543468')`). Stable across CORE and
         Supervisor variants of the same product regardless of version
         suffixes — this is the authoritative key in real data.
      2. `('prefix', <six_digit>, <lowercased_prefix>)` — legacy fallback
         for names without a parenthesized ID.

    Returns None if the name is too malformed to extract any key.

    The return value is a tuple (rather than a string) so paren-keyed and
    prefix-keyed events never collide with each other — an event that
    matches one scheme will not accidentally pair with an event that
    matches the other.
    """
    if not project_name:
        return None
    paren_match = _PAREN_ID_RE.search(project_name)
    if paren_match:
        return ('paren', paren_match.group(1))
    m = _PAIRING_RE.match(project_name)
    if m:
        return ('prefix', m.group('six_digit'),
                m.group('prefix').strip().lower())
    return None


def pair_cores_and_supervisors(events: Iterable) -> Mapping[int, object]:
    """Compute the CORE→Supervisor pairing for a set of events.

    Returns a mapping from CORE event `id` to the Supervisor event object.
    Unpaired CORE events are omitted (the caller processes them alone).
    Unpaired Supervisor events are logged as warnings and omitted.

    Args:
        events: iterable of Event-like objects. Only events with
            `event_type in ('Core', 'Supervisor')` are considered; other
            types are ignored.

    Returns:
        dict mapping `core.id → supervisor_event`. The dict is empty if no
        pairings exist.
    """
    cores = [e for e in events if getattr(e, 'event_type', None) == 'Core']
    supervisors = [e for e in events
                   if getattr(e, 'event_type', None) == 'Supervisor']

    sup_by_key: dict[tuple[str, str], object] = {}
    for sup in supervisors:
        key = extract_pairing_key(sup.project_name)
        if key is None:
            logger.warning(
                "Supervisor event %s has malformed name %r; cannot pair",
                sup.project_ref_num, sup.project_name,
            )
            continue
        # If two supervisors share the same key (shouldn't happen in
        # practice), the last one wins; log a warning so we can notice.
        if key in sup_by_key:
            logger.warning(
                "Duplicate Supervisor pairing key %r: events %s and %s; "
                "keeping the latter",
                key, sup_by_key[key].project_ref_num, sup.project_ref_num,
            )
        sup_by_key[key] = sup

    pairs: dict[int, object] = {}
    matched_sup_ids: set = set()

    for core in cores:
        key = extract_pairing_key(core.project_name)
        if key is None:
            logger.warning(
                "Core event %s has malformed name %r; cannot pair",
                core.project_ref_num, core.project_name,
            )
            continue
        sup = sup_by_key.get(key)
        if sup is not None:
            pairs[core.id] = sup
            matched_sup_ids.add(sup.id)

    for sup in supervisors:
        if sup.id not in matched_sup_ids:
            logger.warning(
                "Unpaired Supervisor event %s (%r); no matching CORE found",
                sup.project_ref_num, sup.project_name,
            )

    return pairs
