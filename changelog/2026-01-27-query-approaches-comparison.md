# Query Approach Comparison

## Current Implementation (Multi-Endpoint)

### Endpoint 1: Planning Events (condition-based)
```
GET /planningextcontroller/getPlanningMplans
```
**Filter:** `condition` with values:
- ["Staffed", "Scheduled", "Canceled", "Unstaffed", "In Progress", "Paused", "Expired", "Reissued", "Submitted"]

**Method:** Chunked (3-day chunks, ~25 requests)
**Result:** 1,513 events

### Endpoint 2: Scheduled Events
```
POST /schedulingcontroller/getScheduledEvents
```
**Method:** Single request with date range
**Result:** 500 events

### Endpoint 3: Non-Scheduled Visits
```
POST /schedulingcontroller/getNonScheduledVisits
```
**Method:** Single request
**Result:** Included in the 500 above

**Total:** 2,013 events → 1,158 unique (855 duplicates)

---

## Proposed Alternative (Single Endpoint)

### Role-Based Query
```
GET /planningextcontroller/getPlanningMplans
```
**Filter:** `role` with value:
- ["DIV:US-SHPE-860"]

**Method:** Single request (no chunking needed)
**Date Range:** Full 6-month range in one call
**Limit:** 5000 events per call

---

## Key Questions to Test

1. **Does role-based filter return ALL event statuses?**
   - Staffed ✓
   - Scheduled ✓
   - Canceled ✓
   - Unstaffed ✓
   - In Progress ✓
   - Etc.

2. **Does it match or exceed the 1,158 unique events?**

3. **Does it eliminate the need for scheduling endpoints?**

---

## Benefits of Role-Based (if successful)

### Performance
- **60 seconds → ~5-10 seconds** (one API call vs 27 calls)
- No chunking overhead
- No deduplication processing

### Code Simplicity
- One endpoint instead of three
- No need to merge results
- Simpler error handling

### Maintainability
- Single point of failure/monitoring
- Easier debugging
- Less complex logic

---

## Risks

### If role-based misses events:
- May not return all statuses
- May have different filtering logic
- Could require additional fallback calls

### Testing Needed:
1. Run both approaches side-by-side
2. Compare event IDs
3. Verify all statuses are present
4. Check edge cases (canceled events, expired, etc.)

---

## Recommendation

**Test in production-like environment:**

```python
# Test script structure
role_based_events = fetch_with_role_filter("DIV:US-SHPE-860")
current_method_events = fetch_with_condition_and_scheduling()

# Compare
role_ids = set(e['mPlanID'] for e in role_based_events)
current_ids = set(e['mPlanID'] for e in current_method_events)

missing_in_role = current_ids - role_ids
extra_in_role = role_ids - current_ids

if len(missing_in_role) == 0:
    print("✓ Role-based returns all events!")
    print("  Recommend switching to single endpoint")
else:
    print(f"✗ Role-based missing {len(missing_in_role)} events")
    print("  Keep current multi-endpoint approach")
```

---

## Next Steps

1. **Get division/role ID** for your account
2. **Run comparison test** with real data
3. **Verify all event types** are returned
4. **Measure performance improvement**
5. **Implement if successful** with fallback to current method
