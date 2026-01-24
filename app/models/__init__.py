"""
Database models for Flask Schedule Webapp
Centralizes all SQLAlchemy model imports using factory pattern
"""
from .employee import create_employee_model
from .event import create_event_model
from .schedule import create_schedule_model
from .availability import create_availability_models
from .auto_scheduler import create_auto_scheduler_models
from .system_setting import create_system_setting_model
from .audit import create_audit_models
from .employee_attendance import create_employee_attendance_model
from .paperwork_template import create_paperwork_template_model
from .user_session import create_user_session_model
from .company_holiday import create_company_holiday_model
from .ignored_validation_issue import create_ignored_validation_issue_model
from .shift_block_setting import create_shift_block_setting_model
from .notes import create_notes_models
from .inventory import create_inventory_models


def init_models(db):
    """
    Initialize all models with the database instance

    Args:
        db: SQLAlchemy database instance

    Returns:
        dict: Dictionary containing all model classes
    """
    Employee = create_employee_model(db)
    Event = create_event_model(db)
    Schedule = create_schedule_model(db)
    EmployeeWeeklyAvailability, EmployeeAvailability, EmployeeTimeOff, EmployeeAvailabilityOverride = create_availability_models(db)
    RotationAssignment, PendingSchedule, SchedulerRunHistory, ScheduleException, EventSchedulingOverride, LockedDay, EventTypeOverride = create_auto_scheduler_models(db)
    SystemSetting = create_system_setting_model(db)
    AuditLog, AuditNotificationSettings = create_audit_models(db)
    EmployeeAttendance = create_employee_attendance_model(db)
    PaperworkTemplate = create_paperwork_template_model(db)
    UserSession = create_user_session_model(db)
    CompanyHoliday = create_company_holiday_model(db)
    IgnoredValidationIssue = create_ignored_validation_issue_model(db)
    ShiftBlockSetting = create_shift_block_setting_model(db)
    Note, RecurringReminder = create_notes_models(db)
    inventory_models = create_inventory_models(db)

    return {
        'Employee': Employee,
        'Event': Event,
        'Schedule': Schedule,
        'EmployeeWeeklyAvailability': EmployeeWeeklyAvailability,
        'EmployeeAvailability': EmployeeAvailability,
        'EmployeeTimeOff': EmployeeTimeOff,
        'EmployeeAvailabilityOverride': EmployeeAvailabilityOverride,
        'RotationAssignment': RotationAssignment,
        'PendingSchedule': PendingSchedule,
        'SchedulerRunHistory': SchedulerRunHistory,
        'ScheduleException': ScheduleException,
        'EventSchedulingOverride': EventSchedulingOverride,
        'LockedDay': LockedDay,
        'EventTypeOverride': EventTypeOverride,
        'SystemSetting': SystemSetting,
        'AuditLog': AuditLog,
        'AuditNotificationSettings': AuditNotificationSettings,
        'EmployeeAttendance': EmployeeAttendance,
        'PaperworkTemplate': PaperworkTemplate,
        'UserSession': UserSession,
        'CompanyHoliday': CompanyHoliday,
        'IgnoredValidationIssue': IgnoredValidationIssue,
        'ShiftBlockSetting': ShiftBlockSetting,
        'Note': Note,
        'RecurringReminder': RecurringReminder,
        'SupplyCategory': inventory_models['SupplyCategory'],
        'Supply': inventory_models['Supply'],
        'SupplyAdjustment': inventory_models['SupplyAdjustment'],
        'PurchaseOrder': inventory_models['PurchaseOrder'],
        'OrderItem': inventory_models['OrderItem'],
        'InventoryReminder': inventory_models['InventoryReminder']
    }


__all__ = [
    'init_models',
    'create_employee_model',
    'create_event_model',
    'create_schedule_model',
    'create_availability_models',
    'create_auto_scheduler_models',
    'create_system_setting_model',
    'create_audit_models',
    'create_employee_attendance_model',
    'create_paperwork_template_model',
    'create_user_session_model',
    'create_company_holiday_model',
    # Model registry exports
    'model_registry',
    'get_models',
    'get_db'
]

# Import registry for convenience
from .registry import model_registry, get_models, get_db
