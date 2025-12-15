## Stride Complaint & Service Policies

### Return

**Eligibility (All must be satisfied):**

* Product purchased within **7 calendar days** from the billing date
* Product is **unused** and unworn
* **Original packaging** is intact
* **Original GST bill** is available and unaltered
* A valid order exists in Stride sales records

**Ineligible Conditions (Any one applies):**

* Product shows signs of use
* Damage due to normal wear or misuse
* Missing or damaged original packaging
* Missing or altered GST bill

**Resolution Outcome:**

* Customer must visit the outlet
* Eligible for **refund** after staff inspection
* Final resolution decided by store staff after verification

**Metadata for Automation:**
* `decision`: 'approve'
* `max_days`: 7
* `min_days`: 0
* `eligible_intents`: ['return_refund_request']

---

### Replacement

**Eligibility (All must be satisfied):**

* Product purchased within **7 calendar days** from the billing date
* Issue qualifies as a **manufacturing defect** (e.g., sole separation, stitching failure, glue defects)
* Original GST bill available
* Valid order exists in Stride sales records

**Ineligible Conditions (Any one applies):**

* Damage caused by rough or improper use
* Water damage, cuts, burns, or intentional damage

**Resolution Outcome:**

* Mandatory outlet inspection
* Replacement approved **only after staff verification**
* Replacement subject to stock availability

**Metadata for Automation:**
* `decision`: 'approve'
* `max_days`: 7
* `min_days`: 0
* `eligible_intents`: ['replacement_repair_request','inspection_request']

---

### Repair

**Eligibility (All must be satisfied):**

* Warranty period valid (**up to 6 months / 180 days** from billing date)
* Product is outside the 7-day Return/Replacement window
* Issue is **repairable**
* Valid order exists in Stride sales records

**Ineligible Conditions (Any one applies):**

* Warranty expired
* Structural failure beyond feasible repair

**Resolution Outcome:**

* Repair visit scheduled at outlet
* Manual inspection required before repair approval
* No refund or replacement under this policy

**Metadata for Automation:**
* `decision`: 'approve'
* `max_days`: 180
* `min_days`: 8
* `eligible_intents`: ['replacement_repair_request','inspection_request']

---

### Paid_Repair

**Eligibility (All must be satisfied):**

* Warranty period expired (**more than 6 months / 180 days** from billing date)
* Issue is **repairable**
* Valid order exists in Stride sales records

**Ineligible Conditions:**

* Structural failure beyond feasible repair

**Resolution Outcome:**

* Paid repair required
* Repair visit scheduled at outlet
* Manual inspection required before repair acceptance
* No refund or replacement under this policy

**Metadata for Automation:**
* `decision`: 'approve'
* `max_days`: None
* `min_days`: 181
* `eligible_intents`: ['paid_repair','replacement_repair_request','inspection_request']

---

### Inspection

**Trigger Conditions:**

* Conflicting or incomplete customer information
* Ambiguous or unclear complaint description
* Heavy typographical errors
* Multiple prior tickets for the same order

**Resolution Outcome:**

* Manual inspection ticket generated
* Staff review required
* Ticket validity: **7 calendar days**
* No automated approval or rejection

**Metadata for Automation:**
* `decision`: 'manual'
* `max_days`: None
* `min_days`: 0
* `eligible_intents`: ['inspection_request']

---

### Reject

**Trigger Conditions:**

* The request does not qualify under any active policy window (return, refund, replacement, warranty repair, or paid repair).
* Return or refund explicitly requested beyond the permitted time window.
* Request intent is incompatible with product condition or policy eligibility.
* Evidence of intentional or deliberate damage.
* Product is beyond warranty and no repair (paid or warranty) is applicable.
* The complaint fails to meet the eligibility criteria of all defined policies.

**Resolution Outcome:**

* Claim is automatically rejected for the requested intent.
* No inspection or paid service is offered **for expired return or refund requests**.
* Rejected tickets are closed with a clear reason code.

**Metadata for Automation:**
* `decision`: 'reject'
* `max_days`: null
* `min_days`: null
* `eligible_intents`: ['return_refund_request','replacement_repair_request','paid_repair','general_chat']
