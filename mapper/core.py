from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, Iterable


HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head", "trace")
ACTIONS = ("Read", "Write", "Modify")
RESOURCE_ACCESS = ("Private", "Open-public", "target-access")
CONFIG_STATUSES = ("draft", "completed")
UNMAPPED = "— 미매핑 —"


class DocumentValidationError(ValueError):
    """Raised when an uploaded document is not a supported JSON structure."""


def _decode_json(raw: bytes | str, label: str) -> Any:
    try:
        text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
        return json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DocumentValidationError(f"{label}이(가) 올바른 JSON 파일이 아닙니다: {exc}") from exc


def parse_tools_json(raw: bytes | str) -> list[dict[str, Any]]:
    document = _decode_json(raw, "tools.json")
    tools = document.get("tools") if isinstance(document, dict) else document

    if not isinstance(tools, list) or not tools:
        raise DocumentValidationError(
            "tools.json은 비어 있지 않은 배열이거나 {'tools': [...]} 형태여야 합니다."
        )

    normalized: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for index, tool in enumerate(tools, start=1):
        if not isinstance(tool, dict):
            raise DocumentValidationError(f"tools.json의 {index}번째 항목이 객체가 아닙니다.")
        name = tool.get("name")
        description = tool.get("description")
        input_schema = tool.get("inputSchema")
        if not isinstance(name, str) or not name.strip():
            raise DocumentValidationError(f"tools.json의 {index}번째 항목에 name이 없습니다.")
        name = name.strip()
        if not isinstance(description, str):
            raise DocumentValidationError(
                f"{name}: description은 문자열이어야 합니다."
            )
        if not isinstance(input_schema, dict):
            raise DocumentValidationError(
                f"{name}: inputSchema는 객체여야 합니다."
            )
        if name in seen_names:
            raise DocumentValidationError(f"중복된 tool 이름이 있습니다: {name}")
        seen_names.add(name)
        normalized.append(tool)

    return normalized


def parse_openapi_json(raw: bytes | str) -> dict[str, Any]:
    document = _decode_json(raw, "openapi.json")
    if not isinstance(document, dict):
        raise DocumentValidationError("openapi.json의 최상위 값은 객체여야 합니다.")
    if not isinstance(document.get("paths"), dict) or not document["paths"]:
        raise DocumentValidationError("openapi.json에 비어 있지 않은 paths 객체가 필요합니다.")
    return document


def operation_key(method: str, path: str, operation_id: str) -> str:
    return f"{method.upper()} {path} · {operation_id}"


def extract_operations(openapi_document: dict[str, Any]) -> list[dict[str, str]]:
    operations: list[dict[str, str]] = []
    for path, path_item in openapi_document.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            operation_id = str(operation.get("operationId") or f"{method}-{path}").strip()
            operations.append(
                {
                    "key": operation_key(method, path, operation_id),
                    "operation_id": operation_id,
                    "method": method.upper(),
                    "path": path,
                    "summary": str(operation.get("summary") or ""),
                    "description": str(operation.get("description") or ""),
                }
            )

    if not operations:
        raise DocumentValidationError("openapi.json의 paths에서 operation을 찾지 못했습니다.")
    return operations


def _canonical(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _tokens(*values: Any) -> set[str]:
    words: set[str] = set()
    for value in values:
        separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value or ""))
        words.update(re.findall(r"[a-z0-9]+", separated.lower()))
    return words


def default_operation_for_tool(
    tool: dict[str, Any], operations: list[dict[str, str]]
) -> str:
    name = tool["name"].strip()
    description = tool["description"].strip()

    exact_name = [op for op in operations if op["operation_id"] == name]
    if len(exact_name) == 1:
        return exact_name[0]["key"]

    canonical_name = _canonical(name)
    normalized_name = [
        op for op in operations if _canonical(op["operation_id"]) == canonical_name
    ]
    if len(normalized_name) == 1:
        return normalized_name[0]["key"]

    if description:
        canonical_description = _canonical(description)
        description_matches = [
            op
            for op in operations
            if any(
                value and _canonical(value) == canonical_description
                for value in (op["summary"], op["description"])
            )
        ]
        if len(description_matches) == 1:
            return description_matches[0]["key"]

    return UNMAPPED


def default_actions(
    tool: dict[str, Any], operation: dict[str, str] | None
) -> list[str]:
    method = operation["method"] if operation else ""
    signal_tokens = _tokens(
        tool["name"],
        tool["description"],
        operation["operation_id"] if operation else "",
        operation["summary"] if operation else "",
        operation["description"] if operation else "",
    )
    read_hints = {
        "fetch",
        "find",
        "get",
        "list",
        "lookup",
        "query",
        "read",
        "retrieve",
        "search",
    }
    write_hints = {"add", "create", "insert", "publish", "send", "upload"}
    modify_hints = {
        "archive",
        "delete",
        "modify",
        "move",
        "patch",
        "remove",
        "restore",
        "set",
        "update",
    }

    if method in {"GET", "HEAD", "OPTIONS"}:
        return ["Read"]
    if method == "POST" and signal_tokens & read_hints:
        return ["Read"]
    if method == "POST":
        return ["Write"]
    if method in {"PUT", "PATCH", "DELETE"}:
        return ["Modify"]

    inferred: list[str] = []
    if signal_tokens & read_hints:
        inferred.append("Read")
    if signal_tokens & write_hints:
        inferred.append("Write")
    if signal_tokens & modify_hints:
        inferred.append("Modify")
    return inferred


def build_mapping_rows(
    tools: list[dict[str, Any]], operations: list[dict[str, str]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    operations_by_key = {operation["key"]: operation for operation in operations}
    for tool in tools:
        selected_key = default_operation_for_tool(tool, operations)
        selected_operation = operations_by_key.get(selected_key)
        rows.append(
            {
                "tool_name": tool["name"],
                "tool_description": tool["description"],
                "openapi_operation": selected_key,
                "actions": default_actions(tool, selected_operation),
                "handled_resource": "",
                "resource_access": "Private",
            }
        )
    return rows


def rows_from_saved_mappings(
    tools: list[dict[str, Any]],
    operations: list[dict[str, str]],
    mappings: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = build_mapping_rows(tools, operations)
    saved_by_tool = {
        str(mapping.get("tool_name")): mapping
        for mapping in mappings
        if isinstance(mapping, dict) and mapping.get("tool_name")
    }
    operation_keys = {operation["key"] for operation in operations}

    for row in rows:
        saved = saved_by_tool.get(row["tool_name"])
        if not saved:
            continue
        saved_key = str(saved.get("openapi_operation_key") or UNMAPPED)
        row["openapi_operation"] = saved_key if saved_key in operation_keys else UNMAPPED
        row["actions"] = [
            action for action in saved.get("actions", []) if action in ACTIONS
        ]
        handled_resource = saved.get("handled_resource")
        row["handled_resource"] = (
            handled_resource if isinstance(handled_resource, str) else ""
        )
        scope = saved.get("resource_access")
        row["resource_access"] = scope if scope in RESOURCE_ACCESS else "Private"
    return rows


def validate_mapping_rows(
    tools: list[dict[str, Any]],
    operations: list[dict[str, str]],
    rows: list[dict[str, Any]],
    require_actions: bool = True,
) -> list[str]:
    errors: list[str] = []
    expected_names = {tool["name"] for tool in tools}
    row_names = {str(row.get("tool_name")) for row in rows}
    if len(rows) != len(tools) or row_names != expected_names:
        errors.append("tool 목록과 편집된 매핑 행이 일치하지 않습니다.")

    valid_operation_keys = {operation["key"] for operation in operations}
    for row in rows:
        name = str(row.get("tool_name") or "(이름 없음)")
        selected = row.get("openapi_operation")
        if selected != UNMAPPED and selected not in valid_operation_keys:
            errors.append(f"{name}: 존재하지 않는 OpenAPI operation입니다.")
        actions = row.get("actions")
        if require_actions and (not isinstance(actions, list) or not actions):
            errors.append(f"{name}: Read / Write / Modify 중 하나 이상을 선택하세요.")
        elif isinstance(actions, list) and any(action not in ACTIONS for action in actions):
            errors.append(f"{name}: 허용되지 않은 동작 분류가 있습니다.")
        handled_resource = row.get("handled_resource", "")
        if not isinstance(handled_resource, str):
            errors.append(f"{name}: 처리 리소스는 텍스트로 입력하세요.")
        elif len(handled_resource) > 200:
            errors.append(f"{name}: 처리 리소스는 200자 이하여야 합니다.")
        if row.get("resource_access") not in RESOURCE_ACCESS:
            errors.append(f"{name}: 리소스 공개 범위를 선택하세요.")
    return errors


def build_configuration(
    server_name: str,
    tools: list[dict[str, Any]],
    openapi_document: dict[str, Any],
    operations: list[dict[str, str]],
    rows: list[dict[str, Any]],
    status: str = "completed",
) -> dict[str, Any]:
    server_name = server_name.strip()
    if not server_name:
        raise DocumentValidationError("서버 이름을 입력하세요.")
    if len(server_name) > 100:
        raise DocumentValidationError("서버 이름은 100자 이하여야 합니다.")
    if status not in CONFIG_STATUSES:
        raise DocumentValidationError(f"지원하지 않는 저장 상태입니다: {status}")

    errors = validate_mapping_rows(
        tools,
        operations,
        rows,
        require_actions=status == "completed",
    )
    if errors:
        raise DocumentValidationError("\n".join(errors))

    operations_by_key = {operation["key"]: operation for operation in operations}
    mappings: list[dict[str, Any]] = []
    for row in rows:
        selected_key = str(row["openapi_operation"])
        selected_operation = operations_by_key.get(selected_key)
        mappings.append(
            {
                "tool_name": row["tool_name"],
                "tool_description": row["tool_description"],
                "openapi_operation_key": (
                    selected_operation["key"] if selected_operation else None
                ),
                "openapi_operation_id": (
                    selected_operation["operation_id"] if selected_operation else None
                ),
                "openapi_method": (
                    selected_operation["method"] if selected_operation else None
                ),
                "openapi_path": (
                    selected_operation["path"] if selected_operation else None
                ),
                "actions": list(row.get("actions") or []),
                "handled_resource": row.get("handled_resource", "").strip(),
                "resource_access": row["resource_access"],
            }
        )

    return {
        "schema_version": 3,
        "server_name": server_name,
        "status": status,
        "tools_json": tools,
        "openapi_json": openapi_document,
        "mappings": mappings,
        "updated_at": datetime.now(UTC).isoformat(),
    }
