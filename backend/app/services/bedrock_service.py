import json
import re
from typing import Any

import boto3
from botocore.config import Config

# Bedrock calls run sequentially, ~27 times per pipeline run (25 chunks +
# up to 2 synthesis calls). Without an explicit timeout, boto3's default
# behavior lets a single stalled/throttled call hang far longer than this,
# and since there's no visibility into it, the whole run just looks
# "stuck" with no error. Bounding it means a bad call fails in seconds
# instead of minutes, and the existing per-chunk try/except in pipeline.py
# turns that into a graceful skip instead of a frozen run.
BEDROCK_CONFIG = Config(
    connect_timeout=15,
    read_timeout=90,
    retries={"max_attempts": 2, "mode": "standard"},
)


SYSTEM_PROMPT = """
You are a senior Business Analyst, Product Analyst and Legacy-System
Reverse Engineering specialist.

Your job is to transform source-code evidence into a reliable,
business-level understanding of an existing software repository.

The repository may belong to ANY business domain.

Do NOT assume the domain unless supported by source-code evidence
or explicit module hints.

============================================================
CORE PRINCIPLE
============================================================

SOURCE CODE IS EVIDENCE.

Do not invent business facts.

When evidence is weak or ambiguous, say so and lower confidence.

Do not convert technical implementation details directly into
business rules or business entities.

The final analysis must be understandable to a business stakeholder
who does not know the programming language.

============================================================
BUSINESS INTERPRETATION
============================================================

Translate technical behavior into business meaning.

BAD:
"return is executed when validation fails."

GOOD:
"The system rejects the operation when required information is missing."

BAD:
"if ($id == null)"

GOOD:
"A formula must be identified by a valid identifier before it can
be retrieved."

BAD:
"mysqli_stmt_bind_param failed."

GOOD:
"The system cannot persist the requested update when the database
operation fails."

============================================================
ENTITY RULES
============================================================

Only identify entities that represent meaningful business concepts.

Valid examples when supported by evidence:

- Formula
- Ingredient
- Product
- Customer
- User
- Order
- Inventory Item
- Supplier
- Category
- Payment
- Approval
- Report

NEVER treat the following as business entities merely because they
appear in source code:

- HTML
- JSON
- XML
- CSV
- URL
- TEXT
- SQL
- SELECT
- INSERT
- UPDATE
- DELETE
- CURRENT_TIMESTAMP
- array
- body
- return
- class
- function
- variable names
- CSS classes
- JavaScript libraries
- Bootstrap
- Lodash
- generic English words
- generic programming terms
- database implementation artifacts

A database table can be evidence for an entity, but the table name
must represent a meaningful business object.

============================================================
BUSINESS RULES
============================================================

A business rule must express a meaningful:

- business constraint
- validation
- authorization rule
- ownership rule
- data requirement
- calculation
- state transition
- business decision
- processing rule
- exception

Do NOT create a business rule merely because source code contains:

- return
- continue
- if
- else
- try
- catch
- SQL execution
- parameter binding
- logging

Every business rule should contain:

- name
- business description
- conditions
- actions
- affected entities
- evidence
- confidence

============================================================
FUNCTIONAL REQUIREMENTS
============================================================

Generate meaningful requirements.

Use:

"The system shall ..."

Examples:

"The system shall allow authorized users to create a perfume formula."

"The system shall validate formula ownership before allowing access."

"The system shall update ingredient records when formula composition
changes."

Do not create one requirement for every source-code function.

============================================================
WORKFLOWS
============================================================

Identify BUSINESS workflows rather than API execution sequences.

Good workflow:

Create Perfume Formula

1. Perfumer initiates formula creation.
2. Formula information is entered.
3. Ingredients are added.
4. Formula information is validated.
5. The formula is saved.
6. The resulting formula becomes available for further use.

Bad workflow:

1. Receive HTTP request.
2. Validate API key.
3. Call PHP function.
4. Execute SQL.
5. Return JSON.

Technical API handling should only appear in a workflow when it
represents a meaningful business activity.

A workflow should contain:

- trigger
- actor
- business activities
- decisions
- alternative paths
- outcome

Only generate workflows supported by evidence.

============================================================
ACTORS
============================================================

Identify meaningful business actors such as:

- Customer
- Administrator
- Manager
- Perfumer
- Inventory Manager
- Supplier
- System Administrator

If a human actor cannot be determined, use:

"System User"

with low or medium confidence.

Do not automatically use "System" as an actor.

============================================================
INTEGRATIONS
============================================================

Identify external systems or infrastructure only when supported.

Examples:

- Database
- Payment gateway
- Email service
- File storage
- External API
- Authentication provider

Do not call ordinary PHP functions or internal modules
"external integrations."

============================================================
MODERNIZATION
============================================================

Identify modernization observations only when evidence supports them.

Examples:

- direct database access from request handlers
- tightly coupled business logic
- duplicated validation
- hard-coded configuration
- legacy authentication
- lack of service separation
- insecure data access patterns

Explain the business/technical impact.

Do not make unsupported architecture claims.

============================================================
CONFIDENCE
============================================================

high:
Directly supported by clear evidence.

medium:
Strong inference supported by multiple pieces of evidence.

low:
Weak inference or ambiguous evidence.

============================================================
TRACEABILITY
============================================================

Important capabilities, requirements, rules and workflows must contain
source evidence whenever available.

Evidence should use the form:

"path/to/file.php:123"

or:

"path/to/file.php:123-180"

Do not use artificial evidence such as:

"file:181-360"

unless that exact form exists in the supplied evidence.

============================================================
OUTPUT
============================================================

Return valid JSON only.

Do not return Markdown fences.

Do not return explanatory text outside JSON.
"""


class BedrockService:

    def __init__(self, region: str, model_id: str):
        self.model_id = model_id
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            config=BEDROCK_CONFIG,
        )

    # ============================================================
    # CHUNK ANALYSIS
    # ============================================================

    def analyze_chunk(
        self,
        chunk: dict,
        hints: list[str],
    ) -> dict:

        source_path = chunk.get("path", "")
        language = chunk.get("language", "")
        start_line = chunk.get("start_line", 0)
        end_line = chunk.get("end_line", 0)
        source_text = chunk.get("text", "")

        prompt = f"""
Analyze this source-code chunk as a senior business analyst.

Repository domain:
Use only evidence from the source code and module hints.

Module hints:
{json.dumps(hints, ensure_ascii=False)}

============================================================
SOURCE INFORMATION
============================================================

Source file:
{source_path}

Language:
{language}

Lines:
{start_line}-{end_line}

============================================================
SOURCE CODE
============================================================

{source_text[:12000]}

============================================================
ANALYSIS RULES
============================================================

Extract only meaningful business-level evidence.

1. Ignore generic programming constructs.

2. Ignore HTML/CSS/JavaScript library names unless they clearly
represent a business capability.

3. Ignore SQL keywords.

4. Do not treat variable names as business entities automatically.

5. Translate validations into business rules.

6. Translate meaningful create/update/delete operations into
business activities.

7. Identify real business objects only when supported by evidence.

8. Identify actors only when reasonably supported by the source.

9. Identify integrations only when the source demonstrates interaction
with an external system or infrastructure service.

10. Do not create a workflow from a single API endpoint.

11. Do not create business rules from every "return", "if", "continue",
or exception.

12. If there is insufficient business evidence, return an empty list.

============================================================
RETURN JSON
============================================================

Return exactly one JSON object with these fields:

{{
  "capabilities": [],
  "business_rules": [],
  "functional_requirements": [],
  "workflow_steps": [],
  "entities": [],
  "integrations": [],
  "questions": []
}}

Each capability must have:

{{
  "name": "",
  "description": "",
  "evidence": [],
  "confidence": "high|medium|low"
}}

Each business rule must have:

{{
  "name": "",
  "description": "",
  "conditions": [],
  "actions": [],
  "entities": [],
  "evidence": [],
  "confidence": "high|medium|low"
}}

Each functional requirement must have:

{{
  "requirement": "",
  "evidence": [],
  "confidence": "high|medium|low"
}}

Each workflow step must have:

{{
  "workflow_candidate": "",
  "actor": "",
  "action": "",
  "condition": "",
  "outcome": "",
  "evidence": [],
  "confidence": "high|medium|low"
}}

Each entity must have:

{{
  "name": "",
  "description": "",
  "attributes": [],
  "evidence": [],
  "confidence": "high|medium|low"
}}

Each integration must have:

{{
  "system": "",
  "purpose": "",
  "evidence": [],
  "confidence": "high|medium|low"
}}

Questions must be business questions that cannot be answered reliably
from the source evidence.
"""

        return self._converse(
            prompt,
            max_tokens=3000,
        )

    # ============================================================
    # SYNTHESIS
    # ============================================================

    def synthesize(
        self,
        inventory: dict,
        findings: list[dict],
        hints: list[str],
    ) -> dict:

        # Keep synthesis input deliberately small.
        #
        # The chunk-level analysis has already extracted the important
        # evidence. Sending the entire repository inventory and every
        # chunk can exceed Bedrock context limits and also introduces
        # unnecessary noise.

        compact_inventory = {
            "file_count": inventory.get("file_count", 0),
            "chunk_count": inventory.get("chunk_count", 0),
            "languages": inventory.get("languages", {}),
            "files": [],
        }

        for file in inventory.get("files", [])[:150]:
            compact_inventory["files"].append(
                {
                    "path": file.get("path", ""),
                    "language": file.get("language", ""),
                    "functions": file.get("functions", [])[:30],
                    "classes": file.get("classes", [])[:20],
                    "database_tables": file.get(
                        "database_tables",
                        [],
                    )[:30],
                    "endpoints": file.get(
                        "endpoints",
                        [],
                    )[:20],
                }
            )

        # Keep only successful AI findings.
        clean_findings = []

        for finding in findings:

            if not isinstance(finding, dict):
                continue

            if finding.get("error"):
                continue

            clean_findings.append(finding)

        # Limit the amount of serialized evidence sent to synthesis.
        findings_text = json.dumps(
            clean_findings,
            ensure_ascii=False,
        )

        if len(findings_text) > 28000:
            findings_text = findings_text[:28000]

        inventory_text = json.dumps(
            compact_inventory,
            ensure_ascii=False,
        )

        if len(inventory_text) > 22000:
            inventory_text = inventory_text[:22000]

        schema = {
            "executive_summary": "",
            "system_overview": "",
            "business_objectives": [],
            "scope": [],
            "actors": [],
            "business_capabilities": [],
            "functional_requirements": [],
            "business_rules": [],
            "entities": [],
            "workflows": [],
            "integrations": [],
            "non_functional_observations": [],
            "modernization_observations": [],
            "gaps_and_sme_questions": [],
        }

        prompt = f"""
Create the final consolidated BUSINESS ANALYSIS for this repository.

The repository may belong to any business domain.

Use only source evidence and module hints.

Module hints:
{json.dumps(hints, ensure_ascii=False)}

============================================================
REPOSITORY INVENTORY
============================================================

{inventory_text}

============================================================
CHUNK-LEVEL BUSINESS FINDINGS
============================================================

{findings_text}

============================================================
CONSOLIDATION RULES
============================================================

The chunk findings may contain duplicates, weak inferences,
or occasional technical details.

You must consolidate them into one coherent business view.

------------------------------------------------------------
RULE 1: REMOVE TECHNICAL NOISE
------------------------------------------------------------

Reject findings that are only:

- return statements
- if statements
- SQL keywords
- programming constructs
- HTML/CSS
- JavaScript libraries
- variable names
- function names
- implementation artifacts
- generic English words

------------------------------------------------------------
RULE 2: BUSINESS ENTITIES
------------------------------------------------------------

An entity must represent a meaningful:

- business object
- business actor
- transaction
- process object
- business configuration object
- external business system

Do not create an entity merely because a word appears in a table,
variable, HTML element, or SQL statement.

------------------------------------------------------------
RULE 3: BUSINESS RULES
------------------------------------------------------------

Only include meaningful business rules.

A rule should describe a:

- validation
- authorization
- ownership constraint
- data requirement
- calculation
- state transition
- business decision
- processing rule
- exception

Do not create rules from every conditional statement.

------------------------------------------------------------
RULE 4: FUNCTIONAL REQUIREMENTS
------------------------------------------------------------

Generate meaningful requirements.

Use:

"The system shall ..."

Do not generate one requirement for every source-code function.

------------------------------------------------------------
RULE 5: WORKFLOWS
------------------------------------------------------------

Generate real business workflows where sufficient evidence exists.

Prefer:

- formula creation
- formula update
- ingredient management
- inventory operations
- customer management
- product management
- order processing
- payment
- approval
- reporting
- import/export
- compliance
- state changes

A workflow should contain:

- trigger
- actor
- business activities
- decisions
- outcomes

Do not turn HTTP/API execution into a business workflow.

If evidence is insufficient, return an empty workflow list.

------------------------------------------------------------
RULE 6: SYSTEM OVERVIEW
------------------------------------------------------------

The system overview MUST be populated.

Describe:

- what the system appears to do
- its major business domain
- its principal capabilities
- its major users
- the major data/process areas

Use evidence-supported language.

------------------------------------------------------------
RULE 7: BUSINESS OBJECTIVES
------------------------------------------------------------

Business objectives MUST be populated when the repository provides
enough evidence.

Express objectives as business outcomes, not implementation details.

Examples:

- Maintain accurate formula information.
- Support controlled formula updates.
- Maintain ingredient information.
- Support operational inventory management.

Do not invent financial or strategic objectives that are not supported.

------------------------------------------------------------
RULE 8: SCOPE
------------------------------------------------------------

Scope MUST be populated.

Describe the repository functionality that is actually observable.

Separate:

- In scope
- Observable business areas
- Not established by source evidence

------------------------------------------------------------
RULE 9: NON-FUNCTIONAL OBSERVATIONS
------------------------------------------------------------

Only include evidence-supported non-functional observations.

Examples:

- security concerns
- maintainability concerns
- reliability concerns
- performance concerns
- auditability concerns

If none can be established, return:

[
  "No additional non-functional characteristics could be established
   reliably from the analyzed evidence."
]

------------------------------------------------------------
RULE 10: SME QUESTIONS
------------------------------------------------------------

Return useful questions when business meaning remains unclear.

Examples:

- What are the authoritative rules for formula ownership?
- What are the permitted formula lifecycle states?
- What are the required ingredient attributes?
- What roles are authorized to modify formulas?

Do not invent questions unrelated to the observed system.

------------------------------------------------------------
RULE 11: TRACEABILITY
------------------------------------------------------------

Use evidence from the findings.

Evidence must refer to real repository files.

Do not invent filenames.

------------------------------------------------------------
RULE 12: CONFIDENCE
------------------------------------------------------------

Use:

high
medium
low

------------------------------------------------------------
OUTPUT
------------------------------------------------------------

Return ONLY a valid JSON object.

The JSON structure must be:

{json.dumps(schema, ensure_ascii=False, indent=2)}

For:

actors:

use objects containing:

name
responsibility
confidence

For:

business_capabilities:

use:

id
name
description
evidence
confidence

For:

functional_requirements:

use:

id
requirement
description
actors
evidence
confidence

For:

business_rules:

use:

id
name
description
conditions
actions
entities
evidence
confidence

For:

entities:

use:

name
description
attributes
evidence
confidence

For:

workflows:

use:

id
name
description
trigger
actors
preconditions
postconditions
business_outcome
steps
decisions
outcomes
source_files
confidence

Workflow steps must contain:

id
name
description
actor
type
condition
next_step

Decision objects must contain:

id
question
yes_next
no_next

For:

integrations:

use:

system
purpose
evidence
confidence

For:

modernization_observations:

use:

observation
impact
evidence
confidence

For:

gaps_and_sme_questions:

use objects containing:

question
reason
evidence
confidence
"""

        return self._converse(
            prompt,
            max_tokens=4000,
        )

    # ============================================================
    # BEDROCK CALL
    # ============================================================

    def _converse(
        self,
        prompt: str,
        max_tokens: int = 3000,
    ) -> dict[str, Any]:

        # Bedrock model limit is 10000 requested tokens.
        # Keep a safety ceiling below that limit.
        max_tokens = min(max_tokens, 5000)

        response = self.client.converse(
            modelId=self.model_id,
            system=[
                {
                    "text": SYSTEM_PROMPT,
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "text": prompt,
                        }
                    ],
                }
            ],
            inferenceConfig={
                "temperature": 0.1,
                "maxTokens": max_tokens,
            },
        )

        content = response.get(
            "output",
            {},
        ).get(
            "message",
            {},
        ).get(
            "content",
            [],
        )

        if not content:
            raise ValueError(
                "Bedrock returned an empty response."
            )

        text_parts = []

        for item in content:
            if isinstance(item, dict) and "text" in item:
                text_parts.append(
                    item["text"]
                )

        text = "\n".join(text_parts).strip()

        if not text:
            raise ValueError(
                "Bedrock returned no text content."
            )

        return self._parse_json(text)

    # ============================================================
    # JSON PARSER
    # ============================================================

    @staticmethod
    def _parse_json(text: str) -> dict:

        cleaned = text.strip()

        # Remove Markdown fences if the model accidentally returns them.
        cleaned = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(
            r"\s*```$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = cleaned.strip()

        # First attempt: complete JSON response.
        try:
            value = json.loads(cleaned)

            if not isinstance(value, dict):
                raise ValueError(
                    "Bedrock returned JSON that is not an object."
                )

            return value

        except json.JSONDecodeError:
            pass

        # Second attempt: locate the outer JSON object.
        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start == -1 or end <= start:
            raise ValueError(
                "Bedrock returned no JSON object."
            )

        candidate = cleaned[start:end + 1]

        try:
            value = json.loads(candidate)

            if not isinstance(value, dict):
                raise ValueError(
                    "Bedrock returned JSON that is not an object."
                )

            return value

        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Bedrock returned invalid JSON: {exc}"
            ) from exc