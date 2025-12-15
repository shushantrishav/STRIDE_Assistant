import ollama
import json


class StrideIntentAnalyser:
    def __init__(
        self,
        model: str = "llama3.2:3b",
        temperature: float = 0.0,
    ):
        self.model = model
        self.temperature = temperature
        self.system_prompt = """
    You are a shoe support intent classifier. Analyze the user text and return ONLY a JSON object.
    You have to check Does this text describe damage caused by a pet, an accident, or user misuse?.
    and then classify them into one of these Categories:
    - refund_request: Money back.
    - return_request: Sending product back (fit/style).
    - replacement_request: Wanting a new pair of the same shoe.
    - repair_request: Fix for manufacturing defects.
    - inspection_request: Damage due to manhandle, misuse, or accidents.
    - general_chat: Greetings or small  or anything else apart from context of shoe.

    Output Schema:
    {
        "intent": "string",
        "confidence": "integer (0-100)",
        "reason": "short explanation of why this category was chosen",
        "misuse_or_accident": "boolean"
    }
    """

    def generate_response(self, user_query: str):
        response = ollama.generate(
            model=self.model,
            system=self.system_prompt,
            prompt=f"User text: '{user_query}'",
            format="json",
            options={"temperature": self.temperature},
        )
        return json.loads(response["response"])

    def analyse(self, user_text: str):
        # Step 1: Get desired intent
        intent_data = self.generate_response(user_query=user_text)
        final_intent = intent_data.get("intent", "general_chat")
        misuse_data = bool(intent_data.get("misuse_or_accident", False))
        confidence = int(intent_data.get("confidence", 0))
        reason = intent_data.get("reason", "No reason provided")

        if final_intent in {"refund_request", "return_request"}:
            return {
                "primary_intent": final_intent,
                "intent": "return_refund_request",
                "confidence": confidence,
                "misuse_or_accident": misuse_data,
                "reason": reason,
            }

        if final_intent in {"repair_request", "replacement_request"}:
            return {
                "primary_intent": final_intent,
                "intent": "replacement_repair_request",
                "confidence": confidence,
                "misuse_or_accident": misuse_data,
                "reason": reason,
            }

        # Correct override logic
        if final_intent not in {"inspection_request", "general_chat"} and misuse_data:
            return {
                "primary_intent": "inspection_request",
                "intent": "inspection_request",
                "confidence": confidence,
                "misuse_or_accident": misuse_data,
                "reason": f"Override: User requested {final_intent}, but damage was flagged as misuse",
            }

        return {
            "primary_intent": final_intent,
            "intent": final_intent,
            "confidence": confidence,
            "misuse_or_accident": misuse_data,
            "reason": reason,
        }
