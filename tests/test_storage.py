from __future__ import annotations

import unittest
from typing import Any

from mapper.storage import SupabaseRepository


class FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeTable:
    def __init__(self) -> None:
        self.mode = ""
        self.server_name = ""
        self.executed_modes: list[str] = []

    def upsert(self, record: dict[str, Any], on_conflict: str) -> "FakeTable":
        self.mode = "upsert"
        self.server_name = record["server_name"]
        return self

    def select(self, columns: str) -> "FakeTable":
        self.mode = "read_back"
        return self

    def eq(self, column: str, value: str) -> "FakeTable":
        self.server_name = value
        return self

    def single(self) -> "FakeTable":
        return self

    def execute(self) -> FakeResponse:
        self.executed_modes.append(self.mode)
        if self.mode == "upsert":
            return FakeResponse([])
        return FakeResponse({"id": "config-id", "server_name": self.server_name})


class FakeClient:
    def __init__(self) -> None:
        self.fake_table = FakeTable()

    def table(self, table_name: str) -> FakeTable:
        return self.fake_table


class StorageTests(unittest.TestCase):
    def test_empty_upsert_response_is_confirmed_with_read_back(self) -> None:
        repository = SupabaseRepository.__new__(SupabaseRepository)
        repository._client = FakeClient()
        configuration = {
            "schema_version": 3,
            "server_name": "widgets",
            "status": "draft",
            "tools_json": [],
            "openapi_json": {},
            "mappings": [],
        }

        saved = repository.save_configuration(configuration)

        self.assertEqual(saved["server_name"], "widgets")
        self.assertEqual(
            repository._client.fake_table.executed_modes,
            ["upsert", "read_back"],
        )


if __name__ == "__main__":
    unittest.main()
