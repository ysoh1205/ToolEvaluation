from __future__ import annotations

from typing import Any

from supabase import Client, create_client


class SupabaseRepository:
    """Small persistence boundary around the Supabase Python client."""

    TABLE = "tool_mapping_configs"

    def __init__(self, url: str, service_role_key: str) -> None:
        if not url or not service_role_key:
            raise ValueError("Supabase URL과 service role key가 모두 필요합니다.")
        self._client: Client = create_client(url, service_role_key)

    def list_configurations(self) -> list[dict[str, Any]]:
        try:
            response = (
                self._client.table(self.TABLE)
                .select("id,server_name,status,updated_at")
                .order("updated_at", desc=True)
                .limit(100)
                .execute()
            )
            return list(response.data or [])
        except Exception:
            response = (
                self._client.table(self.TABLE)
                .select("id,server_name,updated_at")
                .order("updated_at", desc=True)
                .limit(100)
                .execute()
            )
            configurations = list(response.data or [])
            for configuration in configurations:
                configuration["status"] = "completed"
            return configurations

    def get_configuration(self, config_id: str) -> dict[str, Any]:
        response = (
            self._client.table(self.TABLE)
            .select("*")
            .eq("id", config_id)
            .single()
            .execute()
        )
        if not response.data:
            raise LookupError("저장된 구성을 찾지 못했습니다.")
        return dict(response.data)

    def save_configuration(self, configuration: dict[str, Any]) -> dict[str, Any]:
        record = {
            "schema_version": configuration["schema_version"],
            "server_name": configuration["server_name"],
            "status": configuration["status"],
            "tools_json": configuration["tools_json"],
            "openapi_json": configuration["openapi_json"],
            "mappings": configuration["mappings"],
        }
        response = (
            self._client.table(self.TABLE)
            .upsert(record, on_conflict="server_name")
            .execute()
        )
        if response.data:
            return dict(response.data[0])

        read_back = (
            self._client.table(self.TABLE)
            .select("*")
            .eq("server_name", configuration["server_name"])
            .single()
            .execute()
        )
        if not read_back.data:
            raise RuntimeError("저장 결과를 다시 확인하지 못했습니다.")
        return dict(read_back.data)
