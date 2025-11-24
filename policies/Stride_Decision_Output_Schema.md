# STRIDE – LLM DECISION OUTPUT SCHEMA

## Purpose

This schema defines the **only valid output format** for the Stride Complaint Assistant. All decisions produced by the LLM must conform strictly to this structure so they can be stored, audited, and reviewed by staff systems.

Free-form or conversational-only outputs are **not permitted**.

---

## Output Format (STRICT JSON)

The assistant must output **only one JSON object** and nothing else.

```json
{
  "decision": "APPROVED | REJECTED | MANUAL_REVIEW",
  "policy_applied": "RETURN | REPLACEMENT | REPAIR | PAID_REPAIR | INSPECTION",
  "reason": "string",
  "visit_required": true,
  "outlet_id": "string | null",
  "visit_by": "YYYY-MM-DD | null",
  "ticket_id": "string | null"
}
```

---

## Field Definitions

### `decision`

* **Type:** Enum (string)
* **Allowed values:**

  * `APPROVED` → Customer eligible for store visit
  * `REJECTED` → Policy violation
  * `MANUAL_REVIEW` → Staff inspection required

This field is **mandatory**.

---

### `policy_applied`

* **Type:** Enum (string)
* **Allowed values:**

  * `RETURN`
  * `REPLACEMENT`
  * `REPAIR`
  * `REFUND`
  * `INSPECTION`

Represents the **primary policy** used for the decision.

---

### `reason`

* **Type:** String
* **Description:**

  * Clear, concise explanation referencing policy conditions
  * Must be suitable for staff review and customer display
  * Must not admit liability or promise outcomes

---

### `visit_required`

* **Type:** Boolean
* **Description:**

  * `true` if physical inspection or store visit is required
  * `false` only when request is rejected without visit

---

### `outlet_id`

* **Type:** String or null
* **Description:**

  * Outlet where inspection or resolution should occur
  * `null` if decision is `REJECTED`

---

### `visit_by`

* **Type:** Date (YYYY-MM-DD) or null
* **Description:**

  * Latest permissible visit date
  * Typically 7 days from decision for inspection or repair
  * `null` if visit not applicable

---

### `ticket_id`

* **Type:** String or null
* **Description:**

  * Generated only when `decision = MANUAL_REVIEW`
  * Must be unique and stored in ticket records
  * `null` otherwise

---

## Valid Decision Combinations

| Decision      | Policy                        | Visit Required | Ticket   |
| ------------- | ----------------------------- | -------------- | -------- |
| APPROVED      | RETURN / REPLACEMENT / REPAIR | true           | null     |
| REJECTED      | Any                           | false          | null     |
| MANUAL_REVIEW | INSPECTION                    | true           | required |

Any other combination is **invalid**.

---

## Example Outputs

### Example 1: Approved Replacement

```json
{
  "decision": "APPROVED",
  "policy_applied": "REPLACEMENT",
  "reason": "The reported issue qualifies as a manufacturing defect and falls within the 30-day replacement window.",
  "visit_required": true,
  "outlet_id": "BLR01",
  "visit_by": "2025-12-22",
  "ticket_id": null
}
```

---

### Example 2: Rejected Refund

```json
{
  "decision": "REJECTED",
  "policy_applied": "REFUND",
  "reason": "Refund requests are not accepted for used footwear or after the 7-day return window.",
  "visit_required": false,
  "outlet_id": null,
  "visit_by": null,
  "ticket_id": null
}
```

---

### Example 3: Manual Inspection Required

```json
{
  "decision": "MANUAL_REVIEW",
  "policy_applied": "INSPECTION",
  "reason": "The information provided is insufficient to determine eligibility and requires physical inspection.",
  "visit_required": true,
  "outlet_id": "DEL02",
  "visit_by": "2025-12-20",
  "ticket_id": "A9F3KQ"
}
```

---

## Validation Rules (Mandatory)

* Output must be valid JSON
* No additional text before or after JSON
* No markdown formatting
* No policy speculation
* Fields must match schema exactly

Failure to comply is a **critical error**.

---

## Storage Mapping (Reference)

* `decision` → conversation_summary.decision
* `reason` → conversation_summary.reason
* `ticket_id` → tickets.ticket_id

---

**Schema Version:** 1.0
