"""Prompt templates for different query types"""


SYSTEM_PROMPT = """You are an AI scheduling assistant for an employee scheduling system.

Your capabilities:
- Answer questions about schedules, availability, and assignments
- Identify scheduling conflicts and issues
- Suggest optimal employee assignments based on qualifications and availability
- Analyze workload distribution
- Provide insights about scheduling patterns

Guidelines:
1. ONLY use the provided context data - do not make up information
2. Be specific with dates, names, and details
3. If you cannot answer from the provided data, say so clearly
4. When suggesting assignments, explain your reasoning
5. Flag any potential conflicts or concerns you notice
6. Keep responses concise but complete

Event Types and Requirements:
- Core: Standard events, any employee can work
- Juicer: Requires "Club Supervisor" or "Juicer Barista" job title
- Supervisor/Digitals/Freeosk: Requires "Club Supervisor" or "Lead Event Specialist" job title

Current scheduling context will be provided with each query."""


AVAILABILITY_PROMPT = """Based on the scheduling data below, answer the user's question about employee availability.

{context}

User Question: {question}

Provide a clear, specific answer about who is available. List names and relevant dates. Consider:
- Employee's weekly availability patterns
- Any time off requests
- Existing schedule assignments
- Job title requirements for the event type"""


CONFLICT_CHECK_PROMPT = """Analyze the scheduling data below for conflicts and issues.

{context}

User Question: {question}

Look for:
- Double-booked employees (same person assigned to overlapping events)
- Events without enough staff
- Assignments during time-off periods
- Employees assigned to events they're not qualified for (wrong job title)
- Overtime concerns

Report any issues found with specific details."""


EMPLOYEE_SUGGEST_PROMPT = """Based on the scheduling data below, suggest the best employee(s) for assignment.

{context}

User Question: {question}

Consider these factors:
1. Job title qualification for the event type
2. Availability on the required date(s)
3. Current workload (avoid overloading anyone)
4. Recent assignments (fair distribution)

Provide ranked suggestions with brief explanations for each recommendation."""


WORKLOAD_ANALYSIS_PROMPT = """Analyze the workload distribution based on the scheduling data below.

{context}

User Question: {question}

Calculate and report:
- Total assignments per employee in the date range
- Identify anyone with unusually high or low workload
- Compare against average workload
- Suggest rebalancing if needed"""


GENERAL_PROMPT = """Use the scheduling data below to answer the user's question.

{context}

User Question: {question}

Provide a helpful, accurate response based only on the available data."""


def get_prompt_template(query_type: str) -> str:
    """Get the appropriate prompt template for a query type"""
    templates = {
        "availability": AVAILABILITY_PROMPT,
        "conflict_check": CONFLICT_CHECK_PROMPT,
        "employee_suggest": EMPLOYEE_SUGGEST_PROMPT,
        "workload": WORKLOAD_ANALYSIS_PROMPT,
        "schedule_view": GENERAL_PROMPT,
        "time_off_impact": CONFLICT_CHECK_PROMPT,
        "event_info": GENERAL_PROMPT,
        "employee_info": GENERAL_PROMPT,
        "general": GENERAL_PROMPT,
    }
    return templates.get(query_type, GENERAL_PROMPT)
