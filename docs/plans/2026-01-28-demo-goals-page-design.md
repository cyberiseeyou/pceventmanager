# Demo Goals Page Design

**Date:** 2026-01-28
**Type:** Feature Addition

## Summary

Add a new page to display upcoming demo goals filtered by the user's club number. Data is fetched from a WordPress table API, filtered by club number from SystemSetting, sorted oldest to newest, and displayed with print functionality.

## Requirements

- Display demo goals filtered by club number (from SystemSetting)
- Sort by demo scheduled date (oldest first)
- Show only: Demo Date, Demo ID, Item Number, Item Description
- Provide print button with clean print formatting
- Handle errors gracefully (missing config, API failures, empty results)

## Data Source

**WordPress API Endpoint:**
```
GET https://productconnections.com/wp-admin/admin-ajax.php
  ?action=wp_ajax_ninja_tables_public_action
  &table_id=5811
  &target_action=get-all-data
  &default_sorting=manual_sort
  &skip_rows=0
  &limit_rows=0
  &ninja_table_public_nonce=2c18cac120
  &chunk_number=0
```

**Response Structure:**
```json
[
  {
    "value": {
      "clubnumber": "4109",
      "demoscheduleddate": "1/30/2026",
      "demoid": "619157",
      "itemnumber": "203373-Sumo Citrus Mandarin",
      "itemdescription": "42",
      "city": " Bossier City",
      "state": " LA",
      "club_supervisor": "Jacob Cradduck",
      ...
    }
  }
]
```

**Fields to Use:**
- `value.clubnumber` - Filter criterion
- `value.demoscheduleddate` - Display and sort
- `value.demoid` - Display
- `value.itemnumber` - Display
- `value.itemdescription` - Display

**Fields to Exclude:** city, state, club_supervisor, market_manager, regional_director

## Architecture

### Backend Components

**1. New Blueprint:** `app/routes/demo_goals.py`
- Route: `GET /demo-goals/` - Renders page template
- Route: `GET /demo-goals/api/data` - Returns filtered/sorted JSON data
- Authentication: Required (`@require_authentication()`)

**2. Data Flow:**
1. Read `club_number` from SystemSetting
2. Fetch WordPress API data
3. Filter where `value.clubnumber` matches setting
4. Parse and sort by `demoscheduleddate` (oldest first)
5. Return only needed fields

### Frontend Components

**1. Template:** `app/templates/demo_goals.html`
- Extends `base.html`
- Loading state (spinner)
- Error state (alert)
- Empty state (no demos message)
- Data table (4 columns)
- Print button

**2. JavaScript:**
- Fetch data from `/demo-goals/api/data` on page load
- Populate table dynamically
- Handle states (loading/error/empty/data)
- Print button triggers `window.print()`

**3. CSS:**
- Optional page styles: `app/static/css/pages/demo-goals.css`
- Inline print styles via `@media print`
- Hide navigation/buttons in print
- Clean table formatting for printing

## Implementation Details

### File Structure

**New Files:**
```
app/routes/demo_goals.py          # Blueprint with routes
app/templates/demo_goals.html     # Page template
app/static/css/pages/demo-goals.css  # Optional styles (can be inline)
```

**Modified Files:**
```
app/__init__.py                    # Register blueprint
app/templates/base.html OR printing.html  # Add navigation link
Database: system_settings table    # Add club_number setting
```

### Backend Route Implementation

**Page Route:**
```python
@demo_goals_bp.route('/')
@require_authentication()
def demo_goals_page():
    return render_template('demo_goals.html')
```

**API Data Route:**
```python
@demo_goals_bp.route('/api/data', methods=['GET'])
@require_authentication()
def get_demo_goals_data():
    # 1. Get club_number from SystemSetting
    # 2. Fetch WordPress API
    # 3. Filter by clubnumber
    # 4. Parse dates (M/D/YYYY format)
    # 5. Sort by date (oldest first)
    # 6. Return JSON
```

### Error Handling

**Configuration Errors:**
- Missing `club_number` in SystemSetting → 400 error with message
- Invalid club_number format → Use as-is (string comparison)

**API Errors:**
- Timeout (10s) → 504 error, "Request timed out"
- Connection error → 503 error, "Could not connect to service"
- Non-200 status → 500 error, "API returned status X"
- Invalid JSON → 500 error, "Invalid response"

**Data Quality:**
- Empty result set → Show "No upcoming demos for club X"
- Missing/invalid date → Skip row or show at end (max sort value)
- Missing fields → Show "N/A"

### Date Parsing

**Format:** `M/D/YYYY` or `MM/DD/YYYY`

**Strategy:**
```python
try:
    parsed_date = datetime.strptime(date_str, '%m/%d/%Y')
except:
    try:
        parsed_date = datetime.strptime(date_str, '%n/%j/%Y')
    except:
        parsed_date = datetime.max  # Sort unparseable to end
```

### Print Functionality

**Print Styles:**
```css
@media print {
    .no-print { display: none !important; }
    .print-only { display: block !important; }
    /* Clean table borders, avoid row breaks */
}
```

**Print Header (visible only when printing):**
- Club number
- Generation timestamp
- Horizontal rule separator

## Configuration

**SystemSetting Entry:**
```python
key: 'club_number'
value: '8135'  # Example
description: 'Club number for filtering demo goals'
is_encrypted: False
```

**Setup Options:**

1. **Via Settings Page:** Add field to existing settings form
2. **Via Database:** Direct SQL insert
3. **Via Python Shell:** Use `SystemSetting.set_setting()`

## Testing Strategy

**Unit Tests:**
- Test date parsing (valid/invalid formats)
- Test club number filtering logic
- Test sorting (oldest first)

**Integration Tests:**
- Test API route with mocked WordPress response
- Test error scenarios (missing config, API down)
- Test empty results

**Manual Tests:**
- [ ] Page loads correctly
- [ ] Data filters to correct club
- [ ] Sorting is correct (oldest first)
- [ ] Print button works
- [ ] Print preview is clean
- [ ] Error states display properly
- [ ] Empty state displays properly
- [ ] Mobile/tablet responsive

## Navigation

**Option A - Main Navigation:**
Add link in main nav menu (if appropriate for all users)

**Option B - Printing Page:**
Add card on printing page (if this is printing-related workflow)

Recommended: **Option B** - Add to printing page since this is print-oriented

## Security Considerations

- Authentication required on all routes
- WordPress API is read-only (GET request)
- No sensitive data stored (club number is not sensitive)
- HTML escaping on frontend to prevent XSS
- No user input validation needed (no forms)

## Performance Considerations

- WordPress API response size: ~100-500 rows expected
- Client-side filtering (happens once per page load)
- No database queries (only SystemSetting lookup)
- Optional: Add 5-10 minute cache for WordPress API response

## Future Enhancements (Out of Scope)

- Date range filter (e.g., next 30 days only)
- Export to CSV/Excel
- Email scheduled report
- Multi-club view for managers
- Caching WordPress API response
- Auto-refresh data every X minutes

## Success Criteria

- [ ] Page displays demo goals for configured club number
- [ ] Data is sorted oldest to newest
- [ ] Print button produces clean printable output
- [ ] Error messages are user-friendly
- [ ] No crashes on missing data or API failures
- [ ] Page loads in < 3 seconds
- [ ] Mobile-responsive layout

## Rollback Plan

If issues occur:
1. Remove blueprint registration from `app/__init__.py`
2. Remove navigation link
3. Delete new files (blueprint, template, CSS)
4. Restart application

No database changes to rollback (SystemSetting entry is harmless).
