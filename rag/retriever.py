from datetime import date, datetime
from Services.embedder import embed_text, cosine_similarity
from Services.logger_config import logger
import sqlite3
import json

def retrieve_policy(user_query: str, predicted_intent: str, order_data: dict):
    # -------------------------------
    # Compute days since purchase (Fixed String Handling)
    # -------------------------------
    try:
        purchase_date_val = order_data.get("purchase_date")
        
        # Convert string to date object if necessary
        if isinstance(purchase_date_val, str):
            purchase_date = datetime.strptime(purchase_date_val, "%Y-%m-%d").date()
        else:
            purchase_date = purchase_date_val
            
        days_used = (date.today() - purchase_date).days
        logger.info(f"Order days_used: {days_used} for purchase_date: {purchase_date}")
    except Exception as e:
        logger.error(f"Error parsing date: {e}")
        return None

    # -------------------------------
    # Embed user query
    # -------------------------------
    query_vec = embed_text(user_query)

    # -------------------------------
    # Query DB & Filter
    # -------------------------------
    conn = sqlite3.connect("stride.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT policy_type, content, embedding, metadata FROM policy_chunks")
    rows = cursor.fetchall()
    conn.close()

    candidates = []
    for row in rows:
        meta = json.loads(row['metadata'])
        
        # Day bounds
        min_days = meta.get("min_days", 0)
        max_days = meta.get("max_days")
        if max_days is None: max_days = 999999
        
        # Eligibility Check
        if min_days <= days_used <= max_days and predicted_intent in meta.get("eligible_intents", []):
            score = cosine_similarity(query_vec, json.loads(row['embedding']))
            candidates.append({
                "policy_type": row['policy_type'],
                "content": json.loads(row['content']),
                "match_score": score
            })

    # Sort and return top match
    if not candidates: return None
    candidates.sort(key=lambda x: x["match_score"], reverse=True)
    return candidates[0]