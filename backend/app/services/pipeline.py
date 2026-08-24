import json
import time
import traceback
import uuid
from pathlib import Path

from app.config import settings
from app.services.artifact_store import ArtifactStore
from app.services.bedrock_service import BedrockService

from app.services.brd_generator import generate_brd
from app.services.knowledge_graph import build_knowledge_graph
from app.services.repository import RepositoryIngestor
from app.services.review import create_review_file
from app.services.static_analyzer import StaticAnalyzer


class AnalysisPipeline:
    def __init__(self):
        self.ingestor = RepositoryIngestor(
            token=settings.github_token,
            workspace_root=settings.workspace_dir,
        )

    def run(
        self,
        repo_url: str,
        branch: str | None,
        module_hints: list[str],
        upload_source: bool | None = None,
    ) -> dict:

        run_id = uuid.uuid4().hex[:12]
        output_dir = settings.output_dir / run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        settings.workspace_dir.mkdir(parents=True, exist_ok=True)

        started = time.time()
        repo_path = None
        temporary = False

        def log(stage: str) -> None:
            # Prints elapsed time at the start of each stage so a stalled
            # run shows exactly which AWS call or step it's stuck in,
            # instead of the frontend's generic "Finalizing..." label
            # (which is a client-side progress estimate, not real state).
            print(f"[{run_id}] {time.time() - started:6.1f}s  {stage}")

        try:
            # ============================================================
            # 1. FETCH REPOSITORY
            # ============================================================

            log("1. Fetching repository (git clone)")
            repo_path, temporary = self.ingestor.fetch(repo_url, branch)

            # ============================================================
            # 2. STATIC ANALYSIS
            # ============================================================

            log("2. Static analysis")
            analyzer = StaticAnalyzer(
                settings.max_files,
                settings.max_file_bytes,
                settings.max_code_chunks,
            )

            inventory = analyzer.analyze(repo_path)

            self._write(
                output_dir / "repository_manifest.json",
                {
                    "run_id": run_id,
                    "repository": repo_url,
                    "branch": branch,
                    "module_hints": module_hints,
                    "source_mode": (
                        "github"
                        if repo_url.startswith(
                            ("http://", "https://", "ssh://", "git@")
                        )
                        else "local"
                    ),
                },
            )

            self._write(
                output_dir / "code_inventory.json",
                inventory,
            )

            # ============================================================
            # 3. STATIC FINDINGS
            # ============================================================

            log("3. Static findings")
            static_findings = self._static_findings(inventory)

            self._write(
                output_dir / "static_findings.json",
                static_findings,
            )

            # ============================================================
            # 4. BEDROCK CHUNK ANALYSIS
            # ============================================================

            log("4. Bedrock chunk analysis (starting)")
            bedrock = BedrockService(
                settings.aws_region,
                settings.bedrock_model_id,
            )

            ai_findings = []

            relevant_chunks = sorted(
                inventory.get("chunks", []),
                key=lambda x: (
                    x.get("business_relevance", 0),
                    x.get("control_count", 0),
                ),
                reverse=True,
            )[: settings.max_bedrock_chunks]

            for chunk_index, chunk in enumerate(relevant_chunks, 1):
                log(f"4. Bedrock chunk {chunk_index}/{len(relevant_chunks)}: {chunk.get('path','')}")
                try:
                    result = bedrock.analyze_chunk(
                        chunk,
                        module_hints,
                    )

                    result["_source"] = {
                        "path": chunk["path"],
                        "start_line": chunk["start_line"],
                        "end_line": chunk["end_line"],
                    }

                    ai_findings.append(result)

                except Exception as exc:
                    # One bad chunk must NEVER kill the complete analysis.
                    ai_findings.append(
                        {
                            "_source": {
                                "path": chunk["path"],
                                "start_line": chunk["start_line"],
                                "end_line": chunk["end_line"],
                            },
                            "error": str(exc),
                        }
                    )

            self._write(
                output_dir / "ai_findings.json",
                ai_findings,
            )

            # ============================================================
            # 5. BEDROCK SYNTHESIS
            # ============================================================

            log("5. Bedrock synthesis (initial)")
            analysis = None
            synthesis_error = None

            try:
                analysis = bedrock.synthesize(
                    inventory,
                    ai_findings,
                    module_hints,
                )
            except Exception as exc:
                print(f"WARNING: Bedrock synthesis failed: {exc}")
                print(traceback.format_exc())

                analysis = self._fallback_analysis(
                    inventory,
                    static_findings,
                    str(exc),
                )

                # --------------------------------------------------------
                # IMPORTANT:
                # Do NOT immediately fail the whole request.
                #
                # Bedrock may fail because of:
                # - token limits
                # - temporary AWS errors
                # - malformed model output
                # - validation errors
                #
                # Try a reduced synthesis once more.
                # --------------------------------------------------------

                log("5. Bedrock synthesis (reduced retry)")
                try:
                    reduced_findings = self._reduce_findings(
                        ai_findings
                    )

                    reduced_inventory = self._reduce_inventory(
                        inventory
                    )

                    analysis = bedrock.synthesize(
                        reduced_inventory,
                        reduced_findings,
                        module_hints,
                    )

                except Exception as retry_exc:
                    synthesis_error = (
                        f"Initial synthesis failed: {synthesis_error}; "
                        f"reduced synthesis failed: {str(retry_exc)}"
                    )

            # ============================================================
            # 6. FALLBACK
            # ============================================================

            log("6. Fallback / normalize")
            if not analysis:
                analysis = self._fallback_analysis(
                    inventory,
                    static_findings,
                    synthesis_error or "Unknown Bedrock synthesis error",
                    module_hints,
                )

            # Normalize the final analysis so downstream PDF/BPMN/
            # knowledge graph generators always receive the expected shape.
            analysis = self._normalize_analysis(
                analysis,
                inventory,
                static_findings,
            )

            self._write(
                output_dir / "analysis_summary.json",
                analysis,
            )

            # ============================================================
            # 7. KNOWLEDGE GRAPH
            # ============================================================

            log("7. Knowledge graph")
            graph = build_knowledge_graph(
                inventory,
                analysis,
            )

            self._write(
                output_dir / "knowledge_graph.json",
                graph,
            )

            # ============================================================
            # 8. GENERATE DOCUMENTS
            # ============================================================

            log("8. Generating BRD documents")
            generated = []

            generated.extend(
                generate_brd(
                    analysis,
                    inventory,
                    run_id,
                    output_dir,
                )
            )


            generated.append(
                create_review_file(
                    analysis,
                    output_dir,
                )
            )

            # ============================================================
            # 9. SUMMARY
            # ============================================================

            log("9. Writing run summary")
            summary = {
                "run_id": run_id,
                "status": "completed",
                "repository": repo_url,
                "branch": branch,
                "duration_seconds": round(time.time() - started, 2),
                "files_analyzed": inventory.get("file_count", 0),
                "chunks_analyzed": inventory.get("chunk_count", 0),
                "languages": inventory.get("languages", {}),
                "business_rules": len(
                    analysis.get("business_rules", [])
                ),
                "workflows": len(
                    analysis.get("workflows", [])
                ),
                "entities": len(
                    analysis.get("entities", [])
                ),
            
                # Knowledge graph is supplementary. Never allow a
                # missing/malformed graph summary to fail the whole run.
                "knowledge_graph_nodes": (
                    graph.get("summary", {}).get("nodes", 0)
                    if isinstance(graph, dict)
                    else 0
                ),
            
                "knowledge_graph_edges": (
                    graph.get("summary", {}).get("edges", 0)
                    if isinstance(graph, dict)
                    else 0
                ),
            
                "bedrock_chunks": len(ai_findings),
                "potential_secret_files": inventory.get(
                    "potential_secret_files",
                    []
                ),
            }

            # Keep synthesis information for diagnostics,
            # but do not mark the entire run as failed.
            if synthesis_error:
                summary["bedrock_synthesis_warning"] = synthesis_error

            self._write(
                output_dir / "run_summary.json",
                summary,
            )

            # ============================================================
            # 10. S3
            # ============================================================

            log("10. Uploading artifacts to S3")
            store = ArtifactStore(
                settings.aws_region,
                settings.s3_bucket_name,
                settings.s3_prefix,
            )

            artifacts = store.upload_directory(
                run_id,
                output_dir,
            )

            should_upload_source = (
                settings.upload_source_to_s3
                if upload_source is None
                else upload_source
            )

            if should_upload_source:
                log("10. Uploading source tree to S3 (upload_source=true)")
                artifacts.extend(
                    store.upload_source(
                        run_id,
                        repo_path,
                    )
                )

            summary["s3_artifacts"] = artifacts

            self._write(
                output_dir / "run_summary.json",
                summary,
            )

            # Refresh summary in S3 after final artifact list is known.
            refreshed = store.upload_file(
                run_id,
                output_dir / "run_summary.json",
            )

            if refreshed and refreshed not in artifacts:
                artifacts.append(refreshed)

            log("Done")
            return {
                "run_id": run_id,
                "status": "completed",
                "summary": summary,
                "artifacts": artifacts,
                "output_dir": str(output_dir),
            }

        except Exception as exc:

            error = {
                "run_id": run_id,
                "status": "failed",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }

            self._write(
                output_dir / "error.json",
                error,
            )

            raise

        finally:
            self.ingestor.cleanup(
                repo_path,
                temporary,
            )

    # ==================================================================
    # STATIC FINDINGS
    # ==================================================================

    @staticmethod
    def _static_findings(inventory):
        rules = []
        endpoints = []
        tables = set()

        for file in inventory.get("files", []):

            for candidate in file.get(
                "business_rule_candidates",
                [],
            ):
                text = str(
                    candidate.get(
                        "text",
                        "",
                    )
                ).strip()

                if not text:
                    continue

                # Ignore obvious technical-only statements.
                if AnalysisPipeline._is_technical_statement(
                    text
                ):
                    continue

                rules.append(
                    {
                        "source": (
                            f"{file['path']}:"
                            f"{candidate['line']}"
                        ),
                        "text": text,
                    }
                )

            for endpoint in file.get(
                "endpoints",
                [],
            ):
                endpoints.append(
                    {
                        "source_file": file["path"],
                        **endpoint,
                    }
                )

            for table in file.get(
                "database_tables",
                [],
            ):
                if table:
                    tables.add(str(table))

        return {
            "business_rule_candidates": rules[:200],
            "api_endpoints": endpoints[:300],
            "database_tables": sorted(tables),
        }

    # ==================================================================
    # REDUCE INPUT BEFORE RETRY
    # ==================================================================

    @staticmethod
    def _reduce_findings(findings):
        """
        Keep only useful AI findings for the second synthesis attempt.

        This prevents the synthesis prompt from becoming enormous when
        many source chunks were analyzed.
        """

        reduced = []

        for finding in findings[:80]:

            if not isinstance(finding, dict):
                continue

            reduced.append(
                {
                    "capabilities": finding.get(
                        "capabilities",
                        [],
                    )[:5],
                    "business_rules": finding.get(
                        "business_rules",
                        [],
                    )[:5],
                    "functional_requirements": finding.get(
                        "functional_requirements",
                        [],
                    )[:5],
                    "workflow_steps": finding.get(
                        "workflow_steps",
                        [],
                    )[:8],
                    "entities": finding.get(
                        "entities",
                        [],
                    )[:8],
                    "integrations": finding.get(
                        "integrations",
                        [],
                    )[:5],
                    "questions": finding.get(
                        "questions",
                        [],
                    )[:5],
                    "_source": finding.get(
                        "_source",
                        {},
                    ),
                }
            )

        return reduced

    @staticmethod
    def _reduce_inventory(inventory):
        """
        Send only the useful repository metadata during a retry.
        """

        return {
            "file_count": inventory.get(
                "file_count",
                0,
            ),
            "chunk_count": inventory.get(
                "chunk_count",
                0,
            ),
            "languages": inventory.get(
                "languages",
                {},
            ),
            "files": [
                {
                    "path": f.get("path"),
                    "language": f.get("language"),
                    "business_relevance": f.get(
                        "business_relevance",
                        0,
                    ),
                    "database_tables": f.get(
                        "database_tables",
                        [],
                    )[:20],
                    "endpoints": f.get(
                        "endpoints",
                        [],
                    )[:10],
                }
                for f in inventory.get(
                    "files",
                    [],
                )[:150]
            ],
        }

    # ==================================================================
    # FALLBACK ANALYSIS
    # ==================================================================

    @staticmethod
    def _fallback_analysis(
        inventory,
        static_findings,
        reason,
        module_hints=None,
    ):
        """
        Deterministic fallback.

        IMPORTANT:
        This fallback deliberately does NOT turn raw `return;`, SQL
        keywords, HTML terms, or every database table into business
        requirements/entities.

        The old fallback was the primary reason the BRD became polluted
        with values such as:

            return;
            HTML
            JSON
            CURRENT_TIMESTAMP
            URL
            a
            an
            and

        This version produces conservative business documentation.
        """

        module_hints = module_hints or []

        files = inventory.get(
            "files",
            [],
        )

        # --------------------------------------------------------------
        # Candidate business files
        # --------------------------------------------------------------

        business_files = []

        for file in files:

            path = str(
                file.get(
                    "path",
                    "",
                )
            ).lower()

            relevance = file.get(
                "business_relevance",
                0,
            )

            if relevance > 0:
                business_files.append(
                    file
                )

            elif any(
                keyword in path
                for keyword in [
                    "formula",
                    "product",
                    "ingredient",
                    "inventory",
                    "order",
                    "customer",
                    "supplier",
                    "payment",
                    "perfum",
                    "category",
                ]
            ):
                business_files.append(
                    file
                )

        # --------------------------------------------------------------
        # Business entities
        # --------------------------------------------------------------

        entities = []

        entity_map = {
            "formula": "Formula",
            "formulas": "Formula",
            "ingredient": "Ingredient",
            "ingredients": "Ingredient",
            "product": "Product",
            "products": "Product",
            "customer": "Customer",
            "customers": "Customer",
            "supplier": "Supplier",
            "suppliers": "Supplier",
            "inventory": "Inventory Item",
            "order": "Order",
            "orders": "Order",
            "payment": "Payment",
            "payments": "Payment",
            "perfumer": "Perfumer",
            "perfumers": "Perfumer",
            "category": "Category",
            "categories": "Category",
        }

        seen_entities = set()

        for table in static_findings.get(
            "database_tables",
            [],
        ):

            normalized = str(table).strip()

            if not normalized:
                continue

            key = normalized.lower()

            if key in seen_entities:
                continue

            # Never allow technical words into fallback entities.
            if AnalysisPipeline._is_technical_entity(
                normalized
            ):
                continue

            mapped = None

            for keyword, business_name in entity_map.items():
                if keyword in key:
                    mapped = business_name
                    break

            if mapped:
                if mapped.lower() not in seen_entities:
                    entities.append(
                        {
                            "name": mapped,
                            "description": (
                                f"{mapped} information is "
                                "represented or accessed by "
                                "the application."
                            ),
                            "attributes": [],
                            "evidence": [],
                            "confidence": "medium",
                        }
                    )

                    seen_entities.add(
                        mapped.lower()
                    )

        # --------------------------------------------------------------
        # File-derived entities
        # --------------------------------------------------------------

        for file in business_files[:100]:

            path = str(
                file.get(
                    "path",
                    "",
                )
            ).lower()

            for keyword, business_name in entity_map.items():

                if keyword not in path:
                    continue

                if business_name.lower() in seen_entities:
                    continue

                entities.append(
                    {
                        "name": business_name,
                        "description": (
                            f"{business_name} is a business object "
                            "referenced by application source code."
                        ),
                        "attributes": [],
                        "evidence": [
                            file.get(
                                "path",
                                "",
                            )
                        ],
                        "confidence": "low",
                    }
                )

                seen_entities.add(
                    business_name.lower()
                )

        # --------------------------------------------------------------
        # Capabilities
        # --------------------------------------------------------------

        capabilities = []

        capability_patterns = [
            (
                "formula",
                "Formula Management",
                "Create, retrieve, update, or maintain formula information.",
            ),
            (
                "ingredient",
                "Ingredient Management",
                "Maintain ingredient information used by business processes.",
            ),
            (
                "product",
                "Product Management",
                "Maintain product information used by the application.",
            ),
            (
                "inventory",
                "Inventory Management",
                "Manage inventory-related information used by the application.",
            ),
            (
                "customer",
                "Customer Management",
                "Maintain customer-related information.",
            ),
            (
                "order",
                "Order Management",
                "Support order-related processing and information management.",
            ),
            (
                "payment",
                "Payment Processing",
                "Support payment-related processing where evidenced by source code.",
            ),
        ]

        used_capabilities = set()

        for file in business_files:

            path = str(
                file.get(
                    "path",
                    "",
                )
            ).lower()

            for keyword, name, description in capability_patterns:

                if keyword not in path:
                    continue

                if name in used_capabilities:
                    continue

                capabilities.append(
                    {
                        "id": f"CAP-{len(capabilities) + 1:03d}",
                        "name": name,
                        "description": description,
                        "evidence": [
                            file.get(
                                "path",
                                "",
                            )
                        ],
                        "confidence": "low",
                    }
                )

                used_capabilities.add(name)

        # If nothing meaningful was found, use a conservative capability.
        if not capabilities:

            evidence = [
                f.get(
                    "path",
                    "",
                )
                for f in business_files[:10]
                if f.get("path")
            ]

            capabilities.append(
                {
                    "id": "CAP-001",
                    "name": "Business Data Management",
                    "description": (
                        "The application provides functionality for "
                        "managing business data exposed by its source "
                        "modules."
                    ),
                    "evidence": evidence,
                    "confidence": "low",
                }
            )

        # --------------------------------------------------------------
        # Actors
        # --------------------------------------------------------------

        actors = []

        actor_names = set()

        text_for_actor_detection = json.dumps(
            {
                "files": [
                    f.get(
                        "path",
                        "",
                    )
                    for f in business_files[:100]
                ],
                "hints": module_hints,
            }
        ).lower()

        actor_patterns = [
            (
                "perfumer",
                "Perfumer",
                "Creates or maintains perfume-related business information.",
                "medium",
            ),
            (
                "inventory",
                "Inventory Manager",
                "Manages inventory-related information.",
                "low",
            ),
            (
                "customer",
                "Customer",
                "Interacts with customer-related business functionality.",
                "low",
            ),
            (
                "admin",
                "Administrator",
                "Manages application or business information.",
                "low",
            ),
            (
                "manager",
                "Manager",
                "Performs management activities supported by the application.",
                "low",
            ),
        ]

        for keyword, name, responsibility, confidence in actor_patterns:

            if keyword in text_for_actor_detection:

                if name.lower() not in actor_names:

                    actors.append(
                        {
                            "name": name,
                            "responsibility": responsibility,
                            "confidence": confidence,
                        }
                    )

                    actor_names.add(
                        name.lower()
                    )

        if not actors:

            actors.append(
                {
                    "name": "System User",
                    "responsibility": (
                        "Uses the application capabilities exposed "
                        "by the analyzed repository."
                    ),
                    "confidence": "low",
                }
            )

        # --------------------------------------------------------------
        # Business objectives
        # --------------------------------------------------------------

        business_objectives = []

        for capability in capabilities[:6]:

            business_objectives.append(
                {
                    "name": (
                        f"Support "
                        f"{capability['name'].lower()}"
                    ),
                    "description": capability[
                        "description"
                    ],
                    "evidence": capability.get(
                        "evidence",
                        [],
                    ),
                    "confidence": capability.get(
                        "confidence",
                        "low",
                    ),
                }
            )

        # --------------------------------------------------------------
        # Scope
        # --------------------------------------------------------------

        scope = []

        for capability in capabilities[:8]:

            scope.append(
                capability["name"]
            )

        if not scope:
            scope = [
                "Business functionality observable "
                "in the analyzed source repository"
            ]

        # --------------------------------------------------------------
        # System overview
        # --------------------------------------------------------------

        capability_names = [
            c["name"]
            for c in capabilities[:5]
        ]

        if capability_names:

            system_overview = (
                "The analyzed application provides business "
                "functionality centered on "
                + ", ".join(capability_names)
                + ". The available source evidence indicates "
                  "that the application manages business data "
                  "and performs operational processing through "
                  "its application modules. The exact business "
                  "processes, responsibilities and operational "
                  "procedures should be validated with business "
                  "stakeholders."
            )

        else:

            system_overview = (
                "The analyzed repository contains application "
                "components that manage business-related data "
                "and processing. The precise business purpose "
                "could not be established with sufficient "
                "confidence from the available source evidence."
            )

        # --------------------------------------------------------------
        # Executive summary
        # --------------------------------------------------------------

        executive_summary = (
            "The repository contains application functionality "
            "supporting "
            + ", ".join(capability_names[:4])
            + ". The analysis is based on source-code evidence "
              "and should be validated with business SMEs before "
              "being treated as an authoritative description of "
              "business processes."
        )

        # --------------------------------------------------------------
        # Functional requirements
        # --------------------------------------------------------------

        functional_requirements = []

        for capability in capabilities[:8]:

            functional_requirements.append(
                {
                    "id": f"FR-{len(functional_requirements) + 1:03d}",
                    "requirement": (
                        "The system shall support "
                        + capability["name"].lower()
                        + "."
                    ),
                    "description": capability[
                        "description"
                    ],
                    "actors": [
                        a["name"]
                        for a in actors[:3]
                    ],
                    "evidence": capability.get(
                        "evidence",
                        [],
                    ),
                    "confidence": "low",
                }
            )

        # --------------------------------------------------------------
        # Business rules
        #
        # IMPORTANT:
        # Do not expose raw static candidates as business rules.
        # --------------------------------------------------------------

        business_rules = []

        # Only use a very small number of candidates and only when
        # they contain actual business-looking validation text.
        for candidate in static_findings.get(
            "business_rule_candidates",
            [],
        )[:30]:

            text = candidate.get(
                "text",
                "",
            ).strip()

            if not text:
                continue

            if AnalysisPipeline._is_technical_statement(
                text
            ):
                continue

            # Do not pretend we know the business meaning if we do not.
            business_rules.append(
                {
                    "id": f"BR-{len(business_rules) + 1:03d}",
                    "name": "Source-derived business validation",
                    "description": (
                        "The source code contains a validation or "
                        "decision that may represent a business rule. "
                        "The exact business interpretation requires "
                        "SME validation."
                    ),
                    "conditions": [],
                    "actions": [],
                    "entities": [],
                    "evidence": [
                        candidate.get(
                            "source",
                            "",
                        )
                    ],
                    "confidence": "low",
                }
            )

            if len(business_rules) >= 10:
                break

        # --------------------------------------------------------------
        # Workflows
        # --------------------------------------------------------------

        workflows = []

        # Only create a conservative workflow when there is evidence
        # of a meaningful business capability.
        for capability in capabilities[:3]:

            capability_name = capability["name"]

            if any(
                word in capability_name.lower()
                for word in [
                    "management",
                    "processing",
                    "formula",
                    "order",
                ]
            ):

                workflows.append(
                    {
                        "id": f"WF-{len(workflows) + 1:03d}",
                        "name": capability_name,
                        "description": (
                            f"A preliminary business workflow "
                            f"associated with {capability_name.lower()}."
                        ),
                        "trigger": (
                            "A business user initiates the "
                            "corresponding activity."
                        ),
                        "actors": [
                            a["name"]
                            for a in actors[:2]
                        ],
                        "preconditions": [],
                        "postconditions": [],
                        "business_outcome": (
                            f"{capability_name} activity is "
                            "completed or updated."
                        ),
                        "steps": [
                            {
                                "id": "S1",
                                "name": "Initiate activity",
                                "description": (
                                    f"The user initiates an activity "
                                    f"related to {capability_name.lower()}."
                                ),
                                "actor": actors[0]["name"],
                                "type": "task",
                                "condition": "",
                                "next_step": "",
                            }
                        ],
                        "decisions": [],
                        "outcomes": [
                            (
                                f"{capability_name} activity "
                                "is completed."
                            )
                        ],
                        "source_files": capability.get(
                            "evidence",
                            [],
                        ),
                        "confidence": "low",
                    }
                )

        # --------------------------------------------------------------
        # Integrations
        # --------------------------------------------------------------

        integrations = []

        if static_findings.get(
            "database_tables"
        ):

            integrations.append(
                {
                    "system": "Application Database",
                    "purpose": (
                        "Store and retrieve business data "
                        "used by the application."
                    ),
                    "evidence": [
                        str(x)
                        for x in static_findings[
                            "database_tables"
                        ][:10]
                    ],
                    "confidence": "high",
                }
            )

        # --------------------------------------------------------------
        # Modernization
        # --------------------------------------------------------------

        modernization_observations = []

        php_files = [
            f
            for f in files
            if str(
                f.get(
                    "language",
                    ""
                )
            ).lower()
            == "php"
        ]

        if php_files:

            modernization_observations.append(
                {
                    "observation": (
                        "Business processing is implemented "
                        "within legacy application source modules."
                    ),
                    "impact": (
                        "Separating business rules from request, "
                        "database and presentation concerns may "
                        "improve maintainability and testability."
                    ),
                    "evidence": [
                        f.get(
                            "path",
                            "",
                        )
                        for f in php_files[:5]
                    ],
                    "confidence": "low",
                }
            )

        # --------------------------------------------------------------
        # Non-functional observations
        # --------------------------------------------------------------

        non_functional_observations = []

        if reason:

            non_functional_observations.append(
                (
                    "AI synthesis was unavailable for this run. "
                    "The business analysis contains conservative "
                    "source-derived fallback content. "
                    f"Technical reason: {reason}"
                )
            )

        # --------------------------------------------------------------
        # Questions
        # --------------------------------------------------------------

        questions = [
            "Which business roles are authorized to create, update, or delete business records?",
            "Which source-code validations represent mandatory business rules?",
            "What are the expected business outcomes for the identified workflows?",
            "Which external systems participate in the business processes?",
        ]

        return {
            "executive_summary": executive_summary,
            "system_overview": system_overview,
            "business_objectives": business_objectives,
            "scope": scope,
            "actors": actors,
            "business_capabilities": capabilities,
            "functional_requirements": functional_requirements,
            "business_rules": business_rules,
            "entities": entities,
            "workflows": workflows,
            "integrations": integrations,
            "non_functional_observations": non_functional_observations,
            "modernization_observations": modernization_observations,
            "gaps_and_sme_questions": questions,
        }

    # ==================================================================
    # NORMALIZATION
    # ==================================================================

    @staticmethod
    def _normalize_analysis(
        analysis,
        inventory,
        static_findings,
    ):
        """
        Protect the BRD generators from missing or malformed
        fields returned by Bedrock.
        """

        if not isinstance(
            analysis,
            dict,
        ):
            analysis = {}

        list_fields = [
            "business_objectives",
            "scope",
            "actors",
            "business_capabilities",
            "functional_requirements",
            "business_rules",
            "entities",
            "workflows",
            "integrations",
            "non_functional_observations",
            "modernization_observations",
            "gaps_and_sme_questions",
        ]

        for field in list_fields:

            value = analysis.get(
                field
            )

            if not isinstance(
                value,
                list,
            ):
                analysis[field] = []

        # Strings
        for field in [
            "executive_summary",
            "system_overview",
        ]:

            if not isinstance(
                analysis.get(field),
                str,
            ):

                analysis[field] = ""

        # --------------------------------------------------------------
        # Remove obvious garbage entities.
        # --------------------------------------------------------------

        cleaned_entities = []

        for entity in analysis.get(
            "entities",
            [],
        ):

            if not isinstance(
                entity,
                dict,
            ):
                continue

            name = str(
                entity.get(
                    "name",
                    "",
                )
            ).strip()

            if not name:
                continue

            if AnalysisPipeline._is_technical_entity(
                name
            ):
                continue

            entity["name"] = name

            cleaned_entities.append(
                entity
            )

        analysis["entities"] = cleaned_entities

        # --------------------------------------------------------------
        # Remove obvious garbage business rules.
        # --------------------------------------------------------------

        cleaned_rules = []

        for rule in analysis.get(
            "business_rules",
            [],
        ):

            if not isinstance(
                rule,
                dict,
            ):
                continue

            description = str(
                rule.get(
                    "description",
                    "",
                )
            ).strip()

            name = str(
                rule.get(
                    "name",
                    "",
                )
            ).strip()

            if (
                not description
                or description.lower()
                in {
                    "return;",
                    "return",
                    "code-derived validation",
                }
            ):
                continue

            if AnalysisPipeline._is_technical_statement(
                description
            ):
                continue

            rule["name"] = (
                name
                or "Business Rule"
            )

            cleaned_rules.append(
                rule
            )

        analysis["business_rules"] = cleaned_rules

        # --------------------------------------------------------------
        # Make sure objectives and scope are not empty.
        # --------------------------------------------------------------

        if not analysis.get(
            "business_objectives"
        ):

            analysis["business_objectives"] = [
                {
                    "name": "Support identified business capabilities",
                    "description": (
                        "Support the business capabilities evidenced "
                        "by the analyzed source repository."
                    ),
                    "evidence": [],
                    "confidence": "low",
                }
            ]

        if not analysis.get(
            "scope"
        ):

            analysis["scope"] = [
                capability.get(
                    "name",
                    "",
                )
                for capability in analysis.get(
                    "business_capabilities",
                    []
                )
                if capability.get(
                    "name"
                )
            ]

        if not analysis.get(
            "scope"
        ):

            analysis["scope"] = [
                "Business functionality evidenced "
                "in the analyzed repository"
            ]

        # --------------------------------------------------------------
        # System overview
        # --------------------------------------------------------------

        if not analysis.get(
            "system_overview"
        ):

            capability_names = [
                x.get(
                    "name",
                    "",
                )
                for x in analysis.get(
                    "business_capabilities",
                    []
                )
                if x.get(
                    "name"
                )
            ]

            if capability_names:

                analysis["system_overview"] = (
                    "The system supports "
                    + ", ".join(
                        capability_names[:6]
                    )
                    + ". This overview is derived from "
                      "source-code evidence and should be "
                      "validated with business stakeholders."
                )

            else:

                analysis["system_overview"] = (
                    "The repository contains application "
                    "functionality for managing business data "
                    "and processing business operations. "
                    "The exact business purpose requires "
                    "stakeholder validation."
                )

        # --------------------------------------------------------------
        # Executive summary
        # --------------------------------------------------------------

        if not analysis.get(
            "executive_summary"
        ):

            analysis["executive_summary"] = (
                analysis["system_overview"]
            )

        return analysis

    # ==================================================================
    # FILTERS
    # ==================================================================

    @staticmethod
    def _is_technical_statement(text: str) -> bool:

        value = str(
            text
        ).strip().lower()

        if not value:
            return True

        exact_bad_values = {
            "return;",
            "return",
            "continue;",
            "break;",
            "true",
            "false",
            "null",
            "html",
            "json",
            "url",
            "text",
            "array",
            "body",
        }

        if value in exact_bad_values:
            return True

        technical_patterns = [
            "mysqli_",
            "json_encode",
            "json_decode",
            "bind_param",
            "execute(",
            "isset(",
            "empty(",
            "strcmp(",
            "usort(",
            "$_post",
            "$_get",
            "$_request",
            "echo ",
            "print ",
            "include ",
            "require ",
            "curl_",
            "http_",
        ]

        return any(
            pattern in value
            for pattern in technical_patterns
        )

    @staticmethod
    def _is_technical_entity(name: str) -> bool:

        value = str(
            name
        ).strip().lower()

        if not value:
            return True

        bad_words = {
            "a",
            "an",
            "and",
            "all",
            "return",
            "class",
            "html",
            "json",
            "url",
            "text",
            "current_timestamp",
            "max",
            "previous",
            "total",
            "array",
            "arrays",
            "body",
            "bootstrap",
            "color",
            "columns",
            "column",
            "cells",
            "cellspacing",
            "border",
            "abstract",
            "available",
            "being",
            "both",
            "can",
            "common",
            "closing",
            "cache",
            "cahce",
            "branding",
            "lodash",
            "csv",
            "amount",
            "purity",
            "pv",
            "cas",
            "if",
            "else",
            "for",
            "while",
            "function",
            "object",
            "string",
            "integer",
            "boolean",
            "null",
            "true",
            "false",
            "columns",
            "body",
        }

        if value in bad_words:
            return True

        technical_prefixes = (
            "$",
            "mysqli",
            "json_",
            "http_",
        )

        if value.startswith(
            technical_prefixes
        ):
            return True

        return False

    # ==================================================================
    # FILE WRITER
    # ==================================================================

    @staticmethod
    def _write(
        path: Path,
        value,
    ):
        path.write_text(
            json.dumps(
                value,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )