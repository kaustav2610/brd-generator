from pathlib import Path

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    ListFlowable,
    ListItem,
)

from reportlab.lib.styles import getSampleStyleSheet


def _join(items, sep=", "):
    """
    Safely convert Bedrock output fields into readable text.
    Handles:
    - list[str]
    - single string
    - list[dict]
    - dict
    """

    if not items:
        return ""

    # Fix: Bedrock sometimes returns a single string
    if isinstance(items, str):
        return items.strip()


    # Fix: Bedrock sometimes returns a single object
    if isinstance(items, dict):
        value = (
            items.get("name")
            or items.get("description")
            or items.get("text")
            or items.get("value")
            or items.get("evidence")
        )

        if isinstance(value, list):
            return sep.join(
                str(x) for x in value
            )

        return str(value or "")


    parts = []

    for item in items:

        if isinstance(item, str):
            parts.append(item.strip())

        elif isinstance(item, dict):

            value = (
                item.get("name")
                or item.get("description")
                or item.get("text")
                or item.get("value")
                or item.get("evidence")
            )

            if value:
                parts.append(str(value))

        else:
            parts.append(str(item))


    return sep.join(
        x for x in parts if x
    )


def generate_brd(
    analysis: dict,
    inventory: dict,
    run_id: str,
    output_dir: Path
) -> list[Path]:

    output_dir.mkdir(parents=True, exist_ok=True)

    lines = []

    def add(text=""):
        lines.append(text)


    # ==================================================
    # HEADER
    # ==================================================

    add("# Business Requirements Document")
    add("")
    add(f"Analysis Run: {run_id}")
    add("")
    add(
        "This document is reverse-engineered from source-code evidence "
        "and must be validated by business SMEs."
    )


    # ==================================================
    # EXECUTIVE SUMMARY
    # ==================================================

    add("")
    add("## Executive Summary")

    add(
        analysis.get(
            "executive_summary",
            "AI-generated repository analysis summary."
        )
    )


    # ==================================================
    # PURPOSE
    # ==================================================

    add("")
    add("## 1. Purpose")

    add(
        "Document the business capabilities, functional requirements, "
        "business rules and workflows observable in the analyzed "
        "repository to support modernization, onboarding and "
        "process standardization."
    )


    # ==================================================
    # SYSTEM OVERVIEW
    # ==================================================

    add("")
    add("## 2. System Overview")

    add(
        analysis.get(
            "system_overview",
            "Not determined from available evidence."
        )
    )


    # ==================================================
    # BUSINESS OBJECTIVES
    # ==================================================

    add("")
    add("## 3. Business Objectives")

    for obj in analysis.get("business_objectives", []):

        add(f"- {obj}")


    # ==================================================
    # SCOPE
    # ==================================================
    add("")
    add("## 4. Scope")
    
    
    scope = analysis.get("scope", [])
    
    
    if isinstance(scope, dict):
    
        if scope.get("in_scope"):
        
            add(
                "In scope: "
                +
                _join(
                    scope.get("in_scope")
                )
            )
    
    
        if scope.get("observable_business_areas"):
        
            add(
                "Observable business areas: "
                +
                _join(
                    scope.get(
                        "observable_business_areas"
                    )
                )
            )
    
    
        if scope.get("not_established"):
        
            add(
                "Not established by source evidence: "
                +
                _join(
                    scope.get(
                        "not_established"
                    )
                )
            )
    
    
    elif isinstance(scope, list):
    
        for item in scope:
        
            if isinstance(item, dict):
            
                add(
                    "- "
                    +
                    item.get(
                        "description",
                        ""
                    )
                )
    
            else:
            
                add(
                    "- "
                    +
                    str(item)
                )


    # ==================================================
    # REPOSITORY
    # ==================================================

    add("")
    add("## 5. Repository Analysis Scope")

    add(
        f"- Source files analyzed: "
        f"{inventory.get('file_count',0)}"
    )

    add(
        f"- Code chunks analyzed: "
        f"{inventory.get('chunk_count',0)}"
    )

    add(
        "- Languages: "
        +
        ", ".join(
            f"{k} ({v})"
            for k,v in inventory.get(
                "languages",
                {}
            ).items()
        )
    )


    # ==================================================
    # ACTORS
    # ==================================================

    add("")
    add("## 6. Actors")

    for actor in analysis.get("actors", []):

        add(
            f"- {actor.get('name','')} : "
            f"{actor.get('responsibility','')} "
            f"(confidence {actor.get('confidence','')})"
        )


    # ==================================================
    # CAPABILITIES
    # ==================================================

    add("")
    add("## 7. Business Capabilities")

    for cap in analysis.get(
        "business_capabilities",
        []
    ):

        add(
            f"### {cap.get('id','CAP')} "
            f"{cap.get('name','')}"
        )

        add(
            cap.get(
                "description",
                ""
            )
        )

        add(
            f"Confidence: "
            f"{cap.get('confidence','')}"
        )

        add(
            "Evidence: "
            +
            _join(
                cap.get(
                    "evidence",
                    []
                )
            )
        )


    # ==================================================
    # REQUIREMENTS
    # ==================================================

    add("")
    add("## 8. Functional Requirements")

    for req in analysis.get(
        "functional_requirements",
        []
    ):

        add(
            f"### {req.get('id','FR')} "
            f"{req.get('requirement','')}"
        )

        add(
            req.get(
                "description",
                ""
            )
        )

        add(
            "Actors: "
            +
            _join(
                req.get(
                    "actors",
                    []
                )
            )
        )

        add(
            "Evidence: "
            +
            _join(
                req.get(
                    "evidence",
                    []
                )
            )
        )


    # ==================================================
    # RULES
    # ==================================================

    add("")
    add("## 9. Business Rules")


    for rule in analysis.get(
        "business_rules",
        []
    ):

        add(
            f"### {rule.get('id','BR')} "
            f"{rule.get('name','')}"
        )

        add(
            rule.get(
                "description",
                ""
            )
        )

        add(
            "Conditions: "
            +
            _join(
                rule.get(
                    "conditions",
                    []
                ),
                sep="; ",
            )
        )

        add(
            "Actions: "
            +
            _join(
                rule.get(
                    "actions",
                    []
                ),
                sep="; ",
            )
        )

        add(
            "Entities: "
            +
            _join(
                rule.get(
                    "entities",
                    []
                )
            )
        )

        add(
            "Evidence: "
            +
            _join(
                rule.get(
                    "evidence",
                    []
                )
            )
        )


    # ==================================================
    # ENTITIES
    # ==================================================

    add("")
    add("## 10. Key Entities")


    for entity in analysis.get(
        "entities",
        []
    ):

        add(
            f"- {entity.get('name','')} : "
            f"{entity.get('description','')}"
        )

        if entity.get("attributes"):

            add(
                "  Attributes: "
                +
                _join(
                    entity["attributes"]
                )
            )


    # ==================================================
    # WORKFLOWS
    # ==================================================

    add("")
    add("## 11. Business Workflows")


    for wf in analysis.get(
        "workflows",
        []
    ):

        add(
            f"### {wf.get('id','WF')} "
            f"{wf.get('name','')}"
        )

        add(
            wf.get(
                "description",
                ""
            )
        )

        add(
            f"Trigger: {wf.get('trigger','')}"
        )

        add(
            "Actors: "
            +
            _join(
                wf.get(
                    "actors",
                    []
                )
            )
        )


        for idx,step in enumerate(
            wf.get("steps",[]),
            1
        ):

            add(
                f"{idx}. "
                f"{step.get('name','')} - "
                f"{step.get('description','')}"
            )


    # ==================================================
    # INTEGRATIONS
    # ==================================================

    add("")
    add("## 12. Integrations")

    integrations = analysis.get("integrations", [])

    if integrations:
        for item in integrations:
            if not isinstance(item, dict):
                continue

            system = str(item.get("system", "")).strip()
            purpose = str(item.get("purpose", "")).strip()

            if not system and not purpose:
                continue

            if system and purpose:
                add(f"- {system}: {purpose}")
            elif system:
                add(f"- {system}")
            else:
                add(f"- {purpose}")
    else:
        add("No significant external business integrations were identified from the analyzed evidence.")


    # ==================================================
    # MODERNIZATION
    # ==================================================

    add("")
    add("## 13. Modernization Observations")

    modernization = analysis.get(
        "modernization_observations",
        []
    )

    valid_modernization = []

    for item in modernization:
        if isinstance(item, dict):
            observation = str(
                item.get("observation", "")
            ).strip()

            impact = str(
                item.get("impact", "")
            ).strip()

            evidence = item.get(
                "evidence",
                []
            )

            if not isinstance(evidence, list):
                evidence = [str(evidence)]

            evidence = [
                str(e).strip()
                for e in evidence
                if str(e).strip()
            ]

            if observation:
                valid_modernization.append(
                    {
                        "observation": observation,
                        "impact": impact,
                        "evidence": evidence,
                    }
                )

    if valid_modernization:

        # Keep the BRD focused. Do not allow an unusually large
        # AI response to make the document unnecessarily long.
        for item in valid_modernization[:10]:

            add(
                f"- Observation: "
                f"{item['observation']}"
            )

            if item["impact"]:
                add(
                    f"  Impact: "
                    f"{item['impact']}"
                )

            if item["evidence"]:
                add(
                    "  Evidence: "
                    + _join(
                        item["evidence"][:8]
                    )
                )

    else:
        add(
            "No significant modernization observations "
            "were identified from the available evidence."
        )


    # ==================================================
    # NON FUNCTIONAL OBSERVATIONS
    # ==================================================

    add("")
    add("## 14. Non Functional Observations")

    non_functional = analysis.get(
        "non_functional_observations",
        []
    )

    valid_non_functional = []

    for item in non_functional:

        # Bedrock may return either:
        #
        # "Some observation"
        #
        # OR:
        #
        # {
        #   "observation": "...",
        #   "evidence": [...],
        #   "confidence": "high"
        # }
        #
        # Handle both safely.

        if isinstance(item, str):

            text = item.strip()

            if text:
                valid_non_functional.append(
                    {
                        "observation": text,
                        "evidence": [],
                        "confidence": "",
                    }
                )

        elif isinstance(item, dict):

            observation = str(
                item.get("observation", "")
            ).strip()

            evidence = item.get(
                "evidence",
                []
            )

            if not isinstance(evidence, list):
                evidence = [str(evidence)]

            evidence = [
                str(e).strip()
                for e in evidence
                if str(e).strip()
            ]

            confidence = str(
                item.get("confidence", "")
            ).strip()

            if observation:
                valid_non_functional.append(
                    {
                        "observation": observation,
                        "evidence": evidence,
                        "confidence": confidence,
                    }
                )

    if valid_non_functional:

        for item in valid_non_functional[:10]:

            add(
                f"- {item['observation']}"
            )

            if item["evidence"]:
                add(
                    "  Evidence: "
                    + _join(
                        item["evidence"][:8]
                    )
                )

            if item["confidence"]:
                add(
                    f"  Confidence: "
                    f"{item['confidence']}"
                )

    else:
        add(
            "No significant non-functional observations "
            "were identified from the analyzed source."
        )


    # ==================================================
    # SME QUESTIONS
    # ==================================================

    add("")
    add("## 15. Gaps and SME Questions")

    questions = analysis.get(
        "gaps_and_sme_questions",
        []
    )

    valid_questions = []

    for item in questions:

        # Bedrock may return a simple string.
        if isinstance(item, str):

            question = item.strip()

            if question:
                valid_questions.append(
                    {
                        "question": question,
                        "reason": "",
                        "evidence": [],
                        "confidence": "",
                    }
                )

        # Or a structured SME question.
        elif isinstance(item, dict):

            question = str(
                item.get("question", "")
            ).strip()

            reason = str(
                item.get("reason", "")
            ).strip()

            evidence = item.get(
                "evidence",
                []
            )

            if not isinstance(evidence, list):
                evidence = [str(evidence)]

            evidence = [
                str(e).strip()
                for e in evidence
                if str(e).strip()
            ]

            confidence = str(
                item.get("confidence", "")
            ).strip()

            if question:
                valid_questions.append(
                    {
                        "question": question,
                        "reason": reason,
                        "evidence": evidence,
                        "confidence": confidence,
                    }
                )

    if valid_questions:

        for index, item in enumerate(
            valid_questions[:10],
            start=1
        ):

            add(
                f"{index}. {item['question']}"
            )

            if item["reason"]:
                add(
                    f"   Reason: "
                    f"{item['reason']}"
                )

            if item["evidence"]:
                add(
                    "   Evidence: "
                    + _join(
                        item["evidence"][:8]
                    )
                )

            if item["confidence"]:
                add(
                    f"   Confidence: "
                    f"{item['confidence']}"
                )

    else:
        add(
            "No additional SME questions were identified "
            "from the available evidence."
        )


    # ==================================================
    # TRACEABILITY
    # ==================================================

    add("")
    add("## 16. Validation and Traceability")

    add(
        "Each AI-derived rule, requirement and workflow "
        "should be reviewed against cited source files."
    )

    
    # ==================================================
    # WRITE MARKDOWN
    # ==================================================

    md = output_dir / "BRD.md"

    md.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )


    # ==================================================
    # WRITE PDF
    # ==================================================

    pdf = output_dir / "BRD.pdf"


    doc = SimpleDocTemplate(
        str(pdf)
    )

    styles = getSampleStyleSheet()

    story = []


    for line in lines:

        if line.startswith("# "):

            story.append(
                Paragraph(
                    line[2:],
                    styles["Title"]
                )
            )

        elif line.startswith("## "):

            story.append(
                Paragraph(
                    line[3:],
                    styles["Heading2"]
                )
            )

        elif line.startswith("### "):

            story.append(
                Paragraph(
                    line[4:],
                    styles["Heading3"]
                )
            )

        elif line.startswith("- "):

            story.append(
                Paragraph(
                    line[2:],
                    styles["BodyText"]
                )
            )

        elif line:

            story.append(
                Paragraph(
                    line,
                    styles["BodyText"]
                )
            )

        story.append(
            Spacer(
                1,
                6
            )
        )


    doc.build(story)


    return [
        md,
        pdf
    ]