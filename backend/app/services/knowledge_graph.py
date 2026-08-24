from collections import defaultdict


def build_knowledge_graph(inventory: dict, analysis: dict) -> dict:
    nodes = []
    edges = []

    node_ids = set()
    edge_ids = set()


    def node(node_id, node_type, name, properties=None):

        if not node_id:
            return

        if node_id not in node_ids:

            node_ids.add(node_id)

            nodes.append(
                {
                    "id": node_id,
                    "type": node_type,
                    "name": name,
                    "properties": properties or {},
                }
            )


    def edge(source, target, relationship, properties=None):

        if not source or not target:
            return

        edge_id = (
            source,
            target,
            relationship
        )

        if edge_id not in edge_ids:

            edge_ids.add(edge_id)

            edges.append(
                {
                    "source": source,
                    "target": target,
                    "relationship": relationship,
                    "properties": properties or {},
                }
            )


    # ==================================================
    # SOURCE REPOSITORY GRAPH
    # ==================================================

    for file in inventory.get("files", []):

        file_id = f"file:{file['path']}"

        node(
            file_id,
            "source_file",
            file["path"],
            {
                "language": file.get("language"),
            }
        )


        for fn in file.get("functions", []):

            function_id = (
                f"function:{file['path']}:{fn}"
            )

            node(
                function_id,
                "function",
                fn,
                {
                    "file": file["path"]
                }
            )

            edge(
                file_id,
                function_id,
                "CONTAINS"
            )


        for cls in file.get("classes", []):

            class_id = (
                f"class:{file['path']}:{cls}"
            )

            node(
                class_id,
                "class",
                cls,
                {
                    "file": file["path"]
                }
            )

            edge(
                file_id,
                class_id,
                "CONTAINS"
            )


        for table in file.get(
            "database_tables",
            []
        ):

            table_id = f"table:{table}"

            node(
                table_id,
                "database_table",
                table
            )

            edge(
                file_id,
                table_id,
                "REFERENCES"
            )


        for endpoint in file.get(
            "endpoints",
            []
        ):

            endpoint_id = (
                f"endpoint:{file['path']}:"
                f"{endpoint.get('method')}:"
                f"{endpoint.get('path')}"
            )


            node(
                endpoint_id,
                "api_endpoint",
                endpoint.get("path"),
                endpoint
            )


            edge(
                file_id,
                endpoint_id,
                "EXPOSES"
            )


    # ==================================================
    # ACTORS
    # ==================================================

    for actor in analysis.get(
        "actors",
        []
    ):

        actor_id = (
            f"actor:{actor.get('name')}"
        )


        node(
            actor_id,
            "business_actor",
            actor.get("name"),
            actor
        )


    # ==================================================
    # BUSINESS CAPABILITIES
    # ==================================================

    for capability in analysis.get(
        "business_capabilities",
        []
    ):

        cap_id = (
            f"capability:{capability.get('id')}"
        )


        node(
            cap_id,
            "business_capability",
            capability.get("name"),
            capability
        )


        for evidence in capability.get(
            "evidence",
            []
        ):

            source = evidence.split(":", 1)[0]

            file_id = f"file:{source}"

            if file_id in node_ids:

                edge(
                    cap_id,
                    file_id,
                    "SUPPORTED_BY"
                )


    # ==================================================
    # FUNCTIONAL REQUIREMENTS
    # ==================================================

    for req in analysis.get(
        "functional_requirements",
        []
    ):

        req_id = (
            f"requirement:{req.get('id')}"
        )


        node(
            req_id,
            "functional_requirement",
            req.get("requirement"),
            req
        )


        for evidence in req.get(
            "evidence",
            []
        ):

            source = evidence.split(":",1)[0]

            file_id = f"file:{source}"

            if file_id in node_ids:

                edge(
                    req_id,
                    file_id,
                    "DERIVED_FROM"
                )


    # ==================================================
    # BUSINESS RULES
    # ==================================================

    for rule in analysis.get(
        "business_rules",
        []
    ):

        rule_id = (
            f"rule:{rule.get('id')}"
        )


        node(
            rule_id,
            "business_rule",
            rule.get("name"),
            rule
        )


        for entity in rule.get(
            "entities",
            []
        ):

            entity_id = (
                f"entity:{entity}"
            )


            node(
                entity_id,
                "business_entity",
                entity
            )


            edge(
                rule_id,
                entity_id,
                "APPLIES_TO"
            )


        for evidence in rule.get(
            "evidence",
            []
        ):

            source = evidence.split(
                ":",
                1
            )[0]


            file_id = f"file:{source}"


            if file_id in node_ids:

                edge(
                    rule_id,
                    file_id,
                    "SUPPORTED_BY"
                )


    # ==================================================
    # BUSINESS ENTITIES
    # ==================================================

    for entity in analysis.get(
        "entities",
        []
    ):

        entity_id = (
            f"entity:{entity.get('name')}"
        )


        node(
            entity_id,
            "business_entity",
            entity.get("name"),
            entity
        )


    # ==================================================
    # WORKFLOWS
    # ==================================================

    for workflow in analysis.get(
        "workflows",
        []
    ):

        workflow_id = (
            f"workflow:{workflow.get('id')}"
        )


        node(
            workflow_id,
            "business_workflow",
            workflow.get("name"),
            workflow
        )


        for actor in workflow.get(
            "actors",
            []
        ):

            actor_id = (
                f"actor:{actor}"
            )


            node(
                actor_id,
                "business_actor",
                actor
            )


            edge(
                workflow_id,
                actor_id,
                "PERFORMED_BY"
            )


        for source in workflow.get(
            "source_files",
            []
        ):

            file_id = f"file:{source}"


            if file_id in node_ids:

                edge(
                    workflow_id,
                    file_id,
                    "IMPLEMENTED_BY"
                )


    # ==================================================
    # INTEGRATIONS
    # ==================================================

    for integration in analysis.get(
        "integrations",
        []
    ):

        integration_id = (
            f"integration:{integration.get('system')}"
        )


        node(
            integration_id,
            "external_system",
            integration.get("system"),
            integration
        )


    # ==================================================
    # MODERNIZATION
    # ==================================================

    for obs in analysis.get(
        "modernization_observations",
        []
    ):

        obs_id = (
            f"modernization:{len(nodes)}"
        )


        node(
            obs_id,
            "modernization_observation",
            obs.get("observation"),
            obs
        )


    # ==================================================
    # SUMMARY
    # ==================================================

    summary = defaultdict(int)


    for n in nodes:
        summary[n["type"]] += 1


    return {

        "nodes": nodes,

        "edges": edges,

        "summary": {

            "total_nodes": len(nodes),

            "total_edges": len(edges),

            "node_types": dict(summary),

        },
    }