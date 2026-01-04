# Scheduling Validation Rules

This document contains all validation rules for daily schedules. These rules are used to validate schedule correctness and can be integrated into an automated validation system.

---

## 1. Employee Assignment Rules

### RULE-001: Single Core/Juicer Production Limit
**Applies to:** All employees EXCEPT Club Supervisor  
**Constraint:** Each employee should only be scheduled to **ONE** Core event OR **ONE** Juicer Production event per day.  
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
**Constraint:** If an employee is scheduled for Juicer Production, they should **NOT** be scheduled for a Core event on the same day.

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

*Document last updated: 2026-01-01*
*Total rules: 19*
