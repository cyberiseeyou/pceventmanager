"""
AI Assistant Service

Unified natural language interface for scheduling operations using LLM function calling
and RAG-based context retrieval. Supports OpenAI, Anthropic Claude, and Google Gemini providers.
"""
from typing import Dict, List, Any, Optional
from datetime import datetime, date, timedelta
from dataclasses import dataclass
import json
import logging

from app.ai.context.retriever import ContextRetriever
from app.ai.context.classifier import QueryClassifier

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
    context_used: Optional[Dict[str, Any]] = None  # RAG context used


class AIAssistant:
    """
    Natural language interface for scheduling operations.
    
    Unifies:
    1. Tool Execution (Function Calling) for actions
    2. RAG (Context Retrieval) for policy/info queries
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
        self.tool_schemas = self.tools.get_tool_schemas()

        # Initialize RAG components
        try:
            self.retriever = ContextRetriever(db_session)
            # Initialize classifier with DB data if possible
            self._init_classifier()
        except Exception as e:
            logger.warning(f"Failed to initialize RAG components: {e}")
            self.retriever = None
            self.classifier = None

    def _init_classifier(self):
        """Initialize QueryClassifier with entity names"""
        try:
            Employee = self.models['Employee']
            Event = self.models['Event']
            
            employees = self.db.query(Employee.name).filter(Employee.is_active == True).all()
            employee_names = [e[0] for e in employees]
            
            events = self.db.query(Event.project_name).limit(100).all()
            event_names = list(set([e[0] for e in events]))
            
            self.classifier = QueryClassifier(employees=employee_names, events=event_names)
        except Exception:
            self.classifier = QueryClassifier()

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
        conversation_history: Optional[List[Dict[str, str]]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> AssistantResponse:
        """
        Process natural language query with RAG + Tools
        """
        try:
            # Step 1: Analyze Context (RAG)
            rag_context = ""
            context_summary = {}
            
            if self.classifier and self.retriever:
                analysis = self.classifier.analyze(user_input)
                retrieved_context = self.retriever.retrieve(analysis)
                rag_context = retrieved_context.to_prompt_context()
                context_summary = {
                    'query_type': analysis.query_type.value,
                    'employees_found': len(retrieved_context.employees),
                    'events_found': len(retrieved_context.events)
                }

            # Step 2: Build Messages
            messages = self._build_messages(
                user_input, 
                conversation_history, 
                rag_context,
                page_context=context
            )

            # Step 3: Call LLM
            if self.provider == 'openai':
                response = self._call_openai(messages)
            elif self.provider == 'anthropic':
                response = self._call_anthropic(messages)
            elif self.provider == 'gemini':
                response = self._call_gemini(messages)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")

            # Attach context usage info
            response.context_used = context_summary
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
        conversation_history: Optional[List[Dict[str, str]]] = None,
        rag_context: str = "",
        page_context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, str]]:
        """Build full message context including RAG and Page context"""
        messages = []

        # System message
        system_message = self._get_system_prompt(rag_context, page_context)
        messages.append({
            'role': 'system',
            'content': system_message
        })

        # Add conversation history
        if conversation_history:
            # Filter valid roles
            valid_history = []
            for msg in conversation_history:
                if msg.get('role') in ['user', 'assistant']:
                    valid_history.append({
                        'role': msg['role'],
                        'content': msg['content']
                    })
            messages.extend(valid_history)

        # Add current user input
        messages.append({
            'role': 'user',
            'content': user_input
        })

        return messages

    def _get_system_prompt(self, rag_context: str = "", page_context: Optional[Dict[str, Any]] = None) -> str:
        """Get enhanced system prompt"""
        today_str = date.today().strftime('%A, %B %d, %Y')
        
        # Base Prompt
        prompt = f'''You are an INTELLIGENT SCHEDULING MANAGEMENT ASSISTANT. Today is {today_str}.

## YOUR ROLE
You are a THINKING PARTNER for scheduling managers.
1. UNDERSTAND the user's intent.
2. USE AVAILABLE DATA to make informed decisions.
3. EXECUTE tasks via tools when asked.

## CONTEXT INFORMATION'''

        # Add Page Context (What the user is looking at)
        if page_context:
            prompt += f"\n\n### USER'S CURRENT VIEW:\n"
            for key, value in page_context.items():
                prompt += f"- {key}: {value}\n"

        # Add RAG Context (Database info found relevant to the query)
        if rag_context:
            prompt += f"\n\n### RETRIEVED DATABASE CONTEXT:\n{rag_context}"

        # Standard Instructions
        prompt += '''
## HOW TO RESPOND
- Be conversational but efficient.
- If you have tool outputs, summarize them clearly.
- If you need to make changes, ALWAYS confirm with the user first unless explicitly told to "auto-fix" or "just do it".

## INTERACTIVE PROBLEM SOLVING
When verifying schedules or fixing issues:
1. Present the problem clearly.
2. Explain WHY it matters (rules).
3. Offer a speciifc solution using available tools.

## AVAILABLE TOOLS
You have tools for:
- querying schedules (get_schedule)
- managing employees (get_employee_info)
- executing changes (assign_employee, reschedule_event)
Use them proactively to gather information before answering.
'''
        return prompt

    def _call_openai(self, messages: List[Dict[str, str]]) -> AssistantResponse:
        """Call OpenAI API with function calling"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=self.tool_schemas,
                tool_choice="auto",
                temperature=0.1
            )

            message = response.choices[0].message

            if message.tool_calls:
                return self._handle_tool_calls(message.tool_calls, messages)
            else:
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

            tool_use_blocks = [block for block in response.content if block.type == 'tool_use']

            if tool_use_blocks:
                return self._handle_anthropic_tool_use(tool_use_blocks, messages)
            else:
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
            gemini_tools = self._convert_tools_to_gemini_format()

            system_message = messages[0]['content'] if messages[0]['role'] == 'system' else None
            conversation_messages = messages[1:] if system_message else messages

            gemini_messages = []
            for msg in conversation_messages:
                role = 'user' if msg['role'] == 'user' else 'model'
                gemini_messages.append({
                    'role': role,
                    'parts': [msg['content']]
                })

            model = self.client.GenerativeModel(
                model_name='gemini-2.5-flash',
                system_instruction=system_message,
                tools=gemini_tools
            )

            response = model.generate_content(
                gemini_messages,
                generation_config={'temperature': 0.1}
            )

            if response.candidates[0].content.parts:
                function_calls = [
                    part.function_call
                    for part in response.candidates[0].content.parts
                    if hasattr(part, 'function_call')
                ]

                if function_calls:
                    return self._handle_gemini_function_calls(function_calls, messages)

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
        if 'type' in params:
            gemini_params['type'] = params['type'].upper()
        if 'properties' in params:
            gemini_params['properties'] = {}
            for prop_name, prop_schema in params['properties'].items():
                gemini_params['properties'][prop_name] = self._convert_property_to_gemini(prop_schema)
        if 'required' in params:
            gemini_params['required'] = params['required']
        if 'description' in params:
            gemini_params['description'] = params['description']
        return gemini_params

    def _convert_property_to_gemini(self, prop_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a single property schema to Gemini format"""
        gemini_prop = {}
        if 'type' in prop_schema:
            gemini_prop['type'] = prop_schema['type'].upper()
        if 'description' in prop_schema:
            gemini_prop['description'] = prop_schema['description']
        if 'items' in prop_schema:
            gemini_prop['items'] = self._convert_property_to_gemini(prop_schema['items'])
        if 'properties' in prop_schema:
            gemini_prop['properties'] = {}
            for nested_name, nested_schema in prop_schema['properties'].items():
                gemini_prop['properties'][nested_name] = self._convert_property_to_gemini(nested_schema)
        if 'enum' in prop_schema:
            gemini_prop['enum'] = prop_schema['enum']
        return gemini_prop

    def _handle_gemini_function_calls(self, function_calls: List[Any], messages: List[Dict[str, str]]) -> AssistantResponse:
        """Execute function calls and format response (Gemini format)"""
        results = []
        all_data = {}
        requires_confirmation = False
        confirmation_data = None

        for function_call in function_calls:
            function_name = function_call.name
            function_args = dict(function_call.args) if function_call.args else {}
            logger.info(f"Executing tool: {function_name} with args: {function_args}")
            result = self.tools.execute_tool(function_name, function_args)
            results.append(result)
            if result.get('data'):
                all_data.update(result['data'])
            if result.get('requires_confirmation'):
                requires_confirmation = True
                confirmation_data = result.get('confirmation_data')

        final_response = self._format_tool_results(results)
        actions = self._extract_actions(results)

        return AssistantResponse(
            response=final_response,
            data=all_data,
            actions=actions,
            requires_confirmation=requires_confirmation,
            confirmation_data=confirmation_data,
            tool_calls=[{'name': fc.name, 'args': dict(fc.args) if fc.args else {}} for fc in function_calls]
        )

    def _handle_tool_calls(self, tool_calls: List[Any], messages: List[Dict[str, str]]) -> AssistantResponse:
        """Execute tool calls and format response (OpenAI format)"""
        results = []
        all_data = {}
        requires_confirmation = False
        confirmation_data = None

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            logger.info(f"Executing tool: {function_name} with args: {function_args}")
            result = self.tools.execute_tool(function_name, function_args)
            results.append(result)
            if result.get('data'):
                all_data.update(result['data'])
            if result.get('requires_confirmation'):
                requires_confirmation = True
                confirmation_data = result.get('confirmation_data')

        final_response = self._format_tool_results(results)
        actions = self._extract_actions(results)

        return AssistantResponse(
            response=final_response,
            data=all_data,
            actions=actions,
            requires_confirmation=requires_confirmation,
            confirmation_data=confirmation_data,
            tool_calls=[{'name': tc.function.name, 'args': json.loads(tc.function.arguments)} for tc in tool_calls]
        )

    def _handle_anthropic_tool_use(self, tool_use_blocks: List[Any], messages: List[Dict[str, str]]) -> AssistantResponse:
        """Execute tool use blocks and format response (Anthropic format)"""
        results = []
        all_data = {}
        requires_confirmation = False
        confirmation_data = None

        for tool_use in tool_use_blocks:
            function_name = tool_use.name
            function_args = tool_use.input
            logger.info(f"Executing tool: {function_name} with args: {function_args}")
            result = self.tools.execute_tool(function_name, function_args)
            results.append(result)
            if result.get('data'):
                all_data.update(result['data'])
            if result.get('requires_confirmation'):
                requires_confirmation = True
                confirmation_data = result.get('confirmation_data')

        final_response = self._format_tool_results(results)
        actions = self._extract_actions(results)

        return AssistantResponse(
            response=final_response,
            data=all_data,
            actions=actions,
            requires_confirmation=requires_confirmation,
            confirmation_data=confirmation_data,
            tool_calls=[{'name': tu.name, 'args': tu.input} for tu in tool_use_blocks]
        )

    def _format_tool_results(self, results: List[Dict[str, Any]]) -> str:
        """Format tool execution results into natural language"""
        if not results:
            return "I couldn't complete that request."
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
        return actions

    def confirm_action(self, confirmation_data: Dict[str, Any]) -> AssistantResponse:
        """
        Confirm and execute a previously requested action
        """
        try:
             # This re-routes to the existing tool execution logic but skips the LLM confirmation step
             # The confirmation_data should contain tool_name and args
             tool_name = confirmation_data.get('tool_name')
             args = confirmation_data.get('args')
             
             if not tool_name:
                 raise ValueError("Invalid confirmation data: missing tool_name")
                 
             # Direct tool execution
             result = self.tools.execute_tool(tool_name, args)
             
             return AssistantResponse(
                 response=result.get('message', 'Action confirmed'),
                 data=result.get('data'),
                 actions=result.get('suggested_actions')
             )
        except Exception as e:
            logger.error(f"Error executing confirmed action: {e}")
            return AssistantResponse(
                response=f"Failed to execute action: {str(e)}",
                data={'error': str(e)}
            )
