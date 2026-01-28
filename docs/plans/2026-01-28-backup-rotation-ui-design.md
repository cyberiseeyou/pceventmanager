# Backup Rotation UI Design

**Date:** 2026-01-28
**Type:** UI Enhancement

## Summary

Add UI support for configuring backup employees in rotation assignments. Update the existing rotation management page to show backup dropdowns below primary employees, and add a "Rotation Management" link to the Settings dropdown menu.

---

## UI Component Updates

### Rotation Page Enhancements

**Visual Layout:**

The existing rotation page will be enhanced with a stacked layout showing backup employee dropdowns directly below each primary employee dropdown.

```
Primary Juicer Rotation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Each day shows:

  Monday
  Primary: [John Smith ▼]
  Backup:  [Jane Doe ▼]  (optional - can be blank)

  Tuesday
  Primary: [Mike Johnson ▼]
  Backup:  [-- Select Backup (Optional) --▼]
```

**Key Features:**
- Backup dropdown appears below primary for each day
- Backup is optional (can remain blank)
- Same employee pool as primary (Juicers for Juicer rotation, Leads for Lead rotation)
- Visual distinction: Primary label in bold, Backup label in regular weight
- Help text: "Backup employees are automatically used when the primary is unavailable"

**Data Structure (sent to API):**
```javascript
{
  juicer: {
    0: { primary: "emp1", backup: "emp2" },  // Monday
    1: { primary: "emp3", backup: null }      // Tuesday (no backup)
  },
  primary_lead: {
    0: { primary: "emp4", backup: "emp5" }
  }
}
```

---

## Settings Dropdown Menu Update

### Navigation Changes

Add "Rotation Management" link to the existing Settings dropdown in the header navigation.

**Updated Dropdown Structure:**
```
Admin/Settings Dropdown:
├─ Help
├─ Settings
├─ Event Time Settings
├─ Rotation Management  ← NEW
├─ ──────────── (divider)
└─ Logout
```

**Link Details:**
- **Icon:** 🔄 (rotation symbol)
- **Text:** "Rotation Management"
- **Route:** `{{ url_for('rotations.index') }}`
- **Active state:** Highlights when on rotations page
- **Position:** After "Event Time Settings", before the divider

**Visual Consistency:**
- Uses same dropdown-item styling as other menu items
- Same icon + text pattern
- Same hover/active states

**Mobile Behavior:**
- Works in collapsed hamburger menu
- Same touch-friendly spacing as other items

---

## Visual Styling & User Experience

### CSS Enhancements

**1. Backup Dropdown Styling:**
```css
.rotation-day {
  display: flex;
  flex-direction: column;
  gap: 12px;  /* Space between primary and backup */
}

.primary-select-group {
  /* Primary dropdown group */
}

.backup-select-group {
  padding-left: 15px;  /* Slight indent to show hierarchy */
  border-left: 3px solid #3498db;  /* Visual indicator */
}

.backup-select-group label {
  font-weight: 400;  /* Normal weight vs bold for primary */
  color: #7f8c8d;    /* Slightly muted */
  font-size: 13px;
}

.backup-badge {
  display: inline-block;
  background: #3498db;
  color: white;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  margin-left: 5px;
}
```

**2. Visual Hierarchy:**
- **Primary label:** Bold, darker color (#34495e)
- **Backup label:** Regular weight, muted color (#7f8c8d) with "Optional" badge
- **Left border:** 3px blue border on backup section to show it's secondary
- **Indent:** 15px left padding for backup dropdown

**3. Empty State:**
- Backup dropdown shows "-- Select Backup (Optional) --" as default
- No visual error when backup is empty (it's optional)
- Placeholder text clearly indicates optional nature

**4. Validation Feedback:**

**If same employee selected for primary and backup:**
- Red border on backup dropdown (`border-color: #e74c3c`)
- Small error message below: "⚠️ Backup must be different from primary"
- Error styling: red text, 12px font size
- Error clears immediately when selection changes

**5. Success Indicators:**
- When backup is configured: Small checkmark ✓ next to backup label (green color)
- On save: "Rotations saved successfully! Backup employees configured for X days"
- Success message includes count of days with backups configured

---

## Implementation Details

### Frontend Logic

**1. Data Collection on Save:**
```javascript
// Collect rotations with backup support
document.getElementById('save-rotations').addEventListener('click', async function() {
    const rotations = {
        juicer: {},
        primary_lead: {}
    };

    document.querySelectorAll('.rotation-day').forEach(day => {
        const type = day.dataset.rotationType;
        const dayIndex = day.dataset.day;
        const primary = day.querySelector('.primary-select').value;
        const backup = day.querySelector('.backup-select').value;

        if (primary) {
            rotations[type][dayIndex] = {
                primary: primary,
                backup: backup || null  // null if empty
            };
        }
    });

    // Send to server...
});
```

**2. Client-Side Validation:**

```javascript
function validateRotations() {
    let isValid = true;
    const errors = [];

    document.querySelectorAll('.rotation-day').forEach(day => {
        const primary = day.querySelector('.primary-select').value;
        const backup = day.querySelector('.backup-select').value;
        const backupSelect = day.querySelector('.backup-select');
        const errorMsg = day.querySelector('.backup-error');

        // Clear previous errors
        backupSelect.classList.remove('error');
        if (errorMsg) errorMsg.remove();

        // Validate: backup must differ from primary
        if (backup && backup === primary) {
            isValid = false;
            backupSelect.classList.add('error');

            const error = document.createElement('div');
            error.className = 'backup-error';
            error.innerHTML = '⚠️ Backup must be different from primary';
            backupSelect.parentElement.appendChild(error);
        }
    });

    return isValid;
}
```

**3. Real-time Validation:**
- Attach change event listeners to all backup dropdowns
- Validate on change, clear errors immediately when fixed
- Disable save button if validation fails

**4. Server Response Handling:**
- **Success:** Show success message with backup count
- **Error:** Display specific validation errors from server
- **Backward compatibility:** Old API format (string) still works

### Backend Integration

**1. Route Handler (already implemented in Phase 6):**
- `app/routes/rotations.py` accepts both formats:
  - Old: `{ "juicer": { "0": "emp1" } }`
  - New: `{ "juicer": { "0": { "primary": "emp1", "backup": "emp2" } } }`
- Returns backup employees in GET responses

**2. Error Scenarios:**
- Backup same as primary: "Backup employee must be different from primary for {day}"
- Invalid employee ID: "Employee {id} not found"
- Missing primary but has backup: "Primary employee required when backup is specified"

---

## Template Changes

### File: `app/templates/rotations.html`

**Changes:**

1. **Update rotation-day structure** (for each day):
```html
<div class="rotation-day" data-rotation-type="juicer" data-day="{{ day_index }}">
    <!-- Primary Select -->
    <div class="primary-select-group">
        <label for="juicer-primary-{{ day_index }}">
            <strong>{{ day_names[day_index] }}</strong>
        </label>
        <select id="juicer-primary-{{ day_index }}"
                class="primary-select"
                name="juicer-primary-{{ day_index }}">
            <option value="">-- Select Primary --</option>
            {% for employee in juicers %}
            <option value="{{ employee.id }}"
                {% if rotations.juicer.get(day_index) and rotations.juicer[day_index].primary == employee.id %}selected{% endif %}>
                {{ employee.name }}
            </option>
            {% endfor %}
        </select>
    </div>

    <!-- Backup Select -->
    <div class="backup-select-group">
        <label for="juicer-backup-{{ day_index }}">
            Backup <span class="backup-badge">Optional</span>
        </label>
        <select id="juicer-backup-{{ day_index }}"
                class="backup-select"
                name="juicer-backup-{{ day_index }}">
            <option value="">-- Select Backup (Optional) --</option>
            {% for employee in juicers %}
            <option value="{{ employee.id }}"
                {% if rotations.juicer.get(day_index) and rotations.juicer[day_index].backup == employee.id %}selected{% endif %}>
                {{ employee.name }}
            </option>
            {% endfor %}
        </select>
    </div>
</div>
```

2. **Update help text:**
```html
<p class="help-text">
    Assign a Juicer Barista for each day of the week.
    Optionally configure backup employees who will be automatically used when the primary is unavailable.
</p>
```

3. **Update JavaScript** to handle new data structure (see Frontend Logic above)

### File: `app/templates/base.html`

**Changes:**

Add rotation management link to settings dropdown (around line 195):

```html
<a href="{{ url_for('admin.event_times_page') }}" class="dropdown-item">
    <span class="dropdown-icon">🕐</span>
    Event Time Settings
</a>
<!-- NEW LINK -->
<a href="{{ url_for('rotations.index') }}"
   class="dropdown-item {% if request.endpoint and request.endpoint.startswith('rotations.') %}active{% endif %}">
    <span class="dropdown-icon">🔄</span>
    Rotation Management
</a>
<div class="dropdown-divider"></div>
```

---

## Testing Checklist

**Manual Testing:**
- [ ] Open rotation management page
- [ ] Configure primary employees for all days
- [ ] Add backup employees for some days
- [ ] Leave some backup dropdowns empty (optional nature)
- [ ] Try selecting same employee for primary and backup (should show error)
- [ ] Save rotations successfully
- [ ] Reload page - verify primary and backup values persist
- [ ] Test on mobile viewport
- [ ] Verify settings dropdown link works
- [ ] Verify active state highlighting

**Edge Cases:**
- [ ] No backups configured (backward compatibility)
- [ ] Partial backups (some days have backups, some don't)
- [ ] Change primary after selecting backup
- [ ] Remove backup selection
- [ ] Invalid employee IDs in response

**Browser Testing:**
- [ ] Chrome/Edge
- [ ] Firefox
- [ ] Safari
- [ ] Mobile browsers

---

## Success Metrics

**User Experience:**
- Clear visual distinction between primary and backup
- Obvious that backup is optional
- Immediate validation feedback prevents errors
- Mobile-friendly layout

**Functionality:**
- Backward compatible with existing rotations
- Supports partial backup configuration
- Proper error handling and validation
- Successful save/load of backup employees

**Accessibility:**
- Clear labels for screen readers
- Keyboard navigation works
- Error messages are announced
- Sufficient color contrast

---

## Future Enhancements (Out of Scope)

- Drag-and-drop employee assignment
- Copy rotation from previous week
- Bulk operations (set all backups to same employee)
- Visual indicators showing when backup was actually used in scheduling
- Email notifications to backup employees when they're assigned
