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
        "method": "get",
        "pathTemplate": "/v1/widgets/{widget_id}",
        "operationId": "get-widget",
    },
    {
        "name": "search-widgets",
        "method": "post",
        "pathTemplate": "/v1/widgets/search",
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

