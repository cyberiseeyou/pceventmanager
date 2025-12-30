"""
Employee Import Service - Business logic for employee import operations
Handles duplicate detection, API interaction, and bulk import with data integrity
"""
from typing import List, Optional, Tuple
from sqlalchemy import func
from pydantic import BaseModel, Field, ValidationError
from app import db
import logging

logger = logging.getLogger(__name__)


class CrossmarkEmployee(BaseModel):
    """
    Pydantic model for Crossmark API employee response validation.

    Validates employee data from Crossmark API with comprehensive type checking
    and field-level validation. All fields except 'role' are required.

    Attributes:
        id: MV Retail employee number (primary identifier)
        repId: Primary MV Retail employee number
        employeeId: Crossmark employee ID
        repMvid: Crossmark employee MVID
        title: Full employee name
        lastName: Employee last name
        nameSort: Name formatted for sorting
        availableHoursPerDay: Available hours per day (string)
        scheduledHours: Currently scheduled hours (string)
        visitCount: Number of visits (string)
        role: Optional employee role

    Examples:
        >>> emp = CrossmarkEmployee(
        ...     id="12345",
        ...     repId="12345",
        ...     employeeId="E12345",
        ...     repMvid="E12345",
        ...     title="John Smith",
        ...     lastName="Smith",
        ...     nameSort="SMITH,JOHN",
        ...     availableHoursPerDay="8",
        ...     scheduledHours="32",
        ...     visitCount="5"
        ... )
        >>> emp.title
        'John Smith'
    """
    id: str = Field(..., description="MV Retail employee number")
    repId: str = Field(..., description="Primary MV Retail employee number")
    employeeId: str = Field(..., description="Crossmark employee ID")
    repMvid: str = Field(..., description="Crossmark employee MVID")
    title: str = Field(..., description="Full employee name")
    lastName: str = Field(..., description="Employee last name")
    nameSort: str = Field(..., description="Name for sorting")
    availableHoursPerDay: str = Field(..., description="Available hours per day")
    scheduledHours: Optional[str] = Field(None, description="Currently scheduled hours")
    visitCount: str = Field(..., description="Number of visits")
    role: Optional[str] = Field(None, description="Employee role")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "12345",
                "repId": "12345",
                "employeeId": "E12345",
                "repMvid": "E12345",
                "title": "John Smith",
                "lastName": "Smith",
                "nameSort": "SMITH,JOHN",
                "availableHoursPerDay": "8",
                "scheduledHours": "32",
                "visitCount": "5",
                "role": "Event Specialist"
            }
        }
    }


class EmployeeImportService:
    """
    Service layer for managing employee import operations.

    Provides static methods for:
    - Case-insensitive duplicate name detection
    - Filtering duplicate employees from API results
    - Applying name casing updates from API
    - Bulk importing employees with atomic transactions
    - Fetching employees from Crossmark API
    """

    @staticmethod
    def check_duplicate_name(name: str) -> Optional['Employee']:
        """
        Check if employee name exists in database (case-insensitive).

        Uses database index ix_employee_name_lower for O(log n) performance.
        Leverages func.lower() for case-insensitive matching.

        Args:
            name: Employee name to check for duplicates

        Returns:
            Employee instance if duplicate found, None otherwise

        Examples:
            >>> EmployeeImportService.check_duplicate_name("John Smith")
            <Employee: John Smith>
            >>> EmployeeImportService.check_duplicate_name("JOHN SMITH")
            <Employee: John Smith>  # Same result, case-insensitive
            >>> EmployeeImportService.check_duplicate_name("Jane Doe")
            None  # No duplicate found
        """
        from flask import current_app
        Employee = current_app.config['Employee']

        # Handle edge cases
        if name is None or not isinstance(name, str):
            return None

        # Strip whitespace for consistency
        name = name.strip()
        if not name:
            return None

        return db.session.query(Employee).filter(
            func.lower(Employee.name) == func.lower(name)
        ).first()

    @staticmethod
    def filter_duplicate_employees(
        api_employees: List[CrossmarkEmployee],
        existing_employees: List['Employee']
    ) -> Tuple[List[CrossmarkEmployee], List[Tuple['Employee', str]]]:
        """
        Filter out duplicate employees and identify casing updates.

        Builds an in-memory lowercase name map for O(n) lookup performance,
        then iterates through API employees to classify them as:
        - New employees (not in database)
        - Existing employees with name casing differences

        Args:
            api_employees: Employees from Crossmark API (CrossmarkEmployee instances)
            existing_employees: Current employees in database

        Returns:
            Tuple of (new_employees, employees_needing_casing_update)
            where employees_needing_casing_update is list of (Employee, new_name) tuples

        Examples:
            >>> api_emps = [
            ...     CrossmarkEmployee(
            ...         id='123', repId='123', employeeId='E123', repMvid='E123',
            ...         title='John Smith', lastName='Smith', nameSort='SMITH,JOHN',
            ...         availableHoursPerDay='8', scheduledHours='32', visitCount='5'
            ...     ),
            ...     CrossmarkEmployee(
            ...         id='456', repId='456', employeeId='E456', repMvid='E456',
            ...         title='JANE DOE', lastName='DOE', nameSort='DOE,JANE',
            ...         availableHoursPerDay='8', scheduledHours='32', visitCount='5'
            ...     )
            ... ]
            >>> existing = [Employee(name='jane doe')]  # lowercase in DB
            >>> new, updates = EmployeeImportService.filter_duplicate_employees(api_emps, existing)
            >>> len(new)  # John Smith is new
            1
            >>> len(updates)  # Jane Doe needs casing update
            1
        """
        # Build lowercase name map for O(n) lookup
        existing_names_lower = {
            emp.name.lower().strip(): emp
            for emp in existing_employees
            if emp.name  # Skip None names
        }

        new_employees = []
        employees_to_update = []

        for api_emp in api_employees:
            api_name = api_emp.title
            if not api_name:  # Skip empty names
                continue

            api_name = api_name.strip()  # Normalize whitespace
            api_name_lower = api_name.lower()

            if api_name_lower in existing_names_lower:
                existing_emp = existing_names_lower[api_name_lower]

                # Check if casing differs (e.g., "john smith" vs "John Smith")
                if existing_emp.name != api_name:
                    employees_to_update.append((existing_emp, api_name))
            else:
                # Not a duplicate - add to new employees list
                new_employees.append(api_emp)

        return new_employees, employees_to_update

    @staticmethod
    def apply_casing_updates(employees_to_update: List[Tuple['Employee', str]]) -> int:
        """
        Apply name casing updates to existing employees.

        Updates employee names in database to match API casing (canonical source).
        Uses atomic transaction with automatic rollback on error.

        Args:
            employees_to_update: List of (Employee, new_name) tuples to update

        Returns:
            Count of employees updated

        Raises:
            Exception: If transaction fails (with automatic rollback)

        Examples:
            >>> from app.models.employee import Employee
            >>> emp = Employee(id='123', name='john smith')
            >>> updates = [(emp, 'John Smith')]
            >>> count = EmployeeImportService.apply_casing_updates(updates)
            >>> count
            1
            >>> emp.name
            'John Smith'

        Notes:
            - Logs each update for audit trail
            - Transaction automatically rolls back on error
            - Preserves all other employee fields unchanged
        """
        try:
            updated_count = 0

            for employee, new_name in employees_to_update:
                old_name = employee.name
                employee.name = new_name
                updated_count += 1
                logger.info(f"Updated name casing: '{old_name}' → '{new_name}'")

            # Commit all updates atomically
            db.session.commit()
            return updated_count

        except Exception as e:
            # Rollback on any error
            db.session.rollback()
            logger.error(f"Failed to apply casing updates: {str(e)}")
            raise Exception(f"Failed to apply casing updates: {str(e)}")

    @staticmethod
    def fetch_crossmark_employees() -> List[CrossmarkEmployee]:
        """
        Fetch employees from Crossmark API for current time range.

        Uses SessionAPIService to call /schedulingcontroller/getAvailableReps endpoint.
        Authenticates automatically if session expired. Validates response with Pydantic.

        Returns:
            List of CrossmarkEmployee instances validated from Crossmark API
            Each instance contains: id, repId, employeeId, title, lastName, etc.

        Raises:
            SessionError: If authentication fails or session invalid
            RequestException: If network failure or API error
            ValidationError: If API response doesn't match expected schema

        Examples:
            >>> employees = EmployeeImportService.fetch_crossmark_employees()
            >>> len(employees)
            47
            >>> employees[0].title
            'John Smith'
            >>> employees[0].repId
            '12345'
        """
        from app.integrations.external_api.session_api_service import session_api
        from datetime import datetime, timedelta

        # Get employees for next 7 days (default date range)
        start_date = datetime.now()
        end_date = start_date + timedelta(days=7)

        # Fetch from Crossmark API
        response = session_api.get_available_representatives(
            start_date=start_date,
            end_date=end_date
        )

        if not response:
            raise Exception("Failed to fetch employees from Crossmark API")

        # Extract employee list from response
        # Try different response formats
        if isinstance(response, list):
            # API returns array of employee objects directly
            employee_list = response
        elif isinstance(response, dict):
            # API returns wrapper object - try common key names
            possible_keys = [
                'employees',           # Standard employees key
                'representatives',     # Crossmark-specific
                'reps',               # Short form
                'availableReps',      # Based on endpoint name
                'data',               # Generic data wrapper
                'results',            # Generic results wrapper
            ]

            employee_list = None
            for key in possible_keys:
                if key in response:
                    employee_list = response[key]
                    break

            if employee_list is None:
                # Response is a dict but doesn't have expected keys
                available_keys = list(response.keys())
                raise ValueError(
                    f"Unexpected API response format: dict with keys {available_keys}. "
                    f"Expected one of {possible_keys}. "
                    f"Response sample: {str(response)[:500]}"
                )
        else:
            # Response format unexpected
            raise ValueError(f"Unexpected API response format: {type(response)}")

        # Handle case where API returns dict of employees keyed by ID
        if isinstance(employee_list, dict):
            # Convert dict values to list (the keys are employee IDs, values are employee objects)
            employee_list = list(employee_list.values())

        # Validate employee_list is now a list
        if not isinstance(employee_list, list):
            raise ValueError(
                f"Expected employee_list to be a list, but got {type(employee_list)}. "
                f"Value: {str(employee_list)[:500]}"
            )

        if employee_list and not isinstance(employee_list[0], dict):
            raise ValueError(
                f"Expected employee_list to contain dictionaries, but first item is {type(employee_list[0])}. "
                f"First item: {str(employee_list[0])[:200]}. "
                f"Full list sample: {str(employee_list)[:500]}"
            )

        # Validate and parse with Pydantic
        try:
            return [CrossmarkEmployee(**emp) for emp in employee_list]
        except ValidationError as e:
            # Re-raise with more context about the validation failure
            error_details = e.errors()
            raise ValueError(
                f"Crossmark API response validation failed: {e.error_count()} errors found. "
                f"Errors: {error_details}"
            ) from e

    @staticmethod
    def bulk_import_employees(selected_employees: List[CrossmarkEmployee]) -> int:
        """
        Import selected employees with default values. Atomic transaction.

        Creates Employee records with:
        - Default values: is_active=True, is_supervisor=False, job_title='Event Specialist'
        - Field mapping: repId → mv_retail_employee_number, employeeId → crossmark_employee_id
        - All-or-nothing semantics: transaction rolls back if any employee fails

        Args:
            selected_employees: CrossmarkEmployee instances to import (from Crossmark API)
            Each instance must contain: title (name), repId, employeeId

        Returns:
            Count of successfully imported employees

        Raises:
            Exception: If transaction fails (with automatic rollback)

        Examples:
            >>> selected = [
            ...     CrossmarkEmployee(
            ...         id='123', repId='123', employeeId='E123', repMvid='E123',
            ...         title='John Smith', lastName='Smith', nameSort='SMITH,JOHN',
            ...         availableHoursPerDay='8', scheduledHours='32', visitCount='5'
            ...     ),
            ...     CrossmarkEmployee(
            ...         id='456', repId='456', employeeId='E456', repMvid='E456',
            ...         title='Jane Doe', lastName='Doe', nameSort='DOE,JANE',
            ...         availableHoursPerDay='8', scheduledHours='32', visitCount='5'
            ...     )
            ... ]
            >>> count = EmployeeImportService.bulk_import_employees(selected)
            >>> count
            2

        Notes:
            - Uses db.session.begin() for atomic operations
            - Rollback occurs automatically on any error
            - No partial imports - either all succeed or all fail
        """
        from flask import current_app
        Employee = current_app.config['Employee']

        try:
            imported_count = 0

            for api_emp in selected_employees:
                # Extract fields from Pydantic model via attributes
                name = api_emp.title
                rep_id = api_emp.repId
                employee_id = api_emp.employeeId

                # Use repId as the primary ID (MV Retail employee number)
                employee = Employee(
                    id=rep_id,  # Primary key
                    name=name,
                    mv_retail_employee_number=rep_id,
                    crossmark_employee_id=employee_id,
                    is_active=True,  # Default: active
                    is_supervisor=False,  # Default: not supervisor
                    job_title='Event Specialist'  # Default job title
                )

                db.session.add(employee)
                imported_count += 1

            # Commit all or nothing
            db.session.commit()
            return imported_count

        except Exception as e:
            # Rollback on any error
            db.session.rollback()
            raise Exception(f"Failed to import employees: {str(e)}")
