# ==========================================
# STRIDE – PROMPT BUILDER
# ==========================================

from typing import Dict, Any
from Services.logger_config import logger  # import logger

class StridePromptBuilder:
    """
    The 'Voice' of the Stride Receptionist.
    Strictly follows the Decision Engine's output.
    """
    
    def __init__(self, brand_name="Stride"):
        self.brand_name = brand_name
        logger.info(f"StridePromptBuilder initialized for brand: {brand_name}")

    def _get_system_instructions(self) -> str:
        return f"""
You are the AI Receptionist for {self.brand_name}, a high-end footwear brand.
Your personality: Professional, empathetic, and firm on policy.

CONSTRAINTS:
1. NO PROMISES: Never tell a customer they WILL get a refund or free replacement. 
2. INSPECTION FIRST: Always explain that our specialists need to see the shoe physically.
3. 3-TURN LIMIT: Be concise. If a ticket is being generated, conclude the chat politely.
4. WARRANTY: If the 'paid_service' flag is true, explain that while the warranty has expired, we offer a professional restoration/repair service for a fee.
5. READ-ONLY: You are explaining a decision made by the 'System'. Do not change it.
"""

    def build_final_prompt(self, user_query: str, decision: Dict[str, Any], turn_count: int) -> str:
        """
        Creates the prompt for the LLM.
        """
        try:
            if decision.get('generate_ticket'):
                task = f"Inform the customer that a {decision.get('ticket_type')} ticket has been created and explain the next steps."
            else:
                task = "Acknowledge the customer's issue and ask 1-2 clarifying questions to understand the problem before our 3-turn limit is reached."

            prompt = f"""
{self._get_system_instructions()}

### CONTEXT
- Customer Issue: "{user_query}"
- Conversation Turn: {turn_count} of 3
- System Decision: {decision.get('decision')}
- Action Result: {decision.get('action')}
- Official Policy Reason: {decision.get('reason')}

### TASK
{task}

### RESPONSE (Polite, Human-like, Max 3 sentences):
"""
            logger.info(f"Prompt built successfully for turn {turn_count} with decision {decision.get('decision')}")
            return prompt.strip()

        except Exception as e:
            logger.error(f"Error building prompt for user_query '{user_query}': {e}", exc_info=True)
            return "An internal error occurred while preparing the response. Please try again later."
