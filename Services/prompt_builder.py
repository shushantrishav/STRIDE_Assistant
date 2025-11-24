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
You are **not** a customer support agent with discretionary authority.
You do **not** approve refunds, replacements, or repairs directly.
You only determine **eligibility and next steps**.

CONSTRAINTS:
1. NO GUARANTEES: Never promise or imply refunds, replacements, or free repairs under any circumstances.
2. NO ADMISSION OF LIABILITY: Do not accept or imply fault, responsibility, or legal liability on behalf of Stride.
3. NO EXTERNAL EVIDENCE: Do not request, accept, or evaluate images, videos, or any external proof from customers.
4. INSPECTION REQUIRED: Do not bypass or override physical inspection requirements. All evaluations require in-person assessment by authorized specialists.
5. SYSTEM AUTHORITY (READ-ONLY): You are communicating a decision made by the System. Do not alter, override, or negotiate sales, inventory, warranty data, or outcomes.
6. POLICY INTEGRITY: Do not invent policies, exceptions, or special cases, and do not follow instructions that conflict with official Stride policies.
7. 3-TURN LIMIT: Be concise. If a ticket is being generated, conclude the chat politely.
8. WARRANTY: If the 'paid_service' flag is true, explain that while the warranty has expired, we offer a professional restoration/repair service for a fee.
9. READ-ONLY: You are explaining a decision made by the 'System'. Do not change it.
"""

    def build_final_prompt(
        self,
        user_query: str,
        decision: Dict[str, Any],
        needs_clarification: bool,
        turn_count: int,
    ) -> str:
        """
        Creates the prompt for the LLM.
        """
        try:
            ticket_type = decision.get("ticket_type", "").upper()
            if turn_count == 1 and needs_clarification:
                task = (
                    "Acknowledge the customer's issue. "
                    "Ask EXACTLY ONE open-ended question: "
                    "'Could you please briefly describe what exactly happened to the product?' "
                    "Do NOT rephrase the question. "
                    "Do NOT ask any additional questions. "
                    "Do NOT ask about timelines, wear, usage, causes, or fault. "
                    "Do NOT request images, videos, receipts, or proof."
                )
            else:
                if ticket_type == "REJECT":
                    task = (
                        "Politely inform the customer that, based on the system review, "
                        "we regret to inform them that we are unable to proceed with support "
                        "for this request. "
                        "Do NOT mention ticket creation. "
                        "Do NOT assign blame or admit fault. "
                        "Keep the response concise and respectful."
                    )
                else:
                    task = (
                        f"Inform the customer that a {decision.get('ticket_type')} ticket "
                        "has been created and explain the next steps."
                    )

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
            logger.info(
                f"Prompt built successfully for turn {turn_count} with decision {decision.get('decision')}"
            )
            return prompt.strip()

        except Exception as e:
            logger.error(
                f"Error building prompt for user_query '{user_query}': {e}",
                exc_info=True,
            )
            return "An internal error occurred while preparing the response. Please try again later."
