"""
AI Assistant Service

Natural language interface for scheduling operations using LLM function calling.
Supports OpenAI, Anthropic Claude, and Google Gemini providers.
"""
from typing import Dict, List, Any, Optional
from datetime import datetime, date, timedelta
from dataclasses import dataclass
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class AssistantResponse:
    """Response from AI assistant"""
    response: str  # Natural language response
    data: Optional[Dict[str, Any]] = None  # Structured data
    actions: Optional[List[Dict[str, str]]] = None  # Suggested follow-up actions
    requires_confirmation: bool = False  # Whether action needs user confirmation
    confirmation_data: Optional[Dict[str, Any]] = None  # Data for confirmation
    tool_calls: Optional[List[Dict[str, Any]]] = None  # Raw tool calls made


class AIAssistant:
    """
    Natural language interface for scheduling operations

    Uses LLM function calling to map natural language queries to
    existing API endpoints and services.
    """

    def __init__(self, provider='openai', api_key=None, db_session=None, models=None):
        """
        Initialize AI Assistant

        Args:
            provider: LLM provider ('openai', 'anthropic', or 'gemini')
            api_key: API key for the provider
            db_session: SQLAlchemy database session
            models: Dictionary of database models
        """
        self.provider = provider
        self.api_key = api_key
        self.db = db_session
        self.models = models

        # Initialize LLM client
        self.client = self._init_client()

        # Import tools
        from app.services.ai_tools import AITools
        self.tools = AITools(db_session, models)

        # Get tool schemas
        self.tool_schemas = self.tools.get_tool_schemas()

    def _init_client(self):
        """Initialize LLM client based on provider"""
        if self.provider == 'openai':
            try:
                import openai
                return openai.OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError("OpenAI package not installed. Run: pip install openai")
        elif self.provider == 'anthropic':
            try:
                import anthropic
                return anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError("Anthropic package not installed. Run: pip install anthropic")
        elif self.provider == 'gemini':
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                return genai
            except ImportError:
                raise ImportError("Google Generative AI package not installed. Run: pip install google-generativeai")
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def process_query(
        self,
        user_input: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> AssistantResponse:
        """
        Process natural language query

        Args:
            user_input: Natural language query from user
            conversation_history: Previous conversation messages

        Returns:
            AssistantResponse with natural language reply and data
        """
        try:
            # Build messages
            messages = self._build_messages(user_input, conversation_history)

            # Call LLM
            if self.provider == 'openai':
                response = self._call_openai(messages)
            elif self.provider == 'anthropic':
                response = self._call_anthropic(messages)
            elif self.provider == 'gemini':
                response = self._call_gemini(messages)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")

            return response

        except Exception as e:
            logger.error(f"Error processing query: {str(e)}", exc_info=True)
            return AssistantResponse(
                response=f"I encountered an error: {str(e)}. Please try again.",
                data={'error': str(e)}
            )

    def _build_messages(
        self,
        user_input: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> List[Dict[str, str]]:
        """Build message list for LLM"""
        messages = []

        # System message
        system_message = self._get_system_prompt()
        messages.append({
            'role': 'system',
            'content': system_message
        })

        # Add conversation history if provided
        if conversation_history:
            messages.extend(conversation_history)

        # Add current user input
        messages.append({
            'role': 'user',
            'content': user_input
        })

        return messages

    def _get_system_prompt(self) -> str:
        """Get system prompt for AI assistant"""
        today_str = date.today().strftime('%A, %B %d, %Y')
        tomorrow_str = (date.today() + timedelta(days=1)).strftime('%A, %B %d')

        return f"""You are an INTELLIGENT SCHEDULING MANAGEMENT ASSISTANT. Today is {today_str}. Tomorrow is {tomorrow_str}.

## YOUR ROLE

You are not just a tool executor - you are a THINKING PARTNER for scheduling managers. Your job is to:
1. **UNDERSTAND** what the user is really trying to accomplish
2. **GATHER** the data needed to make informed decisions
3. **ANALYZE** the situation using scheduling rules and constraints
4. **RECOMMEND** the best course of action
5. **EXECUTE** tasks when asked, with proper validation

## HOW YOU THINK

Before answering ANY request, ask yourself:
- What data do I need to answer this properly?
- Are there related issues I should check?
- What could go wrong with this action?
- What should the user know before proceeding?

**ALWAYS gather context first.** Don't guess - look up the actual data.

## CRITICAL: WHEN USER SAYS "YES" TO FIX ISSUES

When user responds "yes", "fix issues", "fix them", or similar after seeing verification issues:

**DO NOT** call random tools or get employee schedules.
**DO** immediately present the FIRST issue using the exact format in the "INTERACTIVE PROBLEM-SOLVING" section.

Look at the previous message - it contains the issues list. Present issue #1 with:
1. The problem (from the issue message)
2. Why it matters (the rule being violated)
3. The suggested fix (from the recommendation)
4. Ask if they want to execute it

## PROACTIVE AWARENESS

You should always be watching for and mentioning:
- 🚨 **Events due tomorrow that aren't scheduled** (critical!)
- 📋 **Unscheduled events in the next 3 days**
- ⚠️ **Employees scheduled outside their availability**
- 🔄 **Missing rotation coverage** (Juicer, Primary Lead)
- 📊 **Employees approaching overtime** (5+ days this week)
- ✅ **Attendance records not entered for today**
- 📝 **Unreported/incomplete events from past dates**

When you notice these issues, bring them up! For example:
"I can help with that. Also, I noticed there are 3 events due tomorrow that still need scheduling - want me to show you those?"

## YOUR TOOLS (Use them to gather data!)

**📊 DATA GATHERING (Use these to understand the situation):**
- get_schedule / get_daily_roster: See what's scheduled for a date
- get_event_details: Get info about a specific event
- get_employee_info / get_employee_schedule: Learn about an employee
- get_unscheduled_events / get_urgent_events: Find what needs work
- check_time_off / get_pending_time_off: Check who has time off
- get_rotation_schedule: See who should be working Juicer rotation

**🔧 ACTIONS (Use these to make changes):**
- assign_employee_to_event: Schedule someone
- reschedule_event: Move/change a schedule
- unschedule_event: Remove someone from an event
- swap_shifts: Exchange two employees' schedules
- request_time_off / cancel_time_off: Manage time-off
- find_replacement: Find coverage for callouts
- auto_fill_unscheduled: Auto-assign available employees
- bulk_reschedule_day: Move all events (emergency)

**📈 ANALYSIS:**
- get_workload_summary: Who's worked most/least
- check_overtime_risk: Who's at risk of 6-day limit
- check_lead_coverage: Opening/closing Lead coverage

**🔄 SYNC:**
- refresh_database: Sync with external API to get fresh data

## SCHEDULING RULES (You must enforce these!)

**Role Qualifications:**
- Club Supervisor: ALL events (Core, Juicer, Supervisor, Freeosk, Digitals)
- Lead Event Specialist: Core, Supervisor, Freeosk, Digitals (NOT Juicer)
- Event Specialist: Core, Freeosk, Digitals only
- Juicer Barista: ONLY Juicer events

**Hard Rules (CANNOT be violated):**
- Max 1 Core event per employee per day
- Max 6 work days per week
- Cannot schedule during time-off
- Cannot schedule on company holidays
- Juicer employees cannot also work Core on same day
- Event must be scheduled within its date range

**Soft Rules (SHOULD be followed):**
- Lead coverage at opening AND closing shifts
- Balanced Core events across time slots (9:45, 10:30, 11:00, 11:30)
- Each Core event needs a paired Supervisor event

## DECISION-MAKING WORKFLOW

When the user asks you to DO something:

1. **GATHER DATA** - Look up relevant information first
   - "Let me check the current schedule..."
   - "Let me see who's available..."

2. **ANALYZE** - Check for conflicts/issues
   - Does this violate any rules?
   - Are there better options?
   - What are the consequences?

3. **EXPLAIN** - Tell the user what you found
   - "I found 3 available employees for this event..."
   - "There's a conflict because John already has a Core..."

4. **RECOMMEND** - Suggest the best action
   - "I recommend assigning Sarah because she's available and qualified."

5. **CONFIRM** - Get user approval for changes
   - "Should I assign Sarah to this event?"

## HOW TO VERIFY A SCHEDULE (Think through it yourself!)

When asked to verify/check a schedule, DO NOT just call a verification tool. Instead, THINK through it:

**Step 1: Gather the data**
- Call get_schedule for the date to see ALL scheduled events
- Call check_time_off to see who has time off
- Call get_rotation_schedule to see who should work Juicer
- Call get_urgent_events to see what's due but unscheduled

**Step 2: Apply each rule mentally and look for violations**
Go through EACH rule and check if the data violates it:

1. **Core Event Limit**: Does any employee have MORE than 1 Core event? List them.
2. **Availability**: Is anyone scheduled who has time-off that day? List them.
3. **Core Times**: Are all Core events at valid times (9:45, 10:30, 11:00, 11:30)? Are they balanced?
4. **Core-Supervisor Pairing**: Does each Core event have a matching Supervisor event for same store/time?
5. **Freeosk/Digitals**: Are these assigned to Club Supervisor or Lead Event Specialist?
6. **Juicer Rotation**: Is the Juicer event assigned to the rotation person for that day?
7. **Juicer-Core Conflict**: Is the Juicer person ALSO scheduled for a Core event? (They shouldn't be)
8. **Events Due Tomorrow**: Are there any events with tomorrow's due date that aren't scheduled?

**Step 3: Present your findings**
List each issue you found with:
- What the problem is (specific names, events, times)
- Why it's a problem (which rule it violates)
- How to fix it

**Step 4: Offer to fix**
"I found X issues. Would you like me to walk through fixing them one by one?"

## HANDLING REQUESTS

**"Schedule event 616936"**
→ First: get_event_details to see what type of event it is
→ Then: Look at employee availability and qualifications
→ Then: recommend the best employee and ask to assign

**"Verify tomorrow" / "Check the schedule"**
→ Gather: get_schedule, check_time_off, get_rotation_schedule, get_urgent_events
→ THINK through each rule and find violations
→ List issues with severity and recommendations
→ Ask: "Want me to walk through fixing these?"

**"Who can cover for John?"**
→ First: get_employee_schedule to see what John is scheduled for
→ Then: find_replacement to get ranked options
→ Present options with qualifications

**"What needs to be done?"**
→ Check: get_urgent_events (due soon, not scheduled)
→ THINK through the schedule using the verification rules above
→ Check: check_overtime_risk for the week
→ Summarize all actionable items

## INTERACTIVE PROBLEM-SOLVING (CRITICAL!)

When verification finds issues and user says "yes" or "fix issues":

**YOU MUST PRESENT THE FIRST ISSUE LIKE THIS:**

```
📋 **Issue 1 of [total]:** [Issue Title]

**The Problem:**
[Clear explanation of what is wrong - be specific with names, times, events]

**Why This Matters:**
[Brief explanation of the scheduling rule being violated]

**Suggested Fix:**
[Specific action to take - include exact names and what to do]

**Should I execute this fix?** (yes/no/skip/different solution)
```

**EXAMPLE RESPONSE when user says "yes" to fix issues:**

📋 **Issue 1 of 8:** Core-Supervisor Pairing

**The Problem:**
The Core event "Sam's Club #4856" scheduled for John Smith at 10:30 AM does not have a matching Supervisor event.

**Why This Matters:**
Every Core event needs a paired Supervisor event for the same store/time, assigned to a Lead or Supervisor.

**Suggested Fix:**
Create a Supervisor event for Sam's Club #4856 at 10:30 AM and assign it to [Lead Name] who is available.

**Should I execute this fix?** (yes/no/skip/different solution)

---

After user responds:
- If "yes": Follow the CHANGE EXECUTION WORKFLOW below
- If "no" or "skip": Move to Issue 2
- If they suggest something else: Do that instead, then continue

## CHANGE EXECUTION WORKFLOW (CRITICAL!)

When user approves a fix, you MUST follow this exact process:

**STEP 1: CONFIRM WHAT YOU WILL DO**
Before executing, state EXACTLY what change you are about to make:
```
✏️ **I will now:**
- [Specific action, e.g., "Assign Sarah Martinez to Core event #616936"]
- [Any secondary actions, e.g., "This will schedule her for 10:30 AM at Sam's Club"]
```

**STEP 2: EXECUTE THE CHANGE**
Call the appropriate tool (assign_employee_to_event, reschedule_event, etc.)

**STEP 3: REFRESH AND VERIFY THE CHANGE SUCCEEDED**
After executing, ALWAYS verify by:
1. Call refresh_database to sync with external API and get fresh data
2. Call get_event_details or get_schedule to re-query the database
3. Confirm the employee is now assigned / event is now scheduled
4. Check that the API sync succeeded (compare before/after)
5. Report success or failure explicitly:

If SUCCESS:
```
✅ **Change Verified:**
- [What was changed]
- Confirmed: [Employee] is now scheduled for [Event] at [Time]
- Issue #1 is now resolved.

Moving to Issue #2...
```

If FAILED:
```
❌ **Change Failed:**
- Attempted: [What you tried to do]
- Error: [What went wrong]
- The issue remains unresolved.

Would you like me to try a different approach?
```

**STEP 4: CONTINUE TO NEXT ISSUE**
Only after verification, present the next issue.

---

**IMPORTANT:** The verify_schedule response includes `issues_for_fixing` in the data.
Each issue has: rule_name, severity, message, details, and recommendation.
USE this information to present issues clearly!

**To get replacement options**, call find_replacement with the employee name.
**To get available employees**, call get_unscheduled_events or check availability.

## IDENTIFICATION

- **Events**: Accept ref numbers (616936), names, or partial matches
- **Employees**: Use fuzzy matching (Diane → Diane Martinez)
- **Dates**: today, tomorrow, Wednesday, this Friday, next Monday, 2024-12-05

## COMMUNICATION STYLE

- Be conversational but efficient
- Explain your reasoning briefly
- Always include specific names, dates, times
- When multiple options exist, present top 3 with pros/cons
- If something fails, explain why and suggest alternatives
- After completing tasks, mention related things to check

Remember: You're a PARTNER, not just a tool. Think ahead, catch problems, and help the manager succeed!"""

    def _call_openai(self, messages: List[Dict[str, str]]) -> AssistantResponse:
        """Call OpenAI API with function calling"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=self.tool_schemas,
                tool_choice="auto",
                temperature=0.1  # Low temperature for consistent function calling
            )

            message = response.choices[0].message

            # Check if tool calls were made
            if message.tool_calls:
                return self._handle_tool_calls(message.tool_calls, messages)
            else:
                # No tool calls, just return the response
                return AssistantResponse(
                    response=message.content or "I'm not sure how to help with that.",
                    data=None
                )

        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}", exc_info=True)
            raise

    def _call_anthropic(self, messages: List[Dict[str, str]]) -> AssistantResponse:
        """Call Anthropic Claude API with tool use"""
        try:
            # Anthropic expects system message separately
            system_message = messages[0]['content']
            conversation_messages = messages[1:]

            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1024,
                system=system_message,
                messages=conversation_messages,
                tools=self.tool_schemas,
                temperature=0.1
            )

            # Check for tool use
            tool_use_blocks = [block for block in response.content if block.type == 'tool_use']

            if tool_use_blocks:
                return self._handle_anthropic_tool_use(tool_use_blocks, messages)
            else:
                # Text response
                text_blocks = [block.text for block in response.content if hasattr(block, 'text')]
                return AssistantResponse(
                    response=' '.join(text_blocks) or "I'm not sure how to help with that.",
                    data=None
                )

        except Exception as e:
            logger.error(f"Anthropic API error: {str(e)}", exc_info=True)
            raise

    def _call_gemini(self, messages: List[Dict[str, str]]) -> AssistantResponse:
        """Call Google Gemini API with function calling"""
        try:
            # Convert tool schemas to Gemini format
            gemini_tools = self._convert_tools_to_gemini_format()

            # Extract system message and conversation
            system_message = messages[0]['content'] if messages[0]['role'] == 'system' else None
            conversation_messages = messages[1:] if system_message else messages

            # Convert messages to Gemini format
            gemini_messages = []
            for msg in conversation_messages:
                role = 'user' if msg['role'] == 'user' else 'model'
                gemini_messages.append({
                    'role': role,
                    'parts': [msg['content']]
                })

            # Create model
            # Use gemini-2.5-flash (Gemini 2.5 Flash model - stable version)
            model = self.client.GenerativeModel(
                model_name='gemini-2.5-flash',
                system_instruction=system_message,
                tools=gemini_tools
            )

            # Generate response
            response = model.generate_content(
                gemini_messages,
                generation_config={'temperature': 0.1}
            )

            # Check for function calls
            if response.candidates[0].content.parts:
                function_calls = [
                    part.function_call
                    for part in response.candidates[0].content.parts
                    if hasattr(part, 'function_call')
                ]

                if function_calls:
                    return self._handle_gemini_function_calls(function_calls, messages)

            # Text response
            text = response.text if hasattr(response, 'text') else "I'm not sure how to help with that."
            return AssistantResponse(
                response=text,
                data=None
            )

        except Exception as e:
            logger.error(f"Gemini API error: {str(e)}", exc_info=True)
            raise

    def _convert_tools_to_gemini_format(self) -> List[Dict[str, Any]]:
        """Convert OpenAI tool format to Gemini function declarations"""
        gemini_tools = []

        for tool in self.tool_schemas:
            if tool['type'] == 'function':
                func = tool['function']

                # Convert parameters to Gemini format
                gemini_params = self._convert_params_to_gemini(func['parameters'])

                gemini_tools.append({
                    'name': func['name'],
                    'description': func['description'],
                    'parameters': gemini_params
                })

        return gemini_tools

    def _convert_params_to_gemini(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Convert OpenAI parameter schema to Gemini format"""
        if not params:
            return {'type': 'OBJECT', 'properties': {}}

        gemini_params = {}

        # Convert type to uppercase
        if 'type' in params:
            gemini_params['type'] = params['type'].upper()

        # Convert properties
        if 'properties' in params:
            gemini_params['properties'] = {}
            for prop_name, prop_schema in params['properties'].items():
                gemini_params['properties'][prop_name] = self._convert_property_to_gemini(prop_schema)

        # Copy required fields
        if 'required' in params:
            gemini_params['required'] = params['required']

        # Copy description if present
        if 'description' in params:
            gemini_params['description'] = params['description']

        return gemini_params

    def _convert_property_to_gemini(self, prop_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a single property schema to Gemini format"""
        gemini_prop = {}

        # Convert type to uppercase
        if 'type' in prop_schema:
            gemini_prop['type'] = prop_schema['type'].upper()

        # Copy description
        if 'description' in prop_schema:
            gemini_prop['description'] = prop_schema['description']

        # Handle array items
        if 'items' in prop_schema:
            gemini_prop['items'] = self._convert_property_to_gemini(prop_schema['items'])

        # Handle nested objects
        if 'properties' in prop_schema:
            gemini_prop['properties'] = {}
            for nested_name, nested_schema in prop_schema['properties'].items():
                gemini_prop['properties'][nested_name] = self._convert_property_to_gemini(nested_schema)

        # Copy enum if present
        if 'enum' in prop_schema:
            gemini_prop['enum'] = prop_schema['enum']

        return gemini_prop

    def _handle_gemini_function_calls(
        self,
        function_calls: List[Any],
        messages: List[Dict[str, str]]
    ) -> AssistantResponse:
        """Execute function calls and format response (Gemini format)"""
        results = []
        all_data = {}
        requires_confirmation = False
        confirmation_data = None

        for function_call in function_calls:
            function_name = function_call.name
            # Handle None args (can happen when function has no parameters)
            function_args = dict(function_call.args) if function_call.args else {}

            logger.info(f"Executing tool: {function_name} with args: {function_args}")

            # Execute the tool
            result = self.tools.execute_tool(function_name, function_args)
            results.append(result)

            # Merge data
            if result.get('data'):
                all_data.update(result['data'])

            # Check if confirmation is needed
            if result.get('requires_confirmation'):
                requires_confirmation = True
                confirmation_data = result.get('confirmation_data')

        # Generate natural language response
        final_response = self._format_tool_results(results)

        # Extract suggested actions
        actions = self._extract_actions(results)

        return AssistantResponse(
            response=final_response,
            data=all_data,
            actions=actions,
            requires_confirmation=requires_confirmation,
            confirmation_data=confirmation_data,
            tool_calls=[{
                'name': fc.name,
                'args': dict(fc.args) if fc.args else {}
            } for fc in function_calls]
        )

    def _handle_tool_calls(
        self,
        tool_calls: List[Any],
        messages: List[Dict[str, str]]
    ) -> AssistantResponse:
        """Execute tool calls and format response (OpenAI format)"""
        results = []
        all_data = {}
        requires_confirmation = False
        confirmation_data = None

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)

            logger.info(f"Executing tool: {function_name} with args: {function_args}")

            # Execute the tool
            result = self.tools.execute_tool(function_name, function_args)
            results.append(result)

            # Merge data
            if result.get('data'):
                all_data.update(result['data'])

            # Check if confirmation is needed
            if result.get('requires_confirmation'):
                requires_confirmation = True
                confirmation_data = result.get('confirmation_data')

        # Generate natural language response
        final_response = self._format_tool_results(results)

        # Extract suggested actions
        actions = self._extract_actions(results)

        return AssistantResponse(
            response=final_response,
            data=all_data,
            actions=actions,
            requires_confirmation=requires_confirmation,
            confirmation_data=confirmation_data,
            tool_calls=[{
                'name': tc.function.name,
                'args': json.loads(tc.function.arguments)
            } for tc in tool_calls]
        )

    def _handle_anthropic_tool_use(
        self,
        tool_use_blocks: List[Any],
        messages: List[Dict[str, str]]
    ) -> AssistantResponse:
        """Execute tool use blocks and format response (Anthropic format)"""
        results = []
        all_data = {}
        requires_confirmation = False
        confirmation_data = None

        for tool_use in tool_use_blocks:
            function_name = tool_use.name
            function_args = tool_use.input

            logger.info(f"Executing tool: {function_name} with args: {function_args}")

            # Execute the tool
            result = self.tools.execute_tool(function_name, function_args)
            results.append(result)

            # Merge data
            if result.get('data'):
                all_data.update(result['data'])

            # Check if confirmation is needed
            if result.get('requires_confirmation'):
                requires_confirmation = True
                confirmation_data = result.get('confirmation_data')

        # Generate natural language response
        final_response = self._format_tool_results(results)

        # Extract suggested actions
        actions = self._extract_actions(results)

        return AssistantResponse(
            response=final_response,
            data=all_data,
            actions=actions,
            requires_confirmation=requires_confirmation,
            confirmation_data=confirmation_data,
            tool_calls=[{
                'name': tu.name,
                'args': tu.input
            } for tu in tool_use_blocks]
        )

    def _format_tool_results(self, results: List[Dict[str, Any]]) -> str:
        """Format tool execution results into natural language"""
        if not results:
            return "I couldn't complete that request."

        # Collect all response messages
        messages = []
        for result in results:
            if result.get('success'):
                messages.append(result.get('message', ''))

        if not messages:
            return "I encountered an issue completing that request."

        return ' '.join(messages)

    def _extract_actions(self, results: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Extract suggested follow-up actions from tool results"""
        actions = []

        for result in results:
            if result.get('suggested_actions'):
                actions.extend(result['suggested_actions'])

        return actions if actions else None

    def confirm_action(self, confirmation_data: Dict[str, Any]) -> AssistantResponse:
        """
        Execute a confirmed action

        Args:
            confirmation_data: Data from the original requires_confirmation response

        Returns:
            AssistantResponse with execution results
        """
        try:
            tool_name = confirmation_data.get('tool_name')
            tool_args = confirmation_data.get('tool_args')

            if not tool_name or not tool_args:
                return AssistantResponse(
                    response="Invalid confirmation data.",
                    data={'error': 'Missing tool information'}
                )

            # Execute the tool with confirmed=True flag
            tool_args['_confirmed'] = True
            result = self.tools.execute_tool(tool_name, tool_args)

            return AssistantResponse(
                response=result.get('message', 'Action completed.'),
                data=result.get('data'),
                actions=result.get('suggested_actions')
            )

        except Exception as e:
            logger.error(f"Error confirming action: {str(e)}", exc_info=True)
            return AssistantResponse(
                response=f"Error executing action: {str(e)}",
                data={'error': str(e)}
            )
