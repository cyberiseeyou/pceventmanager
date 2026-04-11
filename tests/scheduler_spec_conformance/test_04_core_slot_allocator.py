"""Unit tests for the core_slot_allocator module.

Covers spec 04-core-supervisor.md branches C5, C9, C10, C11 at the
slot-allocator level — these are pure-logic tests with no DB state.
"""
from datetime import time

from app.services.core_slot_allocator import SLOT_ORDER, allocate_slot


def test_c5_primary_lead_always_1015_block_1():
    """Spec C5: Primary Lead's first CORE of the day gets 10:15 / block 1."""
    assert allocate_slot(existing={}, is_primary_lead=True) == (time(10, 15), 1)


def test_c5_primary_lead_none_when_1015_taken():
    """Spec C5: if 10:15 already has a CORE, Primary Lead cannot take it
    via this call — caller falls through to a different employee."""
    assert allocate_slot(
        existing={time(10, 15): 1}, is_primary_lead=True
    ) is None


def test_c9_fill_2_per_slot_before_advancing():
    """Spec C9: the first 8 CORE events fill 2 per slot in order:
    (10:15, blk1), (10:15, blk2), (10:45, blk3), (10:45, blk4),
    (11:15, blk5), (11:15, blk6), (11:45, blk7), (11:45, blk8)."""
    existing: dict[time, int] = {}
    expected = [
        (time(10, 15), 1),
        (time(10, 15), 2),
        (time(10, 45), 3),
        (time(10, 45), 4),
        (time(11, 15), 5),
        (time(11, 15), 6),
        (time(11, 45), 7),
        (time(11, 45), 8),
    ]
    for step in expected:
        got = allocate_slot(existing)
        assert got == step, (
            f"Step {step}: allocator returned {got}, expected {step}"
        )
        assert got is not None
        slot = got[0]
        existing[slot] = existing.get(slot, 0) + 1


def test_c9_overflow_plus_one_per_slot():
    """After 8 events (2 per slot), the 9th goes to 10:15 as block 9,
    10th to 10:45 as block 10, and so on — one per slot in order."""
    full = {s: 2 for s in SLOT_ORDER}
    assert allocate_slot(full) == (time(10, 15), 9)

    full_plus_one = {**full, time(10, 15): 3}
    assert allocate_slot(full_plus_one) == (time(10, 45), 10)

    full_plus_two = {**full, time(10, 15): 3, time(10, 45): 3}
    assert allocate_slot(full_plus_two) == (time(11, 15), 11)

    full_plus_three = {
        **full, time(10, 15): 3, time(10, 45): 3, time(11, 15): 3
    }
    assert allocate_slot(full_plus_three) == (time(11, 45), 12)


def test_c10_fill_gaps_first():
    """Spec C10: gaps (slots with fewer events than the theoretical
    fill order) are preferred over advancing the order."""
    # 10:45 has only 1 event while 11:15 has 2 — next CORE fills 10:45.
    existing = {time(10, 15): 2, time(10, 45): 1, time(11, 15): 2}
    got = allocate_slot(existing)
    # Block number is slot_idx * 2 + count + 1 = 1 * 2 + 1 + 1 = 4
    assert got == (time(10, 45), 4)


def test_c11_excludes_bumped_slot_from_count():
    """Spec C11: when computing slot occupancy for placement decisions,
    the caller pre-excludes slots that were freed by bumping in the
    current pass. The allocator sees the post-exclusion count of 0 and
    picks the earliest qualifying slot."""
    existing = {time(10, 15): 2, time(10, 45): 0, time(11, 15): 2}
    # 10:45 is tied for lowest (0) with 11:45 (0, missing = 0); earliest
    # in SLOT_ORDER wins → 10:45, and since count is 0, block is
    # 1*2 + 0 + 1 = 3 (the spot the bumped event used to occupy).
    got = allocate_slot(existing)
    assert got == (time(10, 45), 3)
