# Scheduling Validation Rules

This document contains all validation rules for daily schedules. These rules are used to validate schedule correctness and can be integrated into an automated validation system.

---

## 1. Employee Assignment Rules

### RULE-001: One Primary Event Per Employee Per Day
**Applies to:** All employees EXCEPT Club Supervisor  
**Constraint:** Each employee may be scheduled for at most **one primary event per day**. Primary events are **Core** and **Juicer Production**. Secondary events (Digitals, Freeosk, Supervisor, Juicer Survey, Other) are unlimited per day but require the same employee to also hold a primary event on that day (see RULE-005).  
**Exception:** Club Supervisor is exempt from this rule.

### RULE-002: Primary Lead Daily Assignments
**Applies to:** Primary Lead Event Specialist  
**Constraint:** The Primary Lead should be assigned:
- Daily Freeosk event
- Digital Refresh event

**Exception (Digital Setup Days - Saturdays):**
- If there are Digital Setups, then a **different lead** (or Club Supervisor if no other leads available) should be scheduled the Digital Refresh, as these are scheduled at a later time.

### RULE-003: Primary Lead Block Assignment
**Applies to:** Primary Lead Event Specialist  
**Constraint:** The Primary Lead Event Specialist should always be scheduled for **Block 1**.

### RULE-004: Supervisor Event Priority
**Applies to:** Supervisor events  
**Constraint:** 
1. First priority: Club Supervisor (if available that day)
2. Second priority: Primary Lead Event Specialist (if Club Supervisor unavailable)

### RULE-005: Non-Supervisor Support Event Requirement
**Applies to:** All employees EXCEPT Club Supervisor  
**Constraint:** If anyone besides the Club Supervisor is scheduled a Freeosk, Digital, or Supervisor event, they **MUST** also be scheduled a Core or Juicer event.

### RULE-006: Juicer Production Exclusivity
**Applies to:** Employees scheduled for Juicer Production  
**Constraint:** An employee scheduled for Juicer Production on a given day may not also hold a Core on that same day (both are primary events — RULE-001 caps the total at one). When a Juicer Production needs the primary juicer's day and that juicer already has a Core posted, the Core must be bumped per RULE-022 rather than blocking the Juicer.

---

## 2. Event Pairing Rules

### RULE-007: Core-Supervisor Pairing (Required)
**Applies to:** Core and Supervisor events  
**Constraint:** All Core events **MUST** have their Supervisor counterpart scheduled on the same day.

### RULE-008: Supervisor Without Core (Prohibited)
**Applies to:** Supervisor events  
**Constraint:** There should **NOT** be any Supervisor events scheduled if their corresponding Core event is not scheduled.

### RULE-009: Juicer Production-Survey Pairing
**Applies to:** Juicer Production and Juicer Survey events  
**Constraint:** 
- Juicer Production events are scheduled at **9:00 AM**
- Corresponding Juicer Survey should be scheduled at **5:00 PM**

---

## 3. Event Timing Rules

### RULE-010: Freeosk Timing (Setup Days - Fridays)
**Applies to:** Freeosk events on Fridays (Freeosk Setup days)  
**Constraint:** 
- Freeosk Setup is scheduled at **10:00 AM**
- Freeosk Refresh (not setup) should be scheduled at **12:00 PM (Noon)**
- All other Freeosk events scheduled at **12:00 PM (Noon)**

### RULE-011: Freeosk Timing (Non-Setup Days)
**Applies to:** Freeosk events when there is NO Freeosk Setup  
**Constraint:**
- Freeosk Refresh is scheduled at **10:00 AM**
- All other Freeosk events scheduled at **12:00 PM (Noon)**

### RULE-012: Friday Digital Teardown Timing
**Applies to:** Digital Teardown events on Fridays  
**Constraint:** Digital Teardowns should be scheduled at:
- **5:00 PM**
- **5:15 PM**
- **5:30 PM**
- **5:45 PM**

**Assignment:** Assign to a Lead if they are working.

---

## 4. Scheduling Order Rules

### RULE-013: Standard Block Order (≤8 events)
**Applies to:** Days with 8 or fewer events  
**Constraint:** Scheduling order should be: **1, 2, 3, 4, 5, 6, 7, 8**

### RULE-014: Extended Block Order (>8 events)
**Applies to:** Days with more than 8 events  
**Constraint:** Scheduling order should be: **1, 3, 5, 7, 2, 4, 6, 8**

---

## 5. Conflict Prevention Rules

### RULE-015: Juicer Deep Clean Restriction
**Applies to:** Juicer Deep Clean events  
**Constraint:** Juicer Deep Clean events should **NOT** be scheduled on a day that has a Juicer Production event.

### RULE-016: Availability Compliance
**Applies to:** All employees  
**Constraint:** No employee should be scheduled outside their:
- Availability hours
- Requested days off

---

## 6. Fairness & Distribution Rules

### RULE-017: Schedule Randomization
**Applies to:** All employees  
**Constraint:** Employees should not consistently get the same scheduled time. Scheduling should be as **random as possible** for fairness.

### RULE-018: Weekly Core Event Limit
**Applies to:** Core events  
**Constraint:** Employees cannot have more than **6 Core events per week**.

### RULE-019: Weekly Juicer Production Limit
**Applies to:** Juicer Production events  
**Constraint:** Employees cannot have more than **5 Juicer Production events per week**.

### RULE-020: Duplicate Product Prevention
**Applies to:** All events  
**Constraint:** Events with the **same product** (e.g., Nurri, or any other brand/product) should **NOT** be scheduled on the same day.

### RULE-021: Due Date Priority
**Applies to:** All events  
**Constraint:** Events should be scheduled based on their **due date** (earliest due date first).  
**Exception:** This rule may be bypassed only to avoid violating RULE-020 (Duplicate Product Prevention).

### RULE-022: Juicer Production Outranks Core (Bump-the-Core)
**Applies to:** Juicer Production vs. Core primary-cap conflicts  
**Constraint:** Juicer Production has strictly higher priority than Core. When the primary rotation juicer already has a Core event posted on the day a Juicer Production needs to run, the **Core must be bumped** to another day inside its own scheduling window to make room for the Juicer Production. Core events are window-flexible — they may land on any day within their `start_datetime ≤ d < due_datetime` range.

### RULE-023: Backup Juicer Only on Approved PTO
**Applies to:** Juicer Production rotation fallback  
**Constraint:** The rotation backup juicer is used **only** when the primary rotation juicer has **approved time off** on the target day. A Core conflict on the primary juicer is NOT a reason to fall through to the backup — instead, bump the Core off that day per RULE-022. This preserves the intent of the rotation schedule (primary = default, backup = PTO coverage).

---

## Quick Reference: Day-Specific Rules

| Day | Special Events | Special Rules |
|-----|----------------|---------------|
| **Friday** | Freeosk Setup | Freeosk Refresh at Noon; Digital Teardowns at 5:00-5:45 PM |
| **Saturday** | Digital Setup | Different lead handles Digital Refresh |

---

## Quick Reference: Event Timing

| Event Type | Standard Time | Special Condition Time |
|------------|---------------|------------------------|
| Freeosk Refresh | 10:00 AM | 12:00 PM (if Freeosk Setup exists) |
| Freeosk Setup | 10:00 AM | - |
| Other Freeosk | 12:00 PM | - |
| Juicer Production | 9:00 AM | - |
| Juicer Survey | 5:00 PM | - |
| Digital Teardown (Fri) | 5:00, 5:15, 5:30, 5:45 PM | - |

---

*Document last updated: 2026-04-10*
*Total rules: 23*
