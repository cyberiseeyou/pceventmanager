"""Phase 2 — CORE/Supervisor pairing.

Per spec 00-master-overview.md branches M4-M6, CORE events are paired with
Supervisor events that share:
  1. The same 6-digit event number at the start of `project_name`, AND
  2. The same name prefix up to (but not including) the type keyword
     (CORE or Supervisor, case-insensitive).

Unpaired CORE events process alone (no Supervisor in the output).
Unpaired Supervisor events are logged as warnings and excluded from the
output — a Supervisor with no matching CORE is invalid input.

This module is pure (no DB, no Flask). Caller passes in any iterable of
Event-like objects that expose `event_type`, `project_name`,
`project_ref_num`, and `id` attributes.
"""
import logging
import re
from typing import Iterable, Mapping, Optional

logger = logging.getLogger(__name__)


# Matches `<6-digit><sep><prefix><sep>(CORE|Supervisor)` at the start of the
# project name. The prefix is captured lazily so the pairing key is the
# shortest string that still satisfies the trailing keyword.
_PAIRING_RE = re.compile(
    r'^\s*(?P<six_digit>\d{6})[-\s]+'
    r'(?P<prefix>.+?)\s*'
    r'(?P<separator>[-–\s]+)'
    r'(?P<kind>CORE|SUPERVISOR)',
    re.IGNORECASE,
)


def extract_pairing_key(project_name: str) -> Optional[tuple[str, str]]:
    """Return `(six_digit, normalized_prefix)` or None if the name is malformed.

    The normalized_prefix is the text between the 6-digit prefix and the
    CORE/Supervisor keyword, stripped of leading/trailing whitespace and
    lowercased for case-insensitive comparison.
    """
    if not project_name:
        return None
    m = _PAIRING_RE.match(project_name)
    if not m:
        return None
    return (m.group('six_digit'), m.group('prefix').strip().lower())


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
