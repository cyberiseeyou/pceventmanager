"""
AI Tools Module

Defines all available tools/functions that the AI assistant can call.
Each tool maps to existing application functionality.
"""
from typing import Dict, List, Any, Optional
from datetime import datetime, date, timedelta
import logging
from difflib import SequenceMatcher
from sqlalchemy import func

logger = logging.getLogger(__name__)


class AITools:
    """Registry and executor for AI assistant tools"""

    def __init__(self, db_session, models):
        """
        Initialize tools registry

        Args:
            db_session: SQLAlchemy database session
            models: Dictionary of database models
        """
        self.db = db_session
        self.models = models

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get OpenAI/Anthropic compatible tool schemas"""
        return [
            # READ TOOLS
            {
                "type": "function",
                "function": {
                    "name": "count_employees",
                    "description": "Count how many employees are scheduled to work on a specific date",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date in YYYY-MM-DD format or relative dates like 'tomorrow', 'Wednesday', etc."
                            }
                        },
                        "required": ["date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_schedule",
                    "description": "Get detailed schedule information for a specific date, including all events and employee assignments",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date in YYYY-MM-DD format"
                            }
                        },
                        "required": ["date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_time_off",
                    "description": "Check time-off requests for a specific date or employee",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_name": {
                                "type": "string",
                                "description": "Employee name (optional, fuzzy matched if provided)"
                            },
                            "date": {
                                "type": "string",
                                "description": "Date to check (optional)"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_unscheduled_events",
                    "description": "List all events that need to be scheduled",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date_range": {
                                "type": "string",
                                "description": "Optional date range like 'this week', 'next week', 'today'"
                            }
                        }
                    }
                }
            },

            # WRITE TOOLS
            {
                "type": "function",
                "function": {
                    "name": "print_paperwork",
                    "description": "Generate and prepare daily paperwork PDF for a specific date",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date for paperwork in YYYY-MM-DD format"
                            }
                        },
                        "required": ["date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "request_time_off",
                    "description": "Create a time-off request for an employee",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_name": {
                                "type": "string",
                                "description": "Name of the employee (will be fuzzy matched)"
                            },
                            "start_date": {
                                "type": "string",
                                "description": "Start date of time off in YYYY-MM-DD format"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date of time off (same as start for single day)"
                            },
                            "reason": {
                                "type": "string",
                                "description": "Reason for time off (e.g., 'Doctor appointment', 'Vacation')"
                            }
                        },
                        "required": ["employee_name", "start_date", "end_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_employee_info",
                    "description": "Get detailed information about an employee including their schedule, availability, and job title",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_name": {
                                "type": "string",
                                "description": "Employee name (fuzzy matched)"
                            }
                        },
                        "required": ["employee_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_employees",
                    "description": "List all active employees, optionally filtered by job title or availability",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "job_title": {
                                "type": "string",
                                "description": "Filter by job title (e.g., 'Lead Event Specialist', 'Club Supervisor')"
                            },
                            "available_on": {
                                "type": "string",
                                "description": "Filter by availability on a specific date"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_schedule_summary",
                    "description": "Get a summary of schedules for a date range (e.g., this week, next week)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date_range": {
                                "type": "string",
                                "description": "Date range like 'this week', 'next week', 'this month'"
                            }
                        },
                        "required": ["date_range"]
                    }
                }
            },

            # NEW TOOLS - Interactive scheduling operations
            {
                "type": "function",
                "function": {
                    "name": "reschedule_event",
                    "description": "Reschedule an existing scheduled event to a new date, time, or employee. Use this when someone asks to move an event or change who is assigned.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_name": {
                                "type": "string",
                                "description": "Current employee assigned to the event (fuzzy matched)"
                            },
                            "event_type": {
                                "type": "string",
                                "description": "Type of event (Core, Freeosk, Juicer, Supervisor, Digitals, Other)"
                            },
                            "current_date": {
                                "type": "string",
                                "description": "Current scheduled date in YYYY-MM-DD format or relative date"
                            },
                            "new_date": {
                                "type": "string",
                                "description": "New date to reschedule to (optional if only changing employee)"
                            },
                            "new_time": {
                                "type": "string",
                                "description": "New time in HH:MM format (optional)"
                            },
                            "new_employee_name": {
                                "type": "string",
                                "description": "New employee to assign (optional if only changing date/time)"
                            }
                        },
                        "required": ["employee_name", "current_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_available_employees",
                    "description": "Get a list of employees available to work on a specific date, optionally filtered by event type. Use this to find who can be scheduled.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date to check availability in YYYY-MM-DD format or relative date"
                            },
                            "event_type": {
                                "type": "string",
                                "description": "Optional event type to filter by role requirements (Core, Freeosk, Supervisor, etc.)"
                            }
                        },
                        "required": ["date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "cancel_time_off",
                    "description": "Cancel/delete a time-off request for an employee",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_name": {
                                "type": "string",
                                "description": "Employee name (fuzzy matched)"
                            },
                            "date": {
                                "type": "string",
                                "description": "A date within the time-off period to cancel"
                            }
                        },
                        "required": ["employee_name", "date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_pending_time_off",
                    "description": "List all upcoming time-off requests. Use this to see who has time off coming up.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "days_ahead": {
                                "type": "integer",
                                "description": "Number of days to look ahead (default 30)"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_event_details",
                    "description": "Get detailed information about a specific event including its schedule, assigned employee, and event dates",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_name": {
                                "type": "string",
                                "description": "Name or partial name of the event (fuzzy matched)"
                            },
                            "event_id": {
                                "type": "integer",
                                "description": "Event ID if known"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "assign_employee_to_event",
                    "description": "Assign an employee to an unscheduled event. Use this to schedule someone for an event that doesn't have anyone assigned yet.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_name": {
                                "type": "string",
                                "description": "Name of the event to schedule (fuzzy matched)"
                            },
                            "employee_name": {
                                "type": "string",
                                "description": "Name of the employee to assign (fuzzy matched)"
                            },
                            "scheduled_date": {
                                "type": "string",
                                "description": "Date to schedule the event in YYYY-MM-DD format"
                            },
                            "scheduled_time": {
                                "type": "string",
                                "description": "Time to schedule in HH:MM format (will use default for event type if not specified)"
                            }
                        },
                        "required": ["event_name", "employee_name", "scheduled_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "unschedule_event",
                    "description": "Remove an employee assignment from a scheduled event, making it unscheduled again",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_name": {
                                "type": "string",
                                "description": "Current employee assigned to the event"
                            },
                            "date": {
                                "type": "string",
                                "description": "Date of the scheduled event"
                            },
                            "event_type": {
                                "type": "string",
                                "description": "Type of event (optional, helps narrow down if multiple events)"
                            }
                        },
                        "required": ["employee_name", "date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_scheduling_conflicts",
                    "description": "Check if scheduling an employee for a specific date/time would cause any conflicts",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_name": {
                                "type": "string",
                                "description": "Employee name to check"
                            },
                            "date": {
                                "type": "string",
                                "description": "Date to check"
                            },
                            "event_type": {
                                "type": "string",
                                "description": "Type of event being scheduled"
                            }
                        },
                        "required": ["employee_name", "date", "event_type"]
                    }
                }
            },

            # ===== EMERGENCY & COVERAGE TOOLS =====
            {
                "type": "function",
                "function": {
                    "name": "find_replacement",
                    "description": "Find available employees who can cover/replace someone's shift. Use this when an employee calls out sick or can't work their scheduled shift. Returns ranked list of qualified replacements.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_name": {
                                "type": "string",
                                "description": "Name of the employee who needs to be replaced/covered"
                            },
                            "date": {
                                "type": "string",
                                "description": "Date of the shift needing coverage"
                            },
                            "event_type": {
                                "type": "string",
                                "description": "Type of event (Core, Juicer, Freeosk, etc.) - helps find qualified replacements"
                            }
                        },
                        "required": ["employee_name", "date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_employee_schedule",
                    "description": "Get all scheduled events for a specific employee over a date range. Shows what someone is working this week, their upcoming shifts, etc.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_name": {
                                "type": "string",
                                "description": "Name of the employee"
                            },
                            "date_range": {
                                "type": "string",
                                "description": "Date range like 'today', 'this week', 'next week', or specific dates"
                            }
                        },
                        "required": ["employee_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "swap_shifts",
                    "description": "Swap schedules between two employees. Use when two employees want to trade shifts or you need to exchange their assignments.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee1_name": {
                                "type": "string",
                                "description": "First employee's name"
                            },
                            "employee2_name": {
                                "type": "string",
                                "description": "Second employee's name"
                            },
                            "date": {
                                "type": "string",
                                "description": "Date of the shifts to swap"
                            },
                            "event_type": {
                                "type": "string",
                                "description": "Optional: specific event type to swap (if employees have multiple events)"
                            }
                        },
                        "required": ["employee1_name", "employee2_name", "date"]
                    }
                }
            },

            # ===== WORKLOAD & ANALYTICS TOOLS =====
            {
                "type": "function",
                "function": {
                    "name": "get_workload_summary",
                    "description": "Get workload summary showing how many events/hours each employee has worked or is scheduled for. Helps identify who needs more hours or who's overworked.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date_range": {
                                "type": "string",
                                "description": "Date range like 'this week', 'last week', 'this month'"
                            },
                            "sort_by": {
                                "type": "string",
                                "description": "Sort by 'most' (highest workload first) or 'least' (lowest first)"
                            }
                        },
                        "required": ["date_range"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_overtime_risk",
                    "description": "Check which employees are approaching or exceeding the 6-day work limit for the week. Helps prevent overtime violations.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "week_of": {
                                "type": "string",
                                "description": "Date within the week to check (defaults to current week)"
                            }
                        }
                    }
                }
            },

            # ===== ROTATION & COVERAGE TOOLS =====
            {
                "type": "function",
                "function": {
                    "name": "get_rotation_schedule",
                    "description": "Get the rotation schedule showing who is assigned to Juicer and Primary Lead rotations for each day of the week.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "rotation_type": {
                                "type": "string",
                                "description": "Type of rotation: 'juicer', 'primary_lead', or 'all'"
                            },
                            "week_of": {
                                "type": "string",
                                "description": "Date within the week to show (defaults to current week)"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_lead_coverage",
                    "description": "Check if there is proper Lead Event Specialist coverage for opening and closing shifts on a specific date.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date to check coverage for"
                            }
                        },
                        "required": ["date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_urgent_events",
                    "description": "Get events that are due soon but not yet scheduled. Helps identify events at risk of missing their deadline.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "days_ahead": {
                                "type": "integer",
                                "description": "Number of days to look ahead (default 7)"
                            }
                        }
                    }
                }
            },

            # ===== COMPANY & SYSTEM TOOLS =====
            {
                "type": "function",
                "function": {
                    "name": "check_company_holidays",
                    "description": "Check if a specific date is a company holiday, or list upcoming company holidays.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Specific date to check, or omit to see upcoming holidays"
                            },
                            "days_ahead": {
                                "type": "integer",
                                "description": "Number of days ahead to look for holidays (default 30)"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_daily_roster",
                    "description": "Get a complete roster/overview for a specific date showing all employees working, their events, times, and any issues. Perfect for daily standup or shift handoff.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date to get roster for (defaults to today)"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_scheduling_rules",
                    "description": "Get information about scheduling rules and constraints. Use when you need to explain why something can or can't be scheduled.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "description": "Specific topic: 'roles', 'event_types', 'time_slots', 'constraints', or 'all'"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "refresh_database",
                    "description": "Refresh the local database by syncing with the external API (Crossmark). Use this BEFORE verifying any changes to ensure you're seeing the latest data. This pulls fresh data from the external system.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sync_type": {
                                "type": "string",
                                "description": "What to sync: 'schedules' (default), 'events', 'employees', or 'all'"
                            }
                        }
                    }
                }
            },

            # ===== BULK OPERATIONS =====
            {
                "type": "function",
                "function": {
                    "name": "bulk_reschedule_day",
                    "description": "Move ALL events from one date to another. Use when a store closes unexpectedly or for weather emergencies. This is a major operation that requires confirmation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "from_date": {
                                "type": "string",
                                "description": "Date to move events FROM (e.g., 'tomorrow', 'Friday')"
                            },
                            "to_date": {
                                "type": "string",
                                "description": "Date to move events TO (e.g., 'Saturday', 'next Monday')"
                            },
                            "reason": {
                                "type": "string",
                                "description": "Reason for the bulk move (e.g., 'store closed', 'weather emergency')"
                            }
                        },
                        "required": ["from_date", "to_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "reassign_employee_events",
                    "description": "Remove an employee from ALL their scheduled events. Use when someone quits, is terminated, or goes on extended leave. Shows what needs reassignment.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_name": {
                                "type": "string",
                                "description": "Name of the employee to remove from all events"
                            },
                            "reason": {
                                "type": "string",
                                "description": "Reason (e.g., 'terminated', 'quit', 'extended leave')"
                            },
                            "date_range": {
                                "type": "string",
                                "description": "Optional date range to limit (e.g., 'this week', 'next 2 weeks'). Defaults to all future events."
                            }
                        },
                        "required": ["employee_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "auto_fill_unscheduled",
                    "description": "Attempt to automatically assign available employees to unscheduled events for a date. Shows proposed assignments for review before committing.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date to auto-fill (e.g., 'tomorrow', 'next Monday')"
                            },
                            "event_type": {
                                "type": "string",
                                "description": "Optional: only fill specific event type (e.g., 'Core', 'Juicer')"
                            }
                        },
                        "required": ["date"]
                    }
                }
            }
        ]

    def execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool by name

        Args:
            tool_name: Name of the tool to execute
            tool_args: Arguments for the tool

        Returns:
            Dictionary with execution results
        """
        # Map tool names to methods
        tool_map = {
            'count_employees': self._tool_count_employees,
            'get_schedule': self._tool_get_schedule,
            'check_time_off': self._tool_check_time_off,
            'get_unscheduled_events': self._tool_get_unscheduled_events,
            'print_paperwork': self._tool_print_paperwork,
            'request_time_off': self._tool_request_time_off,
            'get_employee_info': self._tool_get_employee_info,
            'list_employees': self._tool_list_employees,
            'get_schedule_summary': self._tool_get_schedule_summary,
            # Interactive scheduling tools
            'reschedule_event': self._tool_reschedule_event,
            'get_available_employees': self._tool_get_available_employees,
            'cancel_time_off': self._tool_cancel_time_off,
            'get_pending_time_off': self._tool_get_pending_time_off,
            'get_event_details': self._tool_get_event_details,
            'assign_employee_to_event': self._tool_assign_employee_to_event,
            'unschedule_event': self._tool_unschedule_event,
            'check_scheduling_conflicts': self._tool_check_scheduling_conflicts,
            # Emergency & coverage tools
            'find_replacement': self._tool_find_replacement,
            'get_employee_schedule': self._tool_get_employee_schedule,
            'swap_shifts': self._tool_swap_shifts,
            # Workload & analytics tools
            'get_workload_summary': self._tool_get_workload_summary,
            'check_overtime_risk': self._tool_check_overtime_risk,
            # Rotation & coverage tools
            'get_rotation_schedule': self._tool_get_rotation_schedule,
            'check_lead_coverage': self._tool_check_lead_coverage,
            'get_urgent_events': self._tool_get_urgent_events,
            # Company & system tools
            'check_company_holidays': self._tool_check_company_holidays,
            'get_daily_roster': self._tool_get_daily_roster,
            'get_scheduling_rules': self._tool_get_scheduling_rules,
            'refresh_database': self._tool_refresh_database,
            # Bulk operations
            'bulk_reschedule_day': self._tool_bulk_reschedule_day,
            'reassign_employee_events': self._tool_reassign_employee_events,
            'auto_fill_unscheduled': self._tool_auto_fill_unscheduled,
        }

        if tool_name not in tool_map:
            return {
                'success': False,
                'message': f"Unknown tool: {tool_name}",
                'data': None
            }

        try:
            return tool_map[tool_name](tool_args)
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {str(e)}", exc_info=True)
            return {
                'success': False,
                'message': f"Error executing {tool_name}: {str(e)}",
                'data': {'error': str(e)}
            }

    # ===== READ TOOLS =====

    def _tool_verify_schedule(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Verify schedule for a specific date"""
        date_str = args.get('date')
        parsed_date = self._parse_date(date_str)

        if not parsed_date:
            return {
                'success': False,
                'message': f"Could not parse date: {date_str}",
                'data': None
            }

        # Call schedule verification service
        from app.services.schedule_verification import ScheduleVerificationService
        service = ScheduleVerificationService(self.db, self.models)
        result = service.verify_schedule(parsed_date)

        # Format response
        status_messages = {
            'pass': '✅ All clear!',
            'warning': '⚠️ Warnings found',
            'fail': '❌ Critical issues found'
        }

        status_emoji = status_messages.get(result.status, '')

        message = f"{status_emoji} Verified schedule for {parsed_date.strftime('%A, %B %d, %Y')}. "
        message += f"Status: {result.status.title()}. "
        message += f"{result.summary['total_events']} events, {result.summary['total_employees']} employees.\n"

        if result.issues:
            # Include detailed issue information with NUMBERED list
            message += "\n**Issues Found:**\n"

            # Group issues by severity (critical first, then warning, then info)
            critical_issues = [i for i in result.issues if i.severity == 'critical']
            warning_issues = [i for i in result.issues if i.severity == 'warning']
            info_issues = [i for i in result.issues if i.severity == 'info']

            # Combine all issues in priority order for numbered list
            all_issues_ordered = critical_issues + warning_issues + info_issues

            # Show numbered issues
            issue_num = 1
            for issue in critical_issues:
                recommendation = self._get_issue_recommendation(issue)
                message += f"\n**Issue #{issue_num}** ❌ CRITICAL - {issue.rule_name}\n"
                message += f"   Problem: {issue.message}\n"
                if recommendation:
                    message += f"   Fix: {recommendation}\n"
                issue_num += 1

            for issue in warning_issues:
                recommendation = self._get_issue_recommendation(issue)
                message += f"\n**Issue #{issue_num}** ⚠️ WARNING - {issue.rule_name}\n"
                message += f"   Problem: {issue.message}\n"
                if recommendation:
                    message += f"   Fix: {recommendation}\n"
                issue_num += 1

            # Info messages (show first 3)
            for issue in info_issues[:3]:
                message += f"\n**Issue #{issue_num}** ℹ️ INFO - {issue.rule_name}\n"
                message += f"   {issue.message}\n"
                issue_num += 1

            if len(info_issues) > 3:
                message += f"\n   ... and {len(info_issues) - 3} more informational messages\n"

            # Add interactive prompt
            message += f"\n---\n📋 **Found {len(result.issues)} issue(s)** ({len(critical_issues)} critical, {len(warning_issues)} warnings)\n"
            message += "\n**Would you like me to walk you through fixing these issues one by one?**\n"
            message += "Say 'yes' and I'll start with Issue #1, explain the problem, and suggest a fix."
        else:
            message += "\nNo issues found. The schedule looks good!"

        return {
            'success': True,
            'message': message,
            'data': {
                'verification_result': result.to_dict(),
                'date': parsed_date.isoformat(),
                'issues_for_fixing': [
                    {
                        'rule_name': issue.rule_name,
                        'severity': issue.severity,
                        'message': issue.message,
                        'details': issue.details,
                        'recommendation': self._get_issue_recommendation(issue)
                    }
                    for issue in result.issues
                ] if result.issues else []
            },
            'suggested_actions': [
                {'label': 'Fix Issues', 'action': 'fix_verification_issues'},
                {'label': 'View Full Report', 'action': f'/schedule-verification?date={parsed_date.isoformat()}'}
            ] if result.issues else None
        }

    def _get_issue_recommendation(self, issue) -> str:
        """Generate a recommendation for how to fix a verification issue"""
        rule_recommendations = {
            # Core event issues
            'Core Event Limit': 'Remove one of the Core events from this employee or reassign it to another qualified employee.',
            'Core Event Time': 'Reschedule this Core event to a valid time slot (9:45, 10:30, 11:00, or 11:30).',
            'Core-Supervisor Pairing': 'Create and schedule a Supervisor event for this Core event.',

            # Employee availability issues
            'Employee Availability': 'Reassign this event to an employee who IS available on this day.',
            'Employee Time Off': 'Reassign this event to a different employee who is not on time-off.',

            # Event assignment issues
            'Freeosk Assignment': 'Reassign this Freeosk event to a Club Supervisor or Lead Event Specialist.',
            'Digital Event Assignment': 'Reassign this Digital event to a Club Supervisor or Lead Event Specialist.',
            'Supervisor Assignment': 'Reassign this Supervisor event to a Club Supervisor or Lead Event Specialist.',

            # Juicer issues
            'Juicer Qualification': 'Reassign this Juicer event to a Club Supervisor or Juicer Barista.',
            'Juicer Rotation': 'Consider assigning this Juicer event to the rotation employee for this day.',
            'Juicer-Core Conflict': 'Remove the Core event from this employee since they are working Juicer.',

            # Balance and coverage
            'Shift Balance': 'Move some Core events from overloaded time slots to empty ones.',

            # Unscheduled events
            'Event Due Tomorrow': 'Assign an available employee to this event today.',
            'Unscheduled Required Event': 'Assign an available employee to this event before the due date.',

            # Legacy rule names (for backwards compatibility)
            'Juicer Event Assignment': 'Reassign to a Club Supervisor or Juicer Barista.',
            'Supervisor Event Time': 'Reschedule to 12:00 noon.',
            'Employee Weekly Availability': 'Reassign to an employee available on this day.',
            'Employee Work Days Limit': 'Remove from one scheduled day this week.',
            'Event Date Range': 'Reschedule within the event\'s valid date range.',
        }

        recommendation = rule_recommendations.get(issue.rule_name)

        # Build specific recommendation from issue details
        if issue.details:
            # For employee-related issues, suggest finding replacement
            if 'employee_name' in issue.details and not recommendation:
                emp_name = issue.details.get('employee_name')
                recommendation = f"Find a replacement for {emp_name} using 'find replacement for {emp_name}'."

            # For event issues, mention the specific event
            if 'event_name' in issue.details and recommendation:
                event_name = issue.details.get('event_name')
                # Append event context if not already specific
                if event_name and 'this event' in recommendation:
                    recommendation = recommendation.replace('this event', f"'{event_name}'")

            # For swap suggestions
            if 'swap_suggestions' in issue.details and issue.details['swap_suggestions']:
                suggestion = issue.details['swap_suggestions'][0]
                if 'suggestion' in suggestion:
                    recommendation = suggestion['suggestion']

        return recommendation

    def _tool_count_employees(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Count employees scheduled for a date"""
        date_str = args.get('date')
        parsed_date = self._parse_date(date_str)

        if not parsed_date:
            return {
                'success': False,
                'message': f"Could not parse date: {date_str}",
                'data': None
            }

        Schedule = self.models['Schedule']

        # Count distinct employees
        count = self.db.query(Schedule.employee_id).filter(
            func.date(Schedule.schedule_datetime) == parsed_date
        ).distinct().count()

        day_name = parsed_date.strftime('%A, %B %d')
        message = f"📊 {count} employee{'s' if count != 1 else ''} scheduled for {day_name}."

        return {
            'success': True,
            'message': message,
            'data': {
                'count': count,
                'date': parsed_date.isoformat()
            }
        }

    def _tool_get_schedule(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed schedule for a date"""
        date_str = args.get('date')
        parsed_date = self._parse_date(date_str)

        if not parsed_date:
            return {
                'success': False,
                'message': f"Could not parse date: {date_str}",
                'data': None
            }

        Schedule = self.models['Schedule']
        Event = self.models['Event']
        Employee = self.models['Employee']

        # Get all schedules for the date
        schedules = self.db.query(Schedule, Event, Employee).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).join(
            Employee, Schedule.employee_id == Employee.id
        ).filter(
            func.date(Schedule.schedule_datetime) == parsed_date
        ).order_by(Schedule.schedule_datetime).all()

        if not schedules:
            return {
                'success': True,
                'message': f"No events scheduled for {parsed_date.strftime('%A, %B %d')}.",
                'data': {'schedules': [], 'date': parsed_date.isoformat()}
            }

        # Format schedule data
        schedule_list = []
        for sched, event, emp in schedules:
            schedule_list.append({
                'time': sched.schedule_datetime.strftime('%I:%M %p'),
                'employee': emp.name,
                'job_title': emp.job_title,
                'event': event.project_name,
                'event_type': event.event_type
            })

        message = f"📅 Schedule for {parsed_date.strftime('%A, %B %d')}:\n"
        message += f"Total: {len(schedules)} event(s)\n"

        # Group by time
        from collections import defaultdict
        by_time = defaultdict(list)
        for item in schedule_list:
            by_time[item['time']].append(f"{item['employee']} - {item['event_type']}")

        for time, events in sorted(by_time.items())[:5]:  # Show first 5 time slots
            message += f"{time}: {', '.join(events)}\n"

        return {
            'success': True,
            'message': message.strip(),
            'data': {
                'schedules': schedule_list,
                'date': parsed_date.isoformat(),
                'total': len(schedules)
            },
            'suggested_actions': [
                {'label': 'View Full Schedule', 'action': f'/daily-view/{parsed_date.isoformat()}'}
            ]
        }

    def _tool_check_time_off(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Check time-off requests"""
        employee_name = args.get('employee_name')
        date_str = args.get('date')

        EmployeeTimeOff = self.models['EmployeeTimeOff']
        Employee = self.models['Employee']

        query = self.db.query(EmployeeTimeOff, Employee).join(
            Employee, EmployeeTimeOff.employee_id == Employee.id
        )

        # Filter by employee if provided
        if employee_name:
            matched_employee = self._find_employee_by_name(employee_name)
            if matched_employee:
                query = query.filter(Employee.id == matched_employee.id)
            else:
                return {
                    'success': False,
                    'message': f"Could not find employee: {employee_name}",
                    'data': None
                }

        # Filter by date if provided
        if date_str:
            parsed_date = self._parse_date(date_str)
            if parsed_date:
                query = query.filter(
                    EmployeeTimeOff.start_date <= parsed_date,
                    EmployeeTimeOff.end_date >= parsed_date
                )

        time_off_records = query.all()

        if not time_off_records:
            message = "No time-off requests found"
            if employee_name:
                message += f" for {employee_name}"
            if date_str:
                message += f" on {date_str}"
            message += "."

            return {
                'success': True,
                'message': message,
                'data': {'time_off': []}
            }

        # Format results
        time_off_list = []
        for time_off, emp in time_off_records:
            time_off_list.append({
                'employee': emp.name,
                'start_date': time_off.start_date.isoformat(),
                'end_date': time_off.end_date.isoformat(),
                'reason': time_off.reason or 'Not specified'
            })

        message = f"📋 Found {len(time_off_list)} time-off request(s):\n"
        for i, to in enumerate(time_off_list[:3], 1):  # Show first 3
            message += f"{i}. {to['employee']}: {to['start_date']} to {to['end_date']} ({to['reason']})\n"

        if len(time_off_list) > 3:
            message += f"... and {len(time_off_list) - 3} more"

        return {
            'success': True,
            'message': message.strip(),
            'data': {'time_off': time_off_list}
        }

    def _tool_get_unscheduled_events(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get unscheduled events"""
        date_range = args.get('date_range', 'all')

        Event = self.models['Event']

        query = self.db.query(Event).filter(Event.is_scheduled == False)

        # Apply date range filter if specified
        if date_range and date_range != 'all':
            start_date, end_date = self._parse_date_range(date_range)
            if start_date and end_date:
                query = query.filter(
                    Event.start_datetime >= start_date,
                    Event.due_datetime <= end_date
                )

        unscheduled = query.all()

        if not unscheduled:
            return {
                'success': True,
                'message': "✅ No unscheduled events found.",
                'data': {'unscheduled': []}
            }

        # Format results
        event_list = []
        for event in unscheduled:
            event_list.append({
                'id': event.id,
                'name': event.project_name,
                'type': event.event_type,
                'start_date': event.start_datetime.date().isoformat(),
                'due_date': event.due_datetime.date().isoformat()
            })

        message = f"📌 Found {len(event_list)} unscheduled event(s)"
        if date_range and date_range != 'all':
            message += f" for {date_range}"
        message += "."

        return {
            'success': True,
            'message': message,
            'data': {'unscheduled': event_list, 'count': len(event_list)},
            'suggested_actions': [
                {'label': 'View Unscheduled Events', 'action': '/unscheduled'}
            ]
        }

    # ===== WRITE TOOLS =====

    def _tool_print_paperwork(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Generate daily paperwork"""
        date_str = args.get('date')
        parsed_date = self._parse_date(date_str)
        confirmed = args.get('_confirmed', False)

        if not parsed_date:
            return {
                'success': False,
                'message': f"Could not parse date: {date_str}",
                'data': None
            }

        if not confirmed:
            # Require confirmation
            return {
                'success': True,
                'message': f"⚠️ Confirm: Generate paperwork PDF for {parsed_date.strftime('%A, %B %d, %Y')}?",
                'requires_confirmation': True,
                'confirmation_data': {
                    'tool_name': 'print_paperwork',
                    'tool_args': {'date': parsed_date.isoformat()},
                    'action': f"Generate paperwork for {parsed_date.strftime('%A, %B %d')}"
                }
            }

        # Generate paperwork (this would call the actual paperwork generation service)
        message = f"🖨️ Paperwork for {parsed_date.strftime('%A, %B %d')} is being generated. You can download it when ready."

        return {
            'success': True,
            'message': message,
            'data': {'date': parsed_date.isoformat(), 'status': 'generating'},
            'suggested_actions': [
                {'label': 'Download PDF', 'action': f'/admin/generate-paperwork?date={parsed_date.isoformat()}'}
            ]
        }

    def _tool_request_time_off(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create time-off request"""
        employee_name = args.get('employee_name')
        start_date_str = args.get('start_date')
        end_date_str = args.get('end_date')
        reason = args.get('reason', '')
        confirmed = args.get('_confirmed', False)

        # Find employee
        employee = self._find_employee_by_name(employee_name)
        if not employee:
            return {
                'success': False,
                'message': f"Could not find employee: {employee_name}",
                'data': None
            }

        # Parse dates
        start_date = self._parse_date(start_date_str)
        end_date = self._parse_date(end_date_str)

        if not start_date or not end_date:
            return {
                'success': False,
                'message': "Invalid date format",
                'data': None
            }

        if not confirmed:
            # Require confirmation
            return {
                'success': True,
                'message': f"⚠️ Confirm: Add time-off for {employee.name} from {start_date.strftime('%A, %B %d')} to {end_date.strftime('%A, %B %d')}?\nReason: {reason or 'Not specified'}",
                'requires_confirmation': True,
                'confirmation_data': {
                    'tool_name': 'request_time_off',
                    'tool_args': {
                        'employee_name': employee.name,
                        'start_date': start_date.isoformat(),
                        'end_date': end_date.isoformat(),
                        'reason': reason
                    },
                    'action': f"Create time-off request for {employee.name}"
                }
            }

        # Create time-off request
        EmployeeTimeOff = self.models['EmployeeTimeOff']
        time_off = EmployeeTimeOff(
            employee_id=employee.id,
            start_date=start_date,
            end_date=end_date,
            reason=reason
        )
        self.db.add(time_off)
        self.db.commit()

        message = f"✅ Time-off request created for {employee.name} from {start_date.strftime('%b %d')} to {end_date.strftime('%b %d')}."
        if reason:
            message += f" Reason: {reason}"

        return {
            'success': True,
            'message': message,
            'data': {
                'employee': employee.name,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'reason': reason
            }
        }

    def _tool_get_employee_info(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get employee information"""
        employee_name = args.get('employee_name')

        employee = self._find_employee_by_name(employee_name)
        if not employee:
            return {
                'success': False,
                'message': f"Could not find employee: {employee_name}",
                'data': None
            }

        message = f"👤 {employee.name}\n"
        message += f"Job Title: {employee.job_title}\n"
        message += f"Status: {'Active' if employee.is_active else 'Inactive'}\n"
        if employee.email:
            message += f"Email: {employee.email}\n"
        if employee.phone:
            message += f"Phone: {employee.phone}"

        return {
            'success': True,
            'message': message.strip(),
            'data': {
                'id': employee.id,
                'name': employee.name,
                'job_title': employee.job_title,
                'email': employee.email,
                'phone': employee.phone,
                'is_active': employee.is_active
            }
        }

    def _tool_list_employees(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """List employees"""
        job_title = args.get('job_title')
        available_on = args.get('available_on')

        Employee = self.models['Employee']

        query = self.db.query(Employee).filter(Employee.is_active == True)

        # Filter by job title
        if job_title:
            query = query.filter(Employee.job_title.ilike(f'%{job_title}%'))

        # Filter by availability
        if available_on:
            parsed_date = self._parse_date(available_on)
            if parsed_date:
                # TODO: Add availability filtering logic
                pass

        employees = query.all()

        if not employees:
            return {
                'success': True,
                'message': "No employees found matching criteria.",
                'data': {'employees': []}
            }

        # Format results
        emp_list = []
        for emp in employees:
            emp_list.append({
                'id': emp.id,
                'name': emp.name,
                'job_title': emp.job_title
            })

        message = f"👥 Found {len(emp_list)} employee(s)"
        if job_title:
            message += f" with job title '{job_title}'"
        message += ":\n"

        for i, emp in enumerate(emp_list[:10], 1):
            message += f"{i}. {emp['name']} ({emp['job_title']})\n"

        if len(emp_list) > 10:
            message += f"... and {len(emp_list) - 10} more"

        return {
            'success': True,
            'message': message.strip(),
            'data': {'employees': emp_list, 'count': len(emp_list)}
        }

    def _tool_get_schedule_summary(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get schedule summary for a date range"""
        date_range = args.get('date_range', 'this week')
        start_date, end_date = self._parse_date_range(date_range)

        if not start_date or not end_date:
            return {
                'success': False,
                'message': f"Could not parse date range: {date_range}",
                'data': None
            }

        Schedule = self.models['Schedule']
        Event = self.models['Event']

        # Count schedules per day
        daily_counts = self.db.query(
            func.date(Schedule.schedule_datetime).label('date'),
            func.count(Schedule.id).label('count')
        ).filter(
            Schedule.schedule_datetime >= start_date,
            Schedule.schedule_datetime <= end_date
        ).group_by(func.date(Schedule.schedule_datetime)).all()

        if not daily_counts:
            return {
                'success': True,
                'message': f"No schedules found for {date_range}.",
                'data': {'summary': []}
            }

        # Format results
        summary = []
        for day_date, count in daily_counts:
            summary.append({
                'date': day_date.isoformat(),
                'day_name': day_date.strftime('%A'),
                'event_count': count
            })

        message = f"📊 Schedule summary for {date_range}:\n"
        for item in summary:
            message += f"{item['day_name']}: {item['event_count']} events\n"

        total = sum(item['event_count'] for item in summary)
        message += f"\nTotal: {total} events across {len(summary)} days"

        return {
            'success': True,
            'message': message.strip(),
            'data': {'summary': summary, 'total': total}
        }

    # ===== NEW INTERACTIVE TOOLS =====

    def _tool_reschedule_event(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Reschedule an event to a new date/time/employee"""
        employee_name = args.get('employee_name')
        current_date_str = args.get('current_date')
        new_date_str = args.get('new_date')
        new_time = args.get('new_time')
        new_employee_name = args.get('new_employee_name')
        event_type = args.get('event_type')
        confirmed = args.get('_confirmed', False)

        # Find current employee
        employee = self._find_employee_by_name(employee_name)
        if not employee:
            return {
                'success': False,
                'message': f"Could not find employee: {employee_name}",
                'data': None
            }

        # Parse current date
        current_date = self._parse_date(current_date_str)
        if not current_date:
            return {
                'success': False,
                'message': f"Could not parse date: {current_date_str}",
                'data': None
            }

        # Find the schedule record
        Schedule = self.models['Schedule']
        Event = self.models['Event']

        query = self.db.query(Schedule, Event).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            Schedule.employee_id == employee.id,
            func.date(Schedule.schedule_datetime) == current_date
        )

        if event_type:
            query = query.filter(Event.event_type == event_type)

        result = query.first()

        if not result:
            return {
                'success': False,
                'message': f"No scheduled event found for {employee.name} on {current_date.strftime('%B %d')}",
                'data': None
            }

        schedule, event = result

        # Determine what's changing
        changes = []
        new_date_parsed = self._parse_date(new_date_str) if new_date_str else None
        new_employee = self._find_employee_by_name(new_employee_name) if new_employee_name else None

        if new_date_parsed:
            changes.append(f"date from {current_date.strftime('%B %d')} to {new_date_parsed.strftime('%B %d')}")
        if new_time:
            changes.append(f"time to {new_time}")
        if new_employee:
            changes.append(f"employee from {employee.name} to {new_employee.name}")

        if not changes:
            return {
                'success': False,
                'message': "No changes specified. Please provide a new date, time, or employee.",
                'data': None
            }

        if not confirmed:
            return {
                'success': True,
                'message': f"⚠️ Confirm: Reschedule {event.project_name} ({event.event_type})?\nChanges: {', '.join(changes)}",
                'requires_confirmation': True,
                'confirmation_data': {
                    'tool_name': 'reschedule_event',
                    'tool_args': args,
                    'action': f"Reschedule {event.project_name}"
                }
            }

        # Apply changes
        from datetime import datetime as dt
        if new_date_parsed:
            current_time = schedule.schedule_datetime.time()
            schedule.schedule_datetime = dt.combine(new_date_parsed, current_time)

        if new_time:
            try:
                new_time_parsed = dt.strptime(new_time, '%H:%M').time()
                schedule.schedule_datetime = dt.combine(
                    schedule.schedule_datetime.date(),
                    new_time_parsed
                )
            except ValueError:
                pass

        if new_employee:
            schedule.employee_id = new_employee.id

        self.db.commit()

        message = f"✅ Rescheduled {event.project_name} ({event.event_type}). Changes: {', '.join(changes)}"

        return {
            'success': True,
            'message': message,
            'data': {
                'event_name': event.project_name,
                'event_type': event.event_type,
                'changes': changes
            }
        }

    def _tool_get_available_employees(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get employees available for a specific date"""
        date_str = args.get('date')
        event_type = args.get('event_type')

        parsed_date = self._parse_date(date_str)
        if not parsed_date:
            return {
                'success': False,
                'message': f"Could not parse date: {date_str}",
                'data': None
            }

        Employee = self.models['Employee']
        EmployeeTimeOff = self.models['EmployeeTimeOff']
        EmployeeAvailability = self.models.get('EmployeeAvailability')
        Schedule = self.models['Schedule']
        Event = self.models['Event']

        # Get all active employees
        all_employees = self.db.query(Employee).filter(Employee.is_active == True).all()

        # Get employees on time off
        time_off_ids = set()
        time_off_records = self.db.query(EmployeeTimeOff.employee_id).filter(
            EmployeeTimeOff.start_date <= parsed_date,
            EmployeeTimeOff.end_date >= parsed_date
        ).all()
        time_off_ids = {r[0] for r in time_off_records}

        # Get employees marked unavailable
        unavailable_ids = set()
        if EmployeeAvailability:
            unavailable_records = self.db.query(EmployeeAvailability.employee_id).filter(
                EmployeeAvailability.date == parsed_date,
                EmployeeAvailability.is_available == False
            ).all()
            unavailable_ids = {r[0] for r in unavailable_records}

        # Get employees already scheduled for Core events (one per day limit)
        core_scheduled_ids = set()
        if event_type == 'Core':
            core_schedules = self.db.query(Schedule.employee_id).join(
                Event, Schedule.event_ref_num == Event.project_ref_num
            ).filter(
                func.date(Schedule.schedule_datetime) == parsed_date,
                Event.event_type == 'Core'
            ).all()
            core_scheduled_ids = {r[0] for r in core_schedules}

        # Filter available employees
        available = []
        for emp in all_employees:
            if emp.id in time_off_ids:
                continue
            if emp.id in unavailable_ids:
                continue
            if emp.id in core_scheduled_ids:
                continue

            # Check role requirements for event type
            if event_type and not emp.can_work_event_type(event_type):
                continue

            available.append({
                'id': emp.id,
                'name': emp.name,
                'job_title': emp.job_title
            })

        day_name = parsed_date.strftime('%A, %B %d')
        message = f"👥 {len(available)} employee(s) available on {day_name}"
        if event_type:
            message += f" for {event_type} events"
        message += ":\n"

        for i, emp in enumerate(available[:8], 1):
            message += f"{i}. {emp['name']} ({emp['job_title']})\n"

        if len(available) > 8:
            message += f"... and {len(available) - 8} more"

        return {
            'success': True,
            'message': message.strip(),
            'data': {'available_employees': available, 'count': len(available), 'date': parsed_date.isoformat()}
        }

    def _tool_cancel_time_off(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel a time-off request"""
        employee_name = args.get('employee_name')
        date_str = args.get('date')
        confirmed = args.get('_confirmed', False)

        employee = self._find_employee_by_name(employee_name)
        if not employee:
            return {
                'success': False,
                'message': f"Could not find employee: {employee_name}",
                'data': None
            }

        parsed_date = self._parse_date(date_str)
        if not parsed_date:
            return {
                'success': False,
                'message': f"Could not parse date: {date_str}",
                'data': None
            }

        EmployeeTimeOff = self.models['EmployeeTimeOff']

        time_off = self.db.query(EmployeeTimeOff).filter(
            EmployeeTimeOff.employee_id == employee.id,
            EmployeeTimeOff.start_date <= parsed_date,
            EmployeeTimeOff.end_date >= parsed_date
        ).first()

        if not time_off:
            return {
                'success': False,
                'message': f"No time-off found for {employee.name} on {parsed_date.strftime('%B %d')}",
                'data': None
            }

        if not confirmed:
            return {
                'success': True,
                'message': f"⚠️ Confirm: Cancel time-off for {employee.name} ({time_off.start_date.strftime('%B %d')} to {time_off.end_date.strftime('%B %d')})?",
                'requires_confirmation': True,
                'confirmation_data': {
                    'tool_name': 'cancel_time_off',
                    'tool_args': args,
                    'action': f"Cancel time-off for {employee.name}"
                }
            }

        self.db.delete(time_off)
        self.db.commit()

        return {
            'success': True,
            'message': f"✅ Cancelled time-off for {employee.name} ({time_off.start_date.strftime('%B %d')} to {time_off.end_date.strftime('%B %d')})",
            'data': {
                'employee': employee.name,
                'start_date': time_off.start_date.isoformat(),
                'end_date': time_off.end_date.isoformat()
            }
        }

    def _tool_get_pending_time_off(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get all upcoming time-off requests"""
        days_ahead = args.get('days_ahead', 30)

        EmployeeTimeOff = self.models['EmployeeTimeOff']
        Employee = self.models['Employee']

        today = date.today()
        end_date = today + timedelta(days=days_ahead)

        time_off_records = self.db.query(EmployeeTimeOff, Employee).join(
            Employee, EmployeeTimeOff.employee_id == Employee.id
        ).filter(
            EmployeeTimeOff.end_date >= today,
            EmployeeTimeOff.start_date <= end_date
        ).order_by(EmployeeTimeOff.start_date).all()

        if not time_off_records:
            return {
                'success': True,
                'message': f"No upcoming time-off requests in the next {days_ahead} days.",
                'data': {'time_off': []}
            }

        time_off_list = []
        for time_off, emp in time_off_records:
            time_off_list.append({
                'employee': emp.name,
                'start_date': time_off.start_date.isoformat(),
                'end_date': time_off.end_date.isoformat(),
                'reason': time_off.reason or 'Not specified'
            })

        message = f"📅 Upcoming time-off (next {days_ahead} days):\n"
        for i, to in enumerate(time_off_list[:10], 1):
            start = datetime.strptime(to['start_date'], '%Y-%m-%d').strftime('%b %d')
            end = datetime.strptime(to['end_date'], '%Y-%m-%d').strftime('%b %d')
            message += f"{i}. {to['employee']}: {start} - {end}\n"

        if len(time_off_list) > 10:
            message += f"... and {len(time_off_list) - 10} more"

        return {
            'success': True,
            'message': message.strip(),
            'data': {'time_off': time_off_list, 'count': len(time_off_list)}
        }

    def _tool_get_event_details(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get details about a specific event"""
        event_name = args.get('event_name')
        event_id = args.get('event_id')

        Event = self.models['Event']
        Schedule = self.models['Schedule']
        Employee = self.models['Employee']

        if event_id:
            event = self.db.query(Event).filter(Event.id == event_id).first()
        elif event_name:
            event = self._find_event_by_name(event_name)
        else:
            return {
                'success': False,
                'message': "Please provide an event name or ID",
                'data': None
            }

        if not event:
            return {
                'success': False,
                'message': f"Could not find event: {event_name or event_id}",
                'data': None
            }

        # Get schedule if exists
        schedule_info = None
        schedule = self.db.query(Schedule, Employee).join(
            Employee, Schedule.employee_id == Employee.id
        ).filter(
            Schedule.event_ref_num == event.project_ref_num
        ).first()

        if schedule:
            sched, emp = schedule
            schedule_info = {
                'employee': emp.name,
                'scheduled_date': sched.schedule_datetime.strftime('%Y-%m-%d'),
                'scheduled_time': sched.schedule_datetime.strftime('%I:%M %p')
            }

        message = f"📋 Event Details:\n"
        message += f"Name: {event.project_name}\n"
        message += f"Type: {event.event_type}\n"
        message += f"Store: {event.store_name or 'N/A'}\n"
        message += f"Date Range: {event.start_datetime.strftime('%b %d')} - {event.due_datetime.strftime('%b %d')}\n"
        message += f"Status: {'Scheduled' if event.is_scheduled else 'Unscheduled'}\n"

        if schedule_info:
            message += f"\nAssigned to: {schedule_info['employee']}\n"
            message += f"Scheduled: {schedule_info['scheduled_date']} at {schedule_info['scheduled_time']}"

        return {
            'success': True,
            'message': message,
            'data': {
                'id': event.id,
                'name': event.project_name,
                'type': event.event_type,
                'store': event.store_name,
                'start_date': event.start_datetime.isoformat(),
                'due_date': event.due_datetime.isoformat(),
                'is_scheduled': event.is_scheduled,
                'schedule': schedule_info
            }
        }

    def _tool_assign_employee_to_event(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Assign an employee to an unscheduled event"""
        event_name = args.get('event_name')
        employee_name = args.get('employee_name')
        scheduled_date_str = args.get('scheduled_date')
        scheduled_time = args.get('scheduled_time')
        confirmed = args.get('_confirmed', False)

        # Find event
        event = self._find_event_by_name(event_name)
        if not event:
            return {
                'success': False,
                'message': f"Could not find event: {event_name}",
                'data': None
            }

        if event.is_scheduled:
            return {
                'success': False,
                'message': f"Event '{event.project_name}' is already scheduled. Use reschedule_event to change it.",
                'data': None
            }

        # Find employee
        employee = self._find_employee_by_name(employee_name)
        if not employee:
            return {
                'success': False,
                'message': f"Could not find employee: {employee_name}",
                'data': None
            }

        # Check if employee can work this event type
        if not employee.can_work_event_type(event.event_type):
            return {
                'success': False,
                'message': f"{employee.name} ({employee.job_title}) cannot work {event.event_type} events",
                'data': None
            }

        # Parse date
        scheduled_date = self._parse_date(scheduled_date_str)
        if not scheduled_date:
            return {
                'success': False,
                'message': f"Could not parse date: {scheduled_date_str}",
                'data': None
            }

        # Get default time if not specified
        if not scheduled_time:
            from app.services.event_time_settings import EventTimeSettings
            try:
                if event.event_type == 'Core':
                    slots = EventTimeSettings.get_core_slots()
                    if slots:
                        scheduled_time = f"{slots[0]['start'].hour:02d}:{slots[0]['start'].minute:02d}"
                elif event.event_type == 'Freeosk':
                    times = EventTimeSettings.get_freeosk_times()
                    scheduled_time = f"{times['start'].hour:02d}:{times['start'].minute:02d}"
                elif event.event_type == 'Supervisor':
                    times = EventTimeSettings.get_supervisor_times()
                    scheduled_time = f"{times['start'].hour:02d}:{times['start'].minute:02d}"
                else:
                    scheduled_time = '09:00'
            except Exception:
                scheduled_time = '09:00'

        if not confirmed:
            return {
                'success': True,
                'message': f"⚠️ Confirm: Assign {employee.name} to '{event.project_name}' ({event.event_type}) on {scheduled_date.strftime('%B %d')} at {scheduled_time}?",
                'requires_confirmation': True,
                'confirmation_data': {
                    'tool_name': 'assign_employee_to_event',
                    'tool_args': {
                        'event_name': event.project_name,
                        'employee_name': employee.name,
                        'scheduled_date': scheduled_date.isoformat(),
                        'scheduled_time': scheduled_time
                    },
                    'action': f"Assign {employee.name} to {event.project_name}"
                }
            }

        # Create schedule
        from datetime import datetime as dt
        Schedule = self.models['Schedule']

        time_parts = scheduled_time.split(':')
        schedule_datetime = dt.combine(
            scheduled_date,
            dt.strptime(scheduled_time, '%H:%M').time()
        )

        new_schedule = Schedule(
            event_ref_num=event.project_ref_num,
            employee_id=employee.id,
            schedule_datetime=schedule_datetime,
            last_synced=dt.utcnow(),
            sync_status='pending'
        )

        self.db.add(new_schedule)
        event.is_scheduled = True
        self.db.commit()

        return {
            'success': True,
            'message': f"✅ Assigned {employee.name} to '{event.project_name}' on {scheduled_date.strftime('%B %d')} at {scheduled_time}",
            'data': {
                'event': event.project_name,
                'employee': employee.name,
                'date': scheduled_date.isoformat(),
                'time': scheduled_time
            }
        }

    def _tool_unschedule_event(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Unschedule an event (remove employee assignment)"""
        employee_name = args.get('employee_name')
        date_str = args.get('date')
        event_type = args.get('event_type')
        confirmed = args.get('_confirmed', False)

        employee = self._find_employee_by_name(employee_name)
        if not employee:
            return {
                'success': False,
                'message': f"Could not find employee: {employee_name}",
                'data': None
            }

        parsed_date = self._parse_date(date_str)
        if not parsed_date:
            return {
                'success': False,
                'message': f"Could not parse date: {date_str}",
                'data': None
            }

        Schedule = self.models['Schedule']
        Event = self.models['Event']

        query = self.db.query(Schedule, Event).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            Schedule.employee_id == employee.id,
            func.date(Schedule.schedule_datetime) == parsed_date
        )

        if event_type:
            query = query.filter(Event.event_type == event_type)

        result = query.first()

        if not result:
            return {
                'success': False,
                'message': f"No scheduled event found for {employee.name} on {parsed_date.strftime('%B %d')}",
                'data': None
            }

        schedule, event = result

        if not confirmed:
            return {
                'success': True,
                'message': f"⚠️ Confirm: Unschedule {employee.name} from '{event.project_name}' ({event.event_type}) on {parsed_date.strftime('%B %d')}?",
                'requires_confirmation': True,
                'confirmation_data': {
                    'tool_name': 'unschedule_event',
                    'tool_args': args,
                    'action': f"Unschedule {employee.name} from {event.project_name}"
                }
            }

        self.db.delete(schedule)
        event.is_scheduled = False
        self.db.commit()

        return {
            'success': True,
            'message': f"✅ Unscheduled {employee.name} from '{event.project_name}'. The event is now available for scheduling.",
            'data': {
                'event': event.project_name,
                'employee': employee.name,
                'date': parsed_date.isoformat()
            }
        }

    def _tool_check_scheduling_conflicts(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Check for potential scheduling conflicts"""
        employee_name = args.get('employee_name')
        date_str = args.get('date')
        event_type = args.get('event_type')

        employee = self._find_employee_by_name(employee_name)
        if not employee:
            return {
                'success': False,
                'message': f"Could not find employee: {employee_name}",
                'data': None
            }

        parsed_date = self._parse_date(date_str)
        if not parsed_date:
            return {
                'success': False,
                'message': f"Could not parse date: {date_str}",
                'data': None
            }

        conflicts = []

        # Check time off
        EmployeeTimeOff = self.models['EmployeeTimeOff']
        time_off = self.db.query(EmployeeTimeOff).filter(
            EmployeeTimeOff.employee_id == employee.id,
            EmployeeTimeOff.start_date <= parsed_date,
            EmployeeTimeOff.end_date >= parsed_date
        ).first()

        if time_off:
            conflicts.append(f"❌ {employee.name} has time-off on {parsed_date.strftime('%B %d')}")

        # Check role restrictions
        if event_type and not employee.can_work_event_type(event_type):
            conflicts.append(f"❌ {employee.name} ({employee.job_title}) cannot work {event_type} events")

        # Check Core event limit
        if event_type == 'Core':
            Schedule = self.models['Schedule']
            Event = self.models['Event']

            existing_core = self.db.query(Schedule).join(
                Event, Schedule.event_ref_num == Event.project_ref_num
            ).filter(
                Schedule.employee_id == employee.id,
                func.date(Schedule.schedule_datetime) == parsed_date,
                Event.event_type == 'Core'
            ).first()

            if existing_core:
                conflicts.append(f"❌ {employee.name} is already scheduled for a Core event on {parsed_date.strftime('%B %d')}")

        if conflicts:
            return {
                'success': True,
                'message': f"⚠️ Conflicts found for scheduling {employee.name} on {parsed_date.strftime('%B %d')}:\n" + "\n".join(conflicts),
                'data': {'has_conflicts': True, 'conflicts': conflicts}
            }

        return {
            'success': True,
            'message': f"✅ No conflicts! {employee.name} can be scheduled for {event_type or 'an event'} on {parsed_date.strftime('%B %d')}.",
            'data': {'has_conflicts': False, 'conflicts': []}
        }

    # ===== EMERGENCY & COVERAGE TOOLS =====

    def _tool_find_replacement(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Find replacement employees for a callout"""
        employee_name = args.get('employee_name')
        date_str = args.get('date')
        event_type = args.get('event_type')

        # Find the employee who needs replacement
        employee = self._find_employee_by_name(employee_name)
        if not employee:
            return {
                'success': False,
                'message': f"Could not find employee: {employee_name}",
                'data': None
            }

        parsed_date = self._parse_date(date_str)
        if not parsed_date:
            return {
                'success': False,
                'message': f"Could not parse date: {date_str}",
                'data': None
            }

        Schedule = self.models['Schedule']
        Event = self.models['Event']
        Employee = self.models['Employee']
        EmployeeTimeOff = self.models['EmployeeTimeOff']

        # Get the employee's scheduled event(s) for that date
        employee_schedules = self.db.query(Schedule, Event).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            Schedule.employee_id == employee.id,
            func.date(Schedule.schedule_datetime) == parsed_date
        ).all()

        if not employee_schedules:
            return {
                'success': True,
                'message': f"{employee.name} has no scheduled events on {parsed_date.strftime('%B %d')} to cover.",
                'data': {'replacements': []}
            }

        # Determine event type from scheduled event if not provided
        if not event_type and employee_schedules:
            event_type = employee_schedules[0][1].event_type

        # Get all active employees except the one being replaced
        all_employees = self.db.query(Employee).filter(
            Employee.is_active == True,
            Employee.id != employee.id
        ).all()

        # Get employees on time off
        time_off_ids = set()
        time_off_records = self.db.query(EmployeeTimeOff.employee_id).filter(
            EmployeeTimeOff.start_date <= parsed_date,
            EmployeeTimeOff.end_date >= parsed_date
        ).all()
        time_off_ids = {r[0] for r in time_off_records}

        # Get employees already scheduled that day (for Core limit check)
        already_scheduled = {}
        day_schedules = self.db.query(Schedule.employee_id, Event.event_type).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            func.date(Schedule.schedule_datetime) == parsed_date
        ).all()
        for emp_id, evt_type in day_schedules:
            if emp_id not in already_scheduled:
                already_scheduled[emp_id] = []
            already_scheduled[emp_id].append(evt_type)

        # Score and rank replacements
        replacements = []
        for emp in all_employees:
            score = 100
            issues = []

            # Check time off
            if emp.id in time_off_ids:
                score -= 100
                issues.append("Has time off")

            # Check role qualification
            if event_type and not emp.can_work_event_type(event_type):
                score -= 100
                issues.append(f"Not qualified for {event_type}")

            # Check Core event limit
            if event_type == 'Core' and 'Core' in already_scheduled.get(emp.id, []):
                score -= 100
                issues.append("Already has Core event")

            # Prefer same job title
            if emp.job_title == employee.job_title:
                score += 20

            # Prefer those not already working that day
            if emp.id not in already_scheduled:
                score += 10

            if score > 0:
                replacements.append({
                    'employee_id': emp.id,
                    'name': emp.name,
                    'job_title': emp.job_title,
                    'score': score,
                    'issues': issues,
                    'already_working': emp.id in already_scheduled
                })

        # Sort by score
        replacements.sort(key=lambda x: x['score'], reverse=True)

        if not replacements:
            return {
                'success': True,
                'message': f"⚠️ No available replacements found for {employee.name}'s {event_type or 'event'} on {parsed_date.strftime('%B %d')}. Everyone is either unavailable, unqualified, or already working.",
                'data': {'replacements': [], 'event_type': event_type}
            }

        # Build message
        message = f"📞 **Replacement options for {employee.name}** ({event_type or 'event'} on {parsed_date.strftime('%B %d')}):\n\n"

        for i, rep in enumerate(replacements[:8], 1):
            status = "✅" if rep['score'] >= 100 else "⚠️"
            already = " (already working)" if rep['already_working'] else ""
            message += f"{i}. {status} **{rep['name']}** ({rep['job_title']}){already}\n"

        if len(replacements) > 8:
            message += f"\n... and {len(replacements) - 8} more options"

        message += "\n\n💡 *Top recommendations are listed first based on availability and qualifications.*"

        return {
            'success': True,
            'message': message,
            'data': {
                'replacements': replacements[:10],
                'original_employee': employee.name,
                'date': parsed_date.isoformat(),
                'event_type': event_type
            }
        }

    def _tool_get_employee_schedule(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get schedule for a specific employee"""
        employee_name = args.get('employee_name')
        date_range = args.get('date_range', 'this week')

        employee = self._find_employee_by_name(employee_name)
        if not employee:
            return {
                'success': False,
                'message': f"Could not find employee: {employee_name}",
                'data': None
            }

        start_date, end_date = self._parse_date_range(date_range)
        if not start_date:
            # Default to this week
            today = date.today()
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)

        Schedule = self.models['Schedule']
        Event = self.models['Event']

        schedules = self.db.query(Schedule, Event).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            Schedule.employee_id == employee.id,
            func.date(Schedule.schedule_datetime) >= start_date,
            func.date(Schedule.schedule_datetime) <= end_date
        ).order_by(Schedule.schedule_datetime).all()

        if not schedules:
            return {
                'success': True,
                'message': f"📅 {employee.name} has no events scheduled for {date_range}.",
                'data': {'employee': employee.name, 'schedules': [], 'date_range': date_range}
            }

        # Group by date
        from collections import defaultdict
        by_date = defaultdict(list)
        for sched, event in schedules:
            day = sched.schedule_datetime.date()
            by_date[day].append({
                'time': sched.schedule_datetime.strftime('%I:%M %p'),
                'event': event.project_name,
                'type': event.event_type,
                'store': event.store_name
            })

        message = f"📅 **{employee.name}'s Schedule** ({date_range}):\n\n"

        for day in sorted(by_date.keys()):
            day_name = day.strftime('%A, %b %d')
            message += f"**{day_name}:**\n"
            for item in by_date[day]:
                message += f"  • {item['time']} - {item['type']}"
                if item['store']:
                    message += f" @ {item['store']}"
                message += "\n"

        message += f"\n📊 Total: {len(schedules)} event(s) over {len(by_date)} day(s)"

        # Count days worked for week limit check
        days_worked = len(by_date)
        if days_worked >= 5:
            message += f"\n⚠️ Working {days_worked}/6 max days this period"

        return {
            'success': True,
            'message': message,
            'data': {
                'employee': employee.name,
                'schedules': [{'date': d.isoformat(), 'events': e} for d, e in by_date.items()],
                'total_events': len(schedules),
                'days_worked': days_worked
            }
        }

    def _tool_swap_shifts(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Swap shifts between two employees"""
        employee1_name = args.get('employee1_name')
        employee2_name = args.get('employee2_name')
        date_str = args.get('date')
        event_type = args.get('event_type')
        confirmed = args.get('_confirmed', False)

        employee1 = self._find_employee_by_name(employee1_name)
        employee2 = self._find_employee_by_name(employee2_name)

        if not employee1:
            return {'success': False, 'message': f"Could not find employee: {employee1_name}", 'data': None}
        if not employee2:
            return {'success': False, 'message': f"Could not find employee: {employee2_name}", 'data': None}

        parsed_date = self._parse_date(date_str)
        if not parsed_date:
            return {'success': False, 'message': f"Could not parse date: {date_str}", 'data': None}

        Schedule = self.models['Schedule']
        Event = self.models['Event']

        # Find schedules for both employees
        query1 = self.db.query(Schedule, Event).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            Schedule.employee_id == employee1.id,
            func.date(Schedule.schedule_datetime) == parsed_date
        )
        query2 = self.db.query(Schedule, Event).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            Schedule.employee_id == employee2.id,
            func.date(Schedule.schedule_datetime) == parsed_date
        )

        if event_type:
            query1 = query1.filter(Event.event_type == event_type)
            query2 = query2.filter(Event.event_type == event_type)

        sched1 = query1.first()
        sched2 = query2.first()

        if not sched1:
            return {'success': False, 'message': f"{employee1.name} has no {event_type or ''} event on {parsed_date.strftime('%B %d')}", 'data': None}
        if not sched2:
            return {'success': False, 'message': f"{employee2.name} has no {event_type or ''} event on {parsed_date.strftime('%B %d')}", 'data': None}

        schedule1, event1 = sched1
        schedule2, event2 = sched2

        # Check if swap is valid (role requirements)
        issues = []
        if not employee1.can_work_event_type(event2.event_type):
            issues.append(f"{employee1.name} cannot work {event2.event_type} events")
        if not employee2.can_work_event_type(event1.event_type):
            issues.append(f"{employee2.name} cannot work {event1.event_type} events")

        if issues:
            return {
                'success': False,
                'message': f"❌ Cannot swap shifts:\n" + "\n".join(f"• {i}" for i in issues),
                'data': {'issues': issues}
            }

        if not confirmed:
            return {
                'success': True,
                'message': f"⚠️ **Confirm shift swap on {parsed_date.strftime('%B %d')}:**\n\n" +
                          f"• {employee1.name}: {event1.event_type} → {event2.event_type}\n" +
                          f"• {employee2.name}: {event2.event_type} → {event1.event_type}",
                'requires_confirmation': True,
                'confirmation_data': {
                    'tool_name': 'swap_shifts',
                    'tool_args': args,
                    'action': f"Swap shifts between {employee1.name} and {employee2.name}"
                }
            }

        # Perform the swap
        schedule1.employee_id = employee2.id
        schedule2.employee_id = employee1.id
        self.db.commit()

        return {
            'success': True,
            'message': f"✅ Successfully swapped shifts on {parsed_date.strftime('%B %d')}:\n" +
                      f"• {employee1.name} now has: {event2.event_type}\n" +
                      f"• {employee2.name} now has: {event1.event_type}",
            'data': {
                'date': parsed_date.isoformat(),
                'employee1': {'name': employee1.name, 'new_event': event2.event_type},
                'employee2': {'name': employee2.name, 'new_event': event1.event_type}
            }
        }

    # ===== WORKLOAD & ANALYTICS TOOLS =====

    def _tool_get_workload_summary(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get workload summary for employees"""
        date_range = args.get('date_range', 'this week')
        sort_by = args.get('sort_by', 'most')

        start_date, end_date = self._parse_date_range(date_range)
        if not start_date:
            today = date.today()
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)

        Schedule = self.models['Schedule']
        Event = self.models['Event']
        Employee = self.models['Employee']

        # Get all active employees
        employees = self.db.query(Employee).filter(Employee.is_active == True).all()

        workload = []
        for emp in employees:
            schedules = self.db.query(Schedule, Event).join(
                Event, Schedule.event_ref_num == Event.project_ref_num
            ).filter(
                Schedule.employee_id == emp.id,
                func.date(Schedule.schedule_datetime) >= start_date,
                func.date(Schedule.schedule_datetime) <= end_date
            ).all()

            event_count = len(schedules)
            days_worked = len(set(s.schedule_datetime.date() for s, e in schedules))
            total_hours = sum((e.estimated_time or e.get_default_duration(e.event_type)) / 60 for s, e in schedules)

            workload.append({
                'employee_id': emp.id,
                'name': emp.name,
                'job_title': emp.job_title,
                'event_count': event_count,
                'days_worked': days_worked,
                'hours': round(total_hours, 1)
            })

        # Sort
        if sort_by == 'least':
            workload.sort(key=lambda x: x['event_count'])
        else:
            workload.sort(key=lambda x: x['event_count'], reverse=True)

        message = f"📊 **Workload Summary** ({date_range}):\n\n"

        # Categorize
        high_workload = [w for w in workload if w['days_worked'] >= 5]
        low_workload = [w for w in workload if w['event_count'] == 0]

        if high_workload:
            message += "**🔴 High Workload (5+ days):**\n"
            for w in high_workload[:5]:
                message += f"  • {w['name']}: {w['event_count']} events, {w['days_worked']} days\n"

        if low_workload:
            message += "\n**🟢 Available (no events):**\n"
            for w in low_workload[:5]:
                message += f"  • {w['name']} ({w['job_title']})\n"

        message += "\n**📋 Full List:**\n"
        for i, w in enumerate(workload[:10], 1):
            status = "🔴" if w['days_worked'] >= 5 else "🟡" if w['days_worked'] >= 3 else "🟢"
            message += f"{i}. {status} {w['name']}: {w['event_count']} events ({w['days_worked']} days, ~{w['hours']}h)\n"

        return {
            'success': True,
            'message': message,
            'data': {
                'workload': workload,
                'date_range': {'start': start_date.isoformat(), 'end': end_date.isoformat()},
                'high_workload_count': len(high_workload),
                'available_count': len(low_workload)
            }
        }

    def _tool_check_overtime_risk(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Check for employees at risk of overtime"""
        week_of_str = args.get('week_of')

        if week_of_str:
            week_of = self._parse_date(week_of_str)
        else:
            week_of = date.today()

        # Get week boundaries (Sunday to Saturday)
        days_since_sunday = (week_of.weekday() + 1) % 7
        week_start = week_of - timedelta(days=days_since_sunday)
        week_end = week_start + timedelta(days=6)

        Schedule = self.models['Schedule']
        Employee = self.models['Employee']

        employees = self.db.query(Employee).filter(Employee.is_active == True).all()

        at_risk = []
        for emp in employees:
            days_worked = self.db.query(
                func.date(Schedule.schedule_datetime)
            ).filter(
                Schedule.employee_id == emp.id,
                func.date(Schedule.schedule_datetime) >= week_start,
                func.date(Schedule.schedule_datetime) <= week_end
            ).distinct().count()

            if days_worked >= 5:
                at_risk.append({
                    'employee_id': emp.id,
                    'name': emp.name,
                    'days_worked': days_worked,
                    'status': 'exceeded' if days_worked > 6 else 'at_limit' if days_worked == 6 else 'approaching'
                })

        at_risk.sort(key=lambda x: x['days_worked'], reverse=True)

        if not at_risk:
            return {
                'success': True,
                'message': f"✅ No overtime risks for the week of {week_start.strftime('%B %d')}. All employees are under 5 days.",
                'data': {'at_risk': [], 'week_start': week_start.isoformat()}
            }

        message = f"⚠️ **Overtime Risk Report** (Week of {week_start.strftime('%B %d')}):\n\n"

        exceeded = [e for e in at_risk if e['status'] == 'exceeded']
        at_limit = [e for e in at_risk if e['status'] == 'at_limit']
        approaching = [e for e in at_risk if e['status'] == 'approaching']

        if exceeded:
            message += "**🔴 EXCEEDED (>6 days):**\n"
            for e in exceeded:
                message += f"  • {e['name']}: {e['days_worked']} days ❌\n"

        if at_limit:
            message += "\n**🟠 AT LIMIT (6 days):**\n"
            for e in at_limit:
                message += f"  • {e['name']}: {e['days_worked']} days\n"

        if approaching:
            message += "\n**🟡 APPROACHING (5 days):**\n"
            for e in approaching:
                message += f"  • {e['name']}: {e['days_worked']} days\n"

        message += f"\n💡 *Maximum is 6 work days per week (Sun-Sat). Found {len(at_risk)} employee(s) at risk.*"

        return {
            'success': True,
            'message': message,
            'data': {
                'at_risk': at_risk,
                'week_start': week_start.isoformat(),
                'week_end': week_end.isoformat(),
                'exceeded_count': len(exceeded),
                'at_limit_count': len(at_limit),
                'approaching_count': len(approaching)
            }
        }

    # ===== ROTATION & COVERAGE TOOLS =====

    def _tool_get_rotation_schedule(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get rotation assignments"""
        rotation_type = args.get('rotation_type', 'all')
        week_of_str = args.get('week_of')

        RotationAssignment = self.models.get('RotationAssignment')
        ScheduleException = self.models.get('ScheduleException')
        Employee = self.models['Employee']

        if not RotationAssignment:
            return {
                'success': False,
                'message': "Rotation assignments are not configured in this system.",
                'data': None
            }

        if week_of_str:
            week_of = self._parse_date(week_of_str)
        else:
            week_of = date.today()

        days_since_sunday = (week_of.weekday() + 1) % 7
        week_start = week_of - timedelta(days=days_since_sunday)

        day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

        # Get rotations
        query = self.db.query(RotationAssignment, Employee).outerjoin(
            Employee, RotationAssignment.employee_id == Employee.id
        )
        if rotation_type != 'all':
            query = query.filter(RotationAssignment.rotation_type == rotation_type)

        rotations = query.order_by(RotationAssignment.day_of_week).all()

        # Build schedule
        schedule = {'juicer': {}, 'primary_lead': {}}
        for rot, emp in rotations:
            emp_name = emp.name if emp else 'Unassigned'
            schedule[rot.rotation_type][rot.day_of_week] = emp_name

        message = f"📅 **Rotation Schedule** (Week of {week_start.strftime('%B %d')}):\n\n"

        if rotation_type in ['all', 'juicer']:
            message += "**🧃 Juicer Rotation:**\n"
            for i, day in enumerate(day_names):
                emp = schedule['juicer'].get(i, 'Not set')
                message += f"  • {day}: {emp}\n"

        if rotation_type in ['all', 'primary_lead']:
            message += "\n**⭐ Primary Lead Rotation:**\n"
            for i, day in enumerate(day_names):
                emp = schedule['primary_lead'].get(i, 'Not set')
                message += f"  • {day}: {emp}\n"

        return {
            'success': True,
            'message': message,
            'data': {
                'schedule': schedule,
                'week_start': week_start.isoformat()
            }
        }

    def _tool_check_lead_coverage(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Check Lead Event Specialist coverage for opening/closing"""
        date_str = args.get('date')

        parsed_date = self._parse_date(date_str)
        if not parsed_date:
            return {'success': False, 'message': f"Could not parse date: {date_str}", 'data': None}

        Schedule = self.models['Schedule']
        Event = self.models['Event']
        Employee = self.models['Employee']

        # Get all Lead Event Specialists with Core events
        lead_schedules = self.db.query(Schedule, Event, Employee).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).join(
            Employee, Schedule.employee_id == Employee.id
        ).filter(
            func.date(Schedule.schedule_datetime) == parsed_date,
            Event.event_type == 'Core',
            Employee.job_title == 'Lead Event Specialist'
        ).order_by(Schedule.schedule_datetime).all()

        # Get all Core event times
        all_core = self.db.query(Schedule.schedule_datetime).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            func.date(Schedule.schedule_datetime) == parsed_date,
            Event.event_type == 'Core'
        ).order_by(Schedule.schedule_datetime).all()

        if not all_core:
            return {
                'success': True,
                'message': f"ℹ️ No Core events scheduled for {parsed_date.strftime('%B %d')} - no Lead coverage needed.",
                'data': {'has_opening': None, 'has_closing': None}
            }

        earliest_time = all_core[0][0].time()
        latest_time = all_core[-1][0].time()
        lead_times = [s.schedule_datetime.time() for s, e, emp in lead_schedules]

        has_opening = earliest_time in lead_times
        has_closing = latest_time in lead_times

        message = f"👥 **Lead Coverage for {parsed_date.strftime('%A, %B %d')}:**\n\n"

        # Opening
        if has_opening:
            opener = next((emp.name for s, e, emp in lead_schedules if s.schedule_datetime.time() == earliest_time), None)
            message += f"✅ **Opening ({earliest_time.strftime('%I:%M %p')}):** {opener}\n"
        else:
            message += f"❌ **Opening ({earliest_time.strftime('%I:%M %p')}):** No Lead scheduled\n"

        # Closing
        if has_closing:
            closer = next((emp.name for s, e, emp in lead_schedules if s.schedule_datetime.time() == latest_time), None)
            message += f"✅ **Closing ({latest_time.strftime('%I:%M %p')}):** {closer}\n"
        else:
            message += f"❌ **Closing ({latest_time.strftime('%I:%M %p')}):** No Lead scheduled\n"

        # List all Leads working
        if lead_schedules:
            message += f"\n**Leads scheduled:** {', '.join(set(emp.name for s, e, emp in lead_schedules))}"

        if not has_opening or not has_closing:
            message += "\n\n💡 *Consider swapping shifts to ensure Lead coverage at opening and closing.*"

        return {
            'success': True,
            'message': message,
            'data': {
                'date': parsed_date.isoformat(),
                'has_opening': has_opening,
                'has_closing': has_closing,
                'opening_time': earliest_time.strftime('%H:%M'),
                'closing_time': latest_time.strftime('%H:%M'),
                'leads_scheduled': [emp.name for s, e, emp in lead_schedules]
            }
        }

    def _tool_get_urgent_events(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get events due soon but not scheduled"""
        days_ahead = args.get('days_ahead', 7)

        today = date.today()
        end_date = today + timedelta(days=days_ahead)

        Event = self.models['Event']

        # Events due within range that aren't scheduled
        urgent = self.db.query(Event).filter(
            Event.is_scheduled == False,
            Event.due_datetime >= datetime.combine(today, datetime.min.time()),
            Event.due_datetime <= datetime.combine(end_date, datetime.max.time()),
            Event.condition != 'Canceled'
        ).order_by(Event.due_datetime).all()

        if not urgent:
            return {
                'success': True,
                'message': f"✅ No urgent unscheduled events in the next {days_ahead} days.",
                'data': {'urgent_events': []}
            }

        message = f"🚨 **Urgent Events** (due within {days_ahead} days):\n\n"

        events_list = []
        for event in urgent:
            days_until_due = (event.due_datetime.date() - today).days
            urgency = "🔴" if days_until_due <= 1 else "🟠" if days_until_due <= 3 else "🟡"

            events_list.append({
                'id': event.id,
                'ref_num': event.project_ref_num,
                'name': event.project_name,
                'type': event.event_type,
                'due_date': event.due_datetime.date().isoformat(),
                'days_until_due': days_until_due
            })

            message += f"{urgency} **{event.project_name}**\n"
            message += f"   Type: {event.event_type} | Due: {event.due_datetime.strftime('%b %d')} ({days_until_due} days)\n"

        message += f"\n📊 Total: {len(urgent)} event(s) need scheduling"

        return {
            'success': True,
            'message': message,
            'data': {'urgent_events': events_list, 'days_ahead': days_ahead}
        }

    # ===== COMPANY & SYSTEM TOOLS =====

    def _tool_check_company_holidays(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Check company holidays"""
        date_str = args.get('date')
        days_ahead = args.get('days_ahead', 30)

        CompanyHoliday = self.models.get('CompanyHoliday')
        if not CompanyHoliday:
            return {
                'success': True,
                'message': "ℹ️ Company holidays are not configured in this system.",
                'data': {'holidays': []}
            }

        if date_str:
            # Check specific date
            check_date = self._parse_date(date_str)
            if not check_date:
                return {'success': False, 'message': f"Could not parse date: {date_str}", 'data': None}

            holiday = self.db.query(CompanyHoliday).filter(
                CompanyHoliday.holiday_date == check_date,
                CompanyHoliday.is_active == True
            ).first()

            if holiday:
                return {
                    'success': True,
                    'message': f"🎉 **{check_date.strftime('%A, %B %d')}** is **{holiday.name}** - company closed.",
                    'data': {'is_holiday': True, 'holiday_name': holiday.name, 'date': check_date.isoformat()}
                }
            else:
                return {
                    'success': True,
                    'message': f"✅ {check_date.strftime('%A, %B %d')} is a regular work day.",
                    'data': {'is_holiday': False, 'date': check_date.isoformat()}
                }
        else:
            # List upcoming holidays
            today = date.today()
            end_date = today + timedelta(days=days_ahead)

            holidays = self.db.query(CompanyHoliday).filter(
                CompanyHoliday.holiday_date >= today,
                CompanyHoliday.holiday_date <= end_date,
                CompanyHoliday.is_active == True
            ).order_by(CompanyHoliday.holiday_date).all()

            if not holidays:
                return {
                    'success': True,
                    'message': f"ℹ️ No company holidays in the next {days_ahead} days.",
                    'data': {'holidays': []}
                }

            message = f"🗓️ **Upcoming Company Holidays** (next {days_ahead} days):\n\n"
            holiday_list = []
            for h in holidays:
                days_until = (h.holiday_date - today).days
                message += f"• **{h.name}** - {h.holiday_date.strftime('%A, %B %d')} ({days_until} days)\n"
                holiday_list.append({
                    'name': h.name,
                    'date': h.holiday_date.isoformat(),
                    'days_until': days_until
                })

            return {
                'success': True,
                'message': message,
                'data': {'holidays': holiday_list}
            }

    def _tool_get_daily_roster(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get complete daily roster"""
        date_str = args.get('date', 'today')

        parsed_date = self._parse_date(date_str) if date_str != 'today' else date.today()
        if not parsed_date:
            parsed_date = date.today()

        Schedule = self.models['Schedule']
        Event = self.models['Event']
        Employee = self.models['Employee']

        # Get all schedules for the day
        schedules = self.db.query(Schedule, Event, Employee).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).join(
            Employee, Schedule.employee_id == Employee.id
        ).filter(
            func.date(Schedule.schedule_datetime) == parsed_date
        ).order_by(Schedule.schedule_datetime, Employee.name).all()

        if not schedules:
            return {
                'success': True,
                'message': f"📋 No events scheduled for {parsed_date.strftime('%A, %B %d')}.",
                'data': {'roster': [], 'date': parsed_date.isoformat()}
            }

        # Build roster
        from collections import defaultdict
        by_employee = defaultdict(list)
        by_time = defaultdict(list)

        for sched, event, emp in schedules:
            time_str = sched.schedule_datetime.strftime('%I:%M %p')
            by_employee[emp.name].append({
                'time': time_str,
                'event': event.project_name,
                'type': event.event_type
            })
            by_time[time_str].append({
                'employee': emp.name,
                'job_title': emp.job_title,
                'event_type': event.event_type
            })

        message = f"📋 **Daily Roster - {parsed_date.strftime('%A, %B %d, %Y')}**\n\n"

        # Summary
        unique_employees = len(by_employee)
        total_events = len(schedules)
        message += f"**Summary:** {unique_employees} employees, {total_events} events\n\n"

        # By Time Slot
        message += "**By Time:**\n"
        for time_str in sorted(by_time.keys()):
            people = by_time[time_str]
            message += f"  **{time_str}:** "
            message += ", ".join(f"{p['employee']} ({p['event_type']})" for p in people)
            message += "\n"

        # By Employee
        message += "\n**By Employee:**\n"
        for emp_name in sorted(by_employee.keys()):
            events = by_employee[emp_name]
            message += f"  • **{emp_name}:** "
            message += ", ".join(f"{e['time']} {e['type']}" for e in events)
            message += "\n"

        # Run verification
        from app.services.schedule_verification import ScheduleVerificationService
        service = ScheduleVerificationService(self.db, self.models)
        verification = service.verify_schedule(parsed_date)

        if verification.issues:
            message += f"\n⚠️ **Issues Found:** {len(verification.issues)}\n"
            for issue in verification.issues[:3]:
                icon = "❌" if issue.severity == 'critical' else "⚠️"
                message += f"  {icon} {issue.message}\n"

        return {
            'success': True,
            'message': message,
            'data': {
                'date': parsed_date.isoformat(),
                'employee_count': unique_employees,
                'event_count': total_events,
                'roster': dict(by_employee),
                'by_time': dict(by_time),
                'issues': len(verification.issues) if verification.issues else 0
            }
        }

    def _tool_get_scheduling_rules(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get scheduling rules and constraints"""
        topic = args.get('topic', 'all')

        rules = {}

        # Role requirements
        rules['roles'] = {
            'Club Supervisor': {
                'can_work': ['Core', 'Juicer', 'Supervisor', 'Freeosk', 'Digitals', 'Other'],
                'description': 'Can work all event types including Juicer'
            },
            'Lead Event Specialist': {
                'can_work': ['Core', 'Supervisor', 'Freeosk', 'Digitals', 'Other'],
                'description': 'Can work most events except Juicer'
            },
            'Event Specialist': {
                'can_work': ['Core', 'Freeosk', 'Digitals', 'Other'],
                'description': 'Standard events only'
            },
            'Juicer Barista': {
                'can_work': ['Juicer'],
                'description': 'Juicer events only'
            }
        }

        # Event types
        rules['event_types'] = {
            'Core': {'duration': '6.5 hours', 'max_per_day': 1, 'roles': 'Any employee'},
            'Juicer': {'duration': '9 hours', 'roles': 'Club Supervisor or Juicer Barista only'},
            'Supervisor': {'duration': '5 min', 'time': '12:00 PM', 'roles': 'Club Supervisor or Lead'},
            'Freeosk': {'duration': '15 min', 'roles': 'Club Supervisor or Lead'},
            'Digitals': {'duration': '15 min', 'roles': 'Club Supervisor or Lead'}
        }

        # Constraints
        rules['constraints'] = [
            {'rule': 'Max 1 Core event per employee per day', 'severity': 'HARD'},
            {'rule': 'Max 6 work days per week (Sunday-Saturday)', 'severity': 'HARD'},
            {'rule': 'Cannot schedule during approved time-off', 'severity': 'HARD'},
            {'rule': 'Cannot schedule on company holidays', 'severity': 'HARD'},
            {'rule': 'Employee must be qualified for event type', 'severity': 'HARD'},
            {'rule': 'Event must be scheduled within its date range', 'severity': 'HARD'},
            {'rule': 'Lead coverage needed for opening/closing shifts', 'severity': 'SOFT'},
            {'rule': 'Shifts should be balanced across time slots', 'severity': 'SOFT'}
        ]

        # Time slots
        from app.services.event_time_settings import get_core_slots, get_supervisor_times
        try:
            core_slots = get_core_slots()
            rules['time_slots'] = {
                'core_slots': [f"{s['start'].strftime('%I:%M %p')}" for s in core_slots],
                'supervisor_time': get_supervisor_times()['start'].strftime('%I:%M %p')
            }
        except Exception:
            rules['time_slots'] = {
                'core_slots': ['9:45 AM', '10:30 AM', '11:00 AM', '11:30 AM'],
                'supervisor_time': '12:00 PM'
            }

        # Build message based on topic
        message = "📚 **Scheduling Rules & Constraints**\n\n"

        if topic in ['all', 'roles']:
            message += "**👥 Role Requirements:**\n"
            for role, info in rules['roles'].items():
                message += f"• **{role}:** {info['description']}\n"
                message += f"  Can work: {', '.join(info['can_work'])}\n"

        if topic in ['all', 'event_types']:
            message += "\n**📋 Event Types:**\n"
            for etype, info in rules['event_types'].items():
                message += f"• **{etype}:** {info['duration']}"
                if 'time' in info:
                    message += f" at {info['time']}"
                if 'max_per_day' in info:
                    message += f" (max {info['max_per_day']}/day)"
                message += f"\n  Roles: {info['roles']}\n"

        if topic in ['all', 'constraints']:
            message += "\n**⚖️ Constraints:**\n"
            for c in rules['constraints']:
                icon = "🔴" if c['severity'] == 'HARD' else "🟡"
                message += f"{icon} {c['rule']}\n"

        if topic in ['all', 'time_slots']:
            message += "\n**⏰ Time Slots:**\n"
            message += f"• Core Events: {', '.join(rules['time_slots']['core_slots'])}\n"
            message += f"• Supervisor Events: {rules['time_slots']['supervisor_time']}\n"

        return {
            'success': True,
            'message': message,
            'data': rules
        }

    def _tool_refresh_database(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Refresh local database from external API"""
        sync_type = args.get('sync_type', 'schedules')

        try:
            from flask import current_app
            from app.integrations.external_api.sync_engine import SyncEngine

            # Check if sync is enabled
            if not current_app.config.get('SYNC_ENABLED', False):
                return {
                    'success': True,
                    'message': "🔄 Sync is disabled in configuration. Using local database data (which is current).",
                    'data': {'sync_enabled': False}
                }

            sync_engine = SyncEngine(current_app, self.db)

            results = {}
            message = "🔄 **Database Refresh Results:**\n\n"

            if sync_type in ['all', 'schedules']:
                schedule_result = sync_engine.sync_schedules()
                results['schedules'] = schedule_result
                message += f"📅 Schedules: {schedule_result.get('synced', 0)} synced, {schedule_result.get('errors', 0)} errors\n"

            if sync_type in ['all', 'events']:
                event_result = sync_engine.sync_events()
                results['events'] = event_result
                message += f"📋 Events: {event_result.get('synced', 0)} synced, {event_result.get('errors', 0)} errors\n"

            if sync_type in ['all', 'employees']:
                employee_result = sync_engine.sync_employees()
                results['employees'] = employee_result
                message += f"👥 Employees: {employee_result.get('synced', 0)} synced, {employee_result.get('errors', 0)} errors\n"

            # Expire all cached objects to force fresh reads
            self.db.expire_all()

            message += "\n✅ Database refreshed. Now using latest data from external system."

            return {
                'success': True,
                'message': message,
                'data': results
            }

        except Exception as e:
            logger.error(f"Error refreshing database: {str(e)}", exc_info=True)
            # Even on error, expire cache to force fresh local reads
            try:
                self.db.expire_all()
            except Exception:
                pass

            return {
                'success': False,
                'message': f"⚠️ Could not sync with external API: {str(e)}. Using local database data.",
                'data': {'error': str(e)}
            }

    # ===== BULK OPERATIONS =====

    def _tool_bulk_reschedule_day(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Move all events from one date to another"""
        from_date_str = args.get('from_date')
        to_date_str = args.get('to_date')
        reason = args.get('reason', 'bulk reschedule')
        confirmed = args.get('_confirmed', False)

        from_date = self._parse_date(from_date_str)
        to_date = self._parse_date(to_date_str)

        if not from_date:
            return {'success': False, 'message': f"Could not parse from_date: {from_date_str}", 'data': None}
        if not to_date:
            return {'success': False, 'message': f"Could not parse to_date: {to_date_str}", 'data': None}

        if from_date == to_date:
            return {'success': False, 'message': "From and to dates are the same", 'data': None}

        Schedule = self.models['Schedule']
        Event = self.models['Event']

        # Find all schedules on the from_date
        schedules = self.db.query(Schedule, Event).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            func.date(Schedule.schedule_datetime) == from_date
        ).all()

        if not schedules:
            return {
                'success': True,
                'message': f"ℹ️ No events scheduled for {from_date.strftime('%B %d')} to move.",
                'data': {'moved_count': 0}
            }

        if not confirmed:
            event_summary = {}
            for sched, event in schedules:
                etype = event.event_type
                event_summary[etype] = event_summary.get(etype, 0) + 1

            summary_str = ", ".join(f"{count} {etype}" for etype, count in event_summary.items())

            return {
                'success': True,
                'message': f"⚠️ **Confirm bulk reschedule:**\n\n" +
                          f"Moving **{len(schedules)} events** from {from_date.strftime('%A, %B %d')} to {to_date.strftime('%A, %B %d')}\n\n" +
                          f"Events: {summary_str}\n\n" +
                          f"Reason: {reason}\n\n" +
                          f"⚠️ *This is a major operation that will affect all schedules for this day.*",
                'requires_confirmation': True,
                'confirmation_data': {
                    'tool_name': 'bulk_reschedule_day',
                    'tool_args': args,
                    'action': f"Move all {len(schedules)} events from {from_date.strftime('%B %d')} to {to_date.strftime('%B %d')}"
                }
            }

        # Perform the bulk move
        moved_count = 0
        for sched, event in schedules:
            # Calculate time difference
            time_of_day = sched.schedule_datetime.time()
            new_datetime = datetime.combine(to_date, time_of_day)
            sched.schedule_datetime = new_datetime
            moved_count += 1

        self.db.commit()

        return {
            'success': True,
            'message': f"✅ Successfully moved **{moved_count} events** from {from_date.strftime('%B %d')} to {to_date.strftime('%B %d')}.\n\n" +
                      f"Reason: {reason}\n\n" +
                      "💡 *Consider verifying the new date's schedule for any conflicts.*",
            'data': {
                'moved_count': moved_count,
                'from_date': from_date.isoformat(),
                'to_date': to_date.isoformat()
            },
            'suggested_actions': [
                {'label': f"Verify {to_date.strftime('%B %d')}", 'action': f"/schedule-verification?date={to_date.isoformat()}"}
            ]
        }

    def _tool_reassign_employee_events(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Remove employee from all their scheduled events"""
        employee_name = args.get('employee_name')
        reason = args.get('reason', 'employee reassignment')
        date_range = args.get('date_range')
        confirmed = args.get('_confirmed', False)

        employee = self._find_employee_by_name(employee_name)
        if not employee:
            return {'success': False, 'message': f"Could not find employee: {employee_name}", 'data': None}

        Schedule = self.models['Schedule']
        Event = self.models['Event']

        # Base query for future events
        today = date.today()
        query = self.db.query(Schedule, Event).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            Schedule.employee_id == employee.id,
            func.date(Schedule.schedule_datetime) >= today
        )

        # Apply date range if specified
        if date_range:
            start_date, end_date = self._parse_date_range(date_range)
            if start_date and end_date:
                query = query.filter(
                    func.date(Schedule.schedule_datetime) <= end_date
                )

        schedules = query.order_by(Schedule.schedule_datetime).all()

        if not schedules:
            return {
                'success': True,
                'message': f"ℹ️ {employee.name} has no future scheduled events to reassign.",
                'data': {'unscheduled_count': 0}
            }

        if not confirmed:
            # Group by date for summary
            from collections import defaultdict
            by_date = defaultdict(list)
            for sched, event in schedules:
                by_date[sched.schedule_datetime.date()].append(event.event_type)

            summary = []
            for d in sorted(by_date.keys())[:5]:
                events = by_date[d]
                summary.append(f"• {d.strftime('%a %b %d')}: {', '.join(events)}")

            remaining = len(by_date) - 5
            if remaining > 0:
                summary.append(f"• ... and {remaining} more days")

            return {
                'success': True,
                'message': f"⚠️ **Confirm removal of {employee.name} from all events:**\n\n" +
                          f"**{len(schedules)} events** will need reassignment:\n\n" +
                          "\n".join(summary) + "\n\n" +
                          f"Reason: {reason}\n\n" +
                          f"⚠️ *This will unschedule all events and mark them as needing assignment.*",
                'requires_confirmation': True,
                'confirmation_data': {
                    'tool_name': 'reassign_employee_events',
                    'tool_args': args,
                    'action': f"Remove {employee.name} from {len(schedules)} events"
                }
            }

        # Perform the removal
        unscheduled_count = 0
        affected_events = []

        for sched, event in schedules:
            affected_events.append({
                'event': event.project_name,
                'type': event.event_type,
                'date': sched.schedule_datetime.date().isoformat()
            })
            event.is_scheduled = False
            self.db.delete(sched)
            unscheduled_count += 1

        self.db.commit()

        return {
            'success': True,
            'message': f"✅ Removed **{employee.name}** from **{unscheduled_count} events**.\n\n" +
                      f"Reason: {reason}\n\n" +
                      f"These events now need to be reassigned to other employees.\n\n" +
                      "💡 *Use 'show urgent unscheduled events' to see what needs assignment.*",
            'data': {
                'employee': employee.name,
                'unscheduled_count': unscheduled_count,
                'affected_events': affected_events[:10]  # Limit for response size
            },
            'suggested_actions': [
                {'label': 'View unscheduled events', 'query': 'show urgent unscheduled events'}
            ]
        }

    def _tool_auto_fill_unscheduled(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Auto-assign available employees to unscheduled events"""
        date_str = args.get('date')
        event_type_filter = args.get('event_type')
        confirmed = args.get('_confirmed', False)

        parsed_date = self._parse_date(date_str)
        if not parsed_date:
            return {'success': False, 'message': f"Could not parse date: {date_str}", 'data': None}

        Event = self.models['Event']
        Employee = self.models['Employee']
        Schedule = self.models['Schedule']
        EmployeeTimeOff = self.models['EmployeeTimeOff']

        # Find unscheduled events for the date
        query = self.db.query(Event).filter(
            Event.is_scheduled == False,
            Event.start_datetime <= datetime.combine(parsed_date, datetime.max.time()),
            Event.due_datetime >= datetime.combine(parsed_date, datetime.min.time()),
            Event.condition != 'Canceled'
        )

        if event_type_filter:
            query = query.filter(Event.event_type == event_type_filter)

        unscheduled = query.all()

        if not unscheduled:
            return {
                'success': True,
                'message': f"✅ No unscheduled {event_type_filter or ''} events for {parsed_date.strftime('%B %d')}.",
                'data': {'proposals': []}
            }

        # Get available employees
        employees = self.db.query(Employee).filter(Employee.is_active == True).all()

        # Get time off
        time_off_records = self.db.query(EmployeeTimeOff.employee_id).filter(
            EmployeeTimeOff.start_date <= parsed_date,
            EmployeeTimeOff.end_date >= parsed_date
        ).all()
        time_off_ids = {r[0] for r in time_off_records}

        # Get already scheduled employees with their Core events
        scheduled_today = self.db.query(Schedule.employee_id, Event.event_type).join(
            Event, Schedule.event_ref_num == Event.project_ref_num
        ).filter(
            func.date(Schedule.schedule_datetime) == parsed_date
        ).all()

        employee_events = {}
        for emp_id, evt_type in scheduled_today:
            if emp_id not in employee_events:
                employee_events[emp_id] = []
            employee_events[emp_id].append(evt_type)

        # Build proposals
        proposals = []
        assigned_employees = set()  # Track assignments within this proposal

        for event in unscheduled:
            best_employee = None
            best_score = -1

            for emp in employees:
                if emp.id in assigned_employees:
                    continue  # Already assigned in this batch
                if emp.id in time_off_ids:
                    continue
                if not emp.can_work_event_type(event.event_type):
                    continue
                if event.event_type == 'Core' and 'Core' in employee_events.get(emp.id, []):
                    continue  # Already has Core

                # Score the employee
                score = 100
                if emp.id not in employee_events:
                    score += 20  # Prefer employees not already working
                if emp.job_title == 'Lead Event Specialist' and event.event_type in ['Freeosk', 'Digitals']:
                    score += 10  # Prefer leads for Lead-only events

                if score > best_score:
                    best_score = score
                    best_employee = emp

            if best_employee:
                proposals.append({
                    'event_id': event.id,
                    'event_name': event.project_name,
                    'event_type': event.event_type,
                    'employee_id': best_employee.id,
                    'employee_name': best_employee.name,
                    'employee_title': best_employee.job_title
                })
                assigned_employees.add(best_employee.id)
                # Track this assignment for future Core limit checks
                if best_employee.id not in employee_events:
                    employee_events[best_employee.id] = []
                employee_events[best_employee.id].append(event.event_type)
            else:
                proposals.append({
                    'event_id': event.id,
                    'event_name': event.project_name,
                    'event_type': event.event_type,
                    'employee_id': None,
                    'employee_name': None,
                    'reason': 'No available qualified employee'
                })

        assignable = [p for p in proposals if p.get('employee_id')]
        unassignable = [p for p in proposals if not p.get('employee_id')]

        if not assignable:
            message = f"⚠️ Could not find available employees for any of the {len(unscheduled)} unscheduled events on {parsed_date.strftime('%B %d')}.\n\n"
            message += "**Cannot assign:**\n"
            for p in unassignable:
                message += f"• {p['event_name']} ({p['event_type']}): {p.get('reason', 'No match')}\n"

            return {
                'success': True,
                'message': message,
                'data': {'proposals': proposals, 'assignable': 0, 'unassignable': len(unassignable)}
            }

        if not confirmed:
            message = f"📋 **Proposed assignments for {parsed_date.strftime('%B %d')}:**\n\n"

            for p in assignable:
                message += f"✅ **{p['event_name']}** ({p['event_type']}) → {p['employee_name']}\n"

            if unassignable:
                message += f"\n⚠️ **Cannot assign ({len(unassignable)}):**\n"
                for p in unassignable:
                    message += f"• {p['event_name']} ({p['event_type']})\n"

            message += f"\n📊 **Summary:** {len(assignable)} can be assigned, {len(unassignable)} need manual assignment"

            return {
                'success': True,
                'message': message,
                'requires_confirmation': True,
                'confirmation_data': {
                    'tool_name': 'auto_fill_unscheduled',
                    'tool_args': {**args, '_proposals': [p for p in proposals if p.get('employee_id')]},
                    'action': f"Assign {len(assignable)} employees to events on {parsed_date.strftime('%B %d')}"
                },
                'data': {'proposals': proposals, 'assignable': len(assignable), 'unassignable': len(unassignable)}
            }

        # Execute the assignments using provided proposals
        saved_proposals = args.get('_proposals', [p for p in proposals if p.get('employee_id')])
        assigned_count = 0

        for prop in saved_proposals:
            event = self.db.query(Event).filter(Event.id == prop['event_id']).first()
            if not event or event.is_scheduled:
                continue

            # Create schedule at a default time (can be adjusted)
            schedule_time = datetime.combine(parsed_date, datetime.strptime('10:30', '%H:%M').time())

            new_schedule = Schedule(
                event_ref_num=event.project_ref_num,
                employee_id=prop['employee_id'],
                schedule_datetime=schedule_time
            )
            self.db.add(new_schedule)
            event.is_scheduled = True
            assigned_count += 1

        self.db.commit()

        return {
            'success': True,
            'message': f"✅ Successfully assigned **{assigned_count} events** on {parsed_date.strftime('%B %d')}.\n\n" +
                      "💡 *Review the schedule to verify times and make any needed adjustments.*",
            'data': {'assigned_count': assigned_count, 'date': parsed_date.isoformat()},
            'suggested_actions': [
                {'label': f"Verify {parsed_date.strftime('%B %d')}", 'action': f"/schedule-verification?date={parsed_date.isoformat()}"}
            ]
        }

    def _find_event_by_name(self, name: str):
        """Find event by name OR project_ref_num"""
        Event = self.models['Event']

        if not name:
            return None

        name = str(name).strip()

        # First check if it's a numeric project_ref_num
        if name.isdigit():
            ref_num = int(name)
            event = self.db.query(Event).filter(
                Event.project_ref_num == ref_num
            ).first()
            if event:
                return event

            # Also check if the number appears in the project name
            event = self.db.query(Event).filter(
                Event.project_name.contains(name)
            ).first()
            if event:
                return event

        # Try exact match on name
        event = self.db.query(Event).filter(
            Event.project_name.ilike(f'%{name}%')
        ).first()

        if event:
            return event

        # Fuzzy match on all unscheduled events first (most relevant)
        unscheduled_events = self.db.query(Event).filter(Event.is_scheduled == False).all()

        best_match = None
        best_ratio = 0

        for evt in unscheduled_events:
            ratio = SequenceMatcher(None, name.lower(), evt.project_name.lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = evt

        if best_ratio > 0.5:
            return best_match

        # Fall back to all events
        all_events = self.db.query(Event).all()

        for evt in all_events:
            ratio = SequenceMatcher(None, name.lower(), evt.project_name.lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = evt

        if best_ratio > 0.5:
            return best_match

        return None

    # ===== UTILITY METHODS =====

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date string including relative dates"""
        if not date_str:
            return None

        date_str = date_str.lower().strip()
        today = date.today()

        # Handle relative dates
        if date_str == 'today':
            return today
        elif date_str == 'tomorrow':
            return today + timedelta(days=1)
        elif date_str == 'yesterday':
            return today - timedelta(days=1)
        elif 'next' in date_str:
            # Handle "next Monday", "next Friday", etc.
            for i, day in enumerate(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
                if day in date_str:
                    days_ahead = i - today.weekday()
                    if days_ahead <= 0:
                        days_ahead += 7
                    return today + timedelta(days=days_ahead)
        elif 'this' in date_str:
            # Handle "this Wednesday", "this Friday", etc.
            for i, day in enumerate(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
                if day in date_str:
                    days_ahead = i - today.weekday()
                    if days_ahead < 0:
                        days_ahead += 7
                    return today + timedelta(days=days_ahead)
        elif date_str in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
            # Assume next occurrence
            day_index = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].index(date_str)
            days_ahead = day_index - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return today + timedelta(days=days_ahead)

        # Try parsing as YYYY-MM-DD
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

        # Try other common formats
        for fmt in ['%m/%d/%Y', '%m-%d-%Y', '%Y/%m/%d']:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        return None

    def _parse_date_range(self, range_str: str) -> tuple:
        """Parse date range string"""
        range_str = range_str.lower().strip()
        today = date.today()

        if range_str == 'this week':
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
            return start, end
        elif range_str == 'next week':
            start = today - timedelta(days=today.weekday()) + timedelta(days=7)
            end = start + timedelta(days=6)
            return start, end
        elif range_str == 'this month':
            start = today.replace(day=1)
            next_month = start.replace(day=28) + timedelta(days=4)
            end = next_month - timedelta(days=next_month.day)
            return start, end

        return None, None

    def _find_employee_by_name(self, name: str):
        """Find employee by fuzzy matching name"""
        Employee = self.models['Employee']

        # First try exact match
        employee = self.db.query(Employee).filter(
            Employee.name.ilike(name)
        ).first()

        if employee:
            return employee

        # Fuzzy match
        all_employees = self.db.query(Employee).filter(Employee.is_active == True).all()

        best_match = None
        best_ratio = 0

        for emp in all_employees:
            ratio = SequenceMatcher(None, name.lower(), emp.name.lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = emp

        # Return if similarity is above 60%
        if best_ratio > 0.6:
            return best_match

        return None
