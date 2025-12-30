---
description: Have Claude Code what is planned
---

AI Agent Rules: Delegating Implementation to Claude Code
# Implementation Delegation Rules

When a plan has been finalized and is ready for implementation, delegate the coding work to Claude Code using the CLI.

## When to Delegate

- A detailed implementation plan exists with clear steps
- The plan has been approved by the user
- The task involves writing, modifying, or refactoring code

## Command Format

```bash
claude -p "<prompt>"
Prompt Construction Rules
1. Include the Full Plan
Pass the complete implementation plan, not a summary. Include:
All files to be created or modified
Specific code changes required
Dependencies and imports needed
Test requirements
2. Provide File Context
Reference exact file paths from the codebase:
claude -p "Implement the following plan:

Files to modify:
- app/services/scheduler.py
- app/models/event.py
- tests/test_scheduler.py

Plan:
[full plan details here]"
3. Include Constraints
Specify any architectural or style constraints:
Existing patterns to follow
Naming conventions
Error handling requirements
Testing expectations
4. One Task Per Invocation
For complex plans, break into sequential invocations:
# Step 1: Create the model
claude -p "Create the Employee model in app/models/employee.py with fields: [...]"

# Step 2: Add the service
claude -p "Create EmployeeService in app/services/employee.py that uses the Employee model [...]"

# Step 3: Add routes
claude -p "Add CRUD routes for Employee in app/routes/employees.py [...]"
Prompt Template
claude -p "Implement the following:

## Context
[Brief description of the feature/fix]

## Files
- [file paths to create/modify]

## Implementation Plan
[Numbered steps with specific details]

## Constraints
- Follow existing patterns in [reference file]
- Add tests in [test file path]
- [Other constraints]

## Acceptance Criteria
- [What success looks like]"
Example
claude -p "Implement a new rotation type for the scheduling system.

## Context
Add 'Merchandiser' as a new rotation type alongside existing Juicer and Digital types.

## Files
- app/models/rotation.py - Add MERCHANDISER enum value
- app/services/rotation_manager.py - Handle merchandiser assignments
- app/templates/admin/rotations.html - Add UI for merchandiser rotation
- tests/test_rotation_manager.py - Add merchandiser test cases

## Implementation Plan
1. Add MERCHANDISER to RotationType enum in rotation.py
2. Update RotationManager.assign_rotation() to handle merchandiser logic
3. Add merchandiser section to rotations.html template
4. Write tests for merchandiser assignment edge cases

## Constraints
- Follow existing rotation patterns (see Juicer implementation)
- Merchandiser priority is between Digital and Core
- Employees can only have one active rotation type

## Acceptance Criteria
- Merchandiser appears in rotation admin UI
- Auto-scheduler considers merchandiser assignments
- All existing tests still pass"
Error Handling
If Claude Code fails or returns an error:
Check if the prompt was too long (split into smaller tasks)
Verify file paths are correct
Ensure the plan has sufficient detail
Re-run with additional context if needed
Do Not
Pass vague instructions like "implement the feature we discussed"
Assume Claude has context from previous sessions
Skip file paths or expect Claude to guess locations
Combine unrelated changes in a single prompt