from __future__ import annotations

import json
import unittest

from mapper.core import (
    DocumentValidationError,
    UNMAPPED,
    build_configuration,
    build_mapping_rows,
    extract_operations,
    parse_openapi_json,
    parse_tools_json,
    rows_from_saved_mappings,
)


TOOLS = [
    {
        "name": "get-widget",
        "description": "Get widget",
        "inputSchema": {
            "type": "object",
            "properties": {"widget_id": {"type": "string"}},
        },
    },
    {
        "name": "search-widgets",
        "description": "Search widgets",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        },
    },
]

OPENAPI = {
    "openapi": "3.1.0",
    "paths": {
        "/v1/widgets/{widget_id}": {
            "get": {"operationId": "get-widget", "summary": "Get widget"}
        },
        "/v1/widgets/search": {
            "post": {"operationId": "search-widgets", "summary": "Search widgets"}
        },
    },
}


class CoreTests(unittest.TestCase):
    def test_parse_and_extract(self) -> None:
        tools = parse_tools_json(json.dumps({"tools": TOOLS}))
        openapi = parse_openapi_json(json.dumps(OPENAPI))
        operations = extract_operations(openapi)

        self.assertEqual(len(tools), 2)
        self.assertEqual(len(operations), 2)
        self.assertEqual(operations[0]["method"], "GET")

    def test_defaults_map_and_classify_tools(self) -> None:
        operations = extract_operations(OPENAPI)
        rows = build_mapping_rows(TOOLS, operations)

        self.assertNotEqual(rows[0]["openapi_operation"], UNMAPPED)
        self.assertEqual(rows[0]["actions"], ["Read"])
        self.assertEqual(rows[1]["actions"], ["Read"])
        self.assertEqual(rows[0]["resource_access"], "Private")
        self.assertEqual(rows[0]["tool_description"], "Get widget")

    def test_generic_three_key_tool_uses_no_extended_fields(self) -> None:
        generic_tools = [
            {
                "name": "createWidget",
                "description": "Create a widget",
                "inputSchema": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                },
            }
        ]
        generic_openapi = {
            "openapi": "3.1.0",
            "paths": {
                "/v1/widgets": {
                    "post": {
                        "operationId": "create-widget",
                        "summary": "Create a widget",
                    }
                }
            },
        }
        parsed_tools = parse_tools_json(json.dumps(generic_tools))
        operations = extract_operations(generic_openapi)
        rows = build_mapping_rows(parsed_tools, operations)

        self.assertNotEqual(rows[0]["openapi_operation"], UNMAPPED)
        self.assertEqual(rows[0]["actions"], ["Write"])
        configuration = build_configuration(
            "generic", parsed_tools, generic_openapi, operations, rows
        )
        self.assertEqual(
            configuration["mappings"][0]["tool_description"], "Create a widget"
        )

    def test_unmapped_three_key_tool_infers_action_from_name(self) -> None:
        generic_tools = [
            {
                "name": "find_documents",
                "description": "Find matching documents",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]
        operations = extract_operations(OPENAPI)
        rows = build_mapping_rows(generic_tools, operations)

        self.assertEqual(rows[0]["openapi_operation"], UNMAPPED)
        self.assertEqual(rows[0]["actions"], ["Read"])

    def test_requires_common_tool_keys(self) -> None:
        with self.assertRaises(DocumentValidationError):
            parse_tools_json(json.dumps([{"name": "incomplete"}]))

    def test_configuration_keeps_unmapped_operation(self) -> None:
        operations = extract_operations(OPENAPI)
        rows = build_mapping_rows(TOOLS, operations)
        rows[1]["openapi_operation"] = UNMAPPED

        configuration = build_configuration(
            "widgets", TOOLS, OPENAPI, operations, rows
        )

        self.assertIsNone(configuration["mappings"][1]["openapi_operation_id"])
        self.assertEqual(configuration["mappings"][0]["actions"], ["Read"])

    def test_saved_mapping_round_trip(self) -> None:
        operations = extract_operations(OPENAPI)
        rows = build_mapping_rows(TOOLS, operations)
        rows[0]["actions"] = ["Read", "Modify"]
        configuration = build_configuration(
            "widgets", TOOLS, OPENAPI, operations, rows
        )

        restored = rows_from_saved_mappings(
            TOOLS, operations, configuration["mappings"]
        )

        self.assertEqual(restored[0]["actions"], ["Read", "Modify"])
        self.assertEqual(
            restored[0]["openapi_operation"], rows[0]["openapi_operation"]
        )

    def test_rejects_missing_actions(self) -> None:
        operations = extract_operations(OPENAPI)
        rows = build_mapping_rows(TOOLS, operations)
        rows[0]["actions"] = []

        with self.assertRaises(DocumentValidationError):
            build_configuration("widgets", TOOLS, OPENAPI, operations, rows)


if __name__ == "__main__":
    unittest.main()
