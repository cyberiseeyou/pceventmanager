"""CORE event time-slot allocator.

Implements spec 04-core-supervisor.md branches C9, C10, C11:

  * Four CORE slots per day: 10:15, 10:45, 11:15, 11:45.
  * Fill 2 per slot before advancing (10:15, 10:15, 10:45, 10:45,
    11:15, 11:15, 11:45, 11:45).
  * After 8 events, +1 per slot in order (10:15 gets the 9th,
    10:45 gets the 10th, 11:15 gets the 11th, 11:45 the 12th,
    10:15 the 13th, and so on).
  * Always fill gaps first: among slots with the lowest current
    count, pick the earliest (SLOT_ORDER-first).
  * Primary Lead always gets 10:15 / block 1 when no CORE yet exists
    on the day.

The module is deliberately pure — no DB, no Flask, no SQLAlchemy —
so the caller passes a dict of current slot counts. The caller is
responsible for pre-cleaning `existing` to reflect spec C11: when a
bump frees a slot earlier in this scheduling pass, exclude that
previously-occupied slot from the counts.
"""
from datetime import time
from typing import Mapping, Optional

# The four time slots in order. Index = slot_order (0..3).
SLOT_ORDER: tuple[time, ...] = (
    time(10, 15),
    time(10, 45),
    time(11, 15),
    time(11, 45),
)


def allocate_slot(
    existing: Mapping[time, int],
    is_primary_lead: bool = False,
) -> Optional[tuple[time, int]]:
    """Return `(slot_time, shift_block)` for the next CORE on a day.

    Args:
        existing: Mapping from slot_time (one of SLOT_ORDER) to the count
            of CORE events already scheduled in that slot on the target
            day. Missing keys are treated as 0. The caller must exclude
            slots that were freed by bumps in the current pass (C11).
        is_primary_lead: If True, allocate slot 10:15 / block 1 for a
            Primary Lead's first CORE of the day. Returns None if the
            Primary Lead cannot take 10:15 (slot already has ≥ 1 CORE),
            letting the caller fall through to a different employee
            selection strategy.

    Returns:
        Tuple of `(slot_time, shift_block)` where `shift_block` is the
        1-indexed block number the CORE will occupy. Returns None only
        when `is_primary_lead=True` and 10:15 is already taken — the
        non-primary-lead path always succeeds because there is no cap.

    The block numbering follows C9:
        blocks 1..8  → the first "2 per slot" pass
        blocks 9..12 → the second pass (1 per slot)
        blocks 13..  → additional +1 per slot rounds
    """
    if is_primary_lead:
        if existing.get(time(10, 15), 0) >= 1:
            return None
        return (time(10, 15), 1)

    counts = [existing.get(s, 0) for s in SLOT_ORDER]

    # C9: fill "2 per slot" in the first pass, then "+1 per slot" per
    # subsequent pass. Find the smallest target count such that some
    # slot still has fewer than `target` events, starting at 2 (the
    # first-pass cap). The earliest slot with count < target is the
    # one to fill. C10 ("fill gaps first") falls out naturally — a
    # slot with a gap has count strictly less than a later-filled
    # slot's count, so it's picked before any fresh slot at the
    # current target.
    target = 2
    while all(c >= target for c in counts):
        target += 1

    for i, c in enumerate(counts):
        if c < target:
            chosen_idx = i
            break
    else:  # pragma: no cover — loop always breaks by construction
        return None

    chosen_slot = SLOT_ORDER[chosen_idx]
    count_at_chosen = counts[chosen_idx]

    # Block numbering formula (C9):
    #   The first pass (counts 0, 1) produces blocks 1..8 interleaved
    #   across slots as (10:15→1, 10:15→2, 10:45→3, 10:45→4, ...).
    #   Subsequent passes (count 2, 3, ...) add +1 per slot in order:
    #   (count 2): 9, 10, 11, 12 for slots 10:15, 10:45, 11:15, 11:45.
    if count_at_chosen < 2:
        shift_block = chosen_idx * 2 + count_at_chosen + 1
    else:
        shift_block = 8 + (count_at_chosen - 2) * 4 + chosen_idx + 1

    return (chosen_slot, shift_block)
