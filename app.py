from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd
import streamlit as st

from mapper.core import (
    ACTIONS,
    RESOURCE_ACCESS,
    UNMAPPED,
    DocumentValidationError,
    build_configuration,
    build_mapping_rows,
    extract_operations,
    parse_openapi_json,
    parse_tools_json,
    rows_from_saved_mappings,
    validate_mapping_rows,
)
from mapper.storage import SupabaseRepository


st.set_page_config(
    page_title="Operation Atlas",
    page_icon="◫",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      [data-testid="stAppViewContainer"] {
        background:
          radial-gradient(circle at 93% 3%, rgba(91, 91, 214, .10), transparent 24rem),
          #f7f7f5;
      }
      [data-testid="stHeader"] { background: transparent; }
      [data-testid="stSidebar"] {
        border-right: 1px solid #e4e4df;
        background: #f0f0ec;
      }
      .block-container { max-width: 1440px; padding-top: 2.4rem; }
      .atlas-kicker {
        color: #5b5bd6; font-size: .76rem; font-weight: 800;
        letter-spacing: .14em; text-transform: uppercase; margin-bottom: .55rem;
      }
      .atlas-title {
        color: #202124; font-size: clamp(2rem, 4vw, 3.65rem);
        font-weight: 750; letter-spacing: -.055em; line-height: 1.02;
        max-width: 850px; margin: 0;
      }
      .atlas-subtitle {
        color: #656760; font-size: 1.05rem; line-height: 1.65;
        max-width: 720px; margin: 1rem 0 2rem;
      }
      .atlas-step {
        display: inline-flex; align-items: center; gap: .55rem;
        border: 1px solid #deded8; border-radius: 999px; background: #fff;
        color: #5a5c55; font-size: .82rem; font-weight: 650;
        margin: 0 .35rem .55rem 0; padding: .45rem .72rem;
      }
      .atlas-step b {
        align-items: center; background: #ececfa; border-radius: 999px;
        color: #5050c4; display: inline-flex; height: 1.35rem;
        justify-content: center; width: 1.35rem;
      }
      .atlas-empty {
        background: rgba(255,255,255,.72); border: 1px dashed #cfcfc7;
        border-radius: 18px; color: #656760; margin-top: 2rem;
        padding: 2.2rem; text-align: center;
      }
      .connection-ok, .connection-off {
        border-radius: 10px; font-size: .82rem; margin: .3rem 0 1rem;
        padding: .65rem .75rem;
      }
      .connection-ok { background:#e8f6ef; color:#18704a; }
      .connection-off { background:#fff4dc; color:#7b5700; }
      [data-testid="stMetric"] {
        background: rgba(255,255,255,.8); border: 1px solid #e2e2dd;
        border-radius: 14px; padding: .85rem 1rem;
      }
      [data-testid="stDataEditor"] {
        border: 1px solid #dfdfda; border-radius: 14px; overflow: hidden;
      }
      .stButton > button, .stDownloadButton > button { border-radius: 10px; }
    </style>
    """,
    unsafe_allow_html=True,
)


def setting(name: str) -> str:
    value = os.getenv(name, "")
    if value:
        return value
    try:
        return str(st.secrets.get(name, ""))
    except FileNotFoundError:
        return ""


@st.cache_resource(show_spinner=False)
def get_repository(url: str, key: str) -> SupabaseRepository:
    return SupabaseRepository(url, key)


def repository_or_none() -> SupabaseRepository | None:
    url = setting("SUPABASE_URL")
    key = setting("SUPABASE_SERVICE_ROLE_KEY")
    return get_repository(url, key) if url and key else None


def set_workspace(
    server_name: str,
    tools: list[dict[str, Any]],
    openapi_document: dict[str, Any],
    mappings: list[dict[str, Any]] | None = None,
) -> None:
    operations = extract_operations(openapi_document)
    rows = (
        rows_from_saved_mappings(tools, operations, mappings)
        if mappings is not None
        else build_mapping_rows(tools, operations)
    )
    st.session_state.workspace = {
        "server_name": server_name,
        "tools": tools,
        "openapi": openapi_document,
        "operations": operations,
        "rows": rows,
    }
    st.session_state.pending_server_name = server_name
    st.session_state.editor_version = st.session_state.get("editor_version", 0) + 1


def parse_editor_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = frame.to_dict(orient="records")
    for row in rows:
        actions = row.get("actions")
        row["actions"] = list(actions) if isinstance(actions, (list, tuple)) else []
    return rows


repo = repository_or_none()

if "pending_server_name" in st.session_state:
    st.session_state.server_name_input = st.session_state.pop("pending_server_name")

with st.sidebar:
    st.markdown("## Operation Atlas")
    st.caption("Tool ↔ OpenAPI mapping registry")

    if repo:
        st.markdown(
            '<div class="connection-ok">● Supabase 연결됨</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="connection-off">● 로컬 편집 모드 · Supabase 설정 필요</div>',
            unsafe_allow_html=True,
        )

    with st.form("document_input", clear_on_submit=False):
        st.markdown("### 새 구성")
        server_name_input = st.text_input(
            "서버 이름",
            key="server_name_input",
            placeholder="예: notion",
            max_chars=100,
        )
        tools_file = st.file_uploader("tools.json", type=["json"], key="tools_file")
        openapi_file = st.file_uploader(
            "openapi.json", type=["json"], key="openapi_file"
        )
        analyze = st.form_submit_button(
            "파일 분석하기", type="primary", width="stretch"
        )

    if analyze:
        if not server_name_input.strip() or not tools_file or not openapi_file:
            st.error("서버 이름과 두 JSON 파일을 모두 입력하세요.")
        else:
            try:
                parsed_tools = parse_tools_json(tools_file.getvalue())
                parsed_openapi = parse_openapi_json(openapi_file.getvalue())
                set_workspace(server_name_input, parsed_tools, parsed_openapi)
                st.rerun()
            except DocumentValidationError as exc:
                st.error(str(exc))

    if repo:
        st.divider()
        st.markdown("### 저장된 구성")
        try:
            saved_configs = repo.list_configurations()
            if saved_configs:
                labels = {
                    f"{item['server_name']} · {str(item.get('updated_at', ''))[:10]}": item[
                        "id"
                    ]
                    for item in saved_configs
                }
                selected_label = st.selectbox(
                    "불러올 서버",
                    options=list(labels),
                    label_visibility="collapsed",
                )
                if st.button("구성 불러오기", width="stretch"):
                    saved = repo.get_configuration(labels[selected_label])
                    set_workspace(
                        saved["server_name"],
                        saved["tools_json"],
                        saved["openapi_json"],
                        saved.get("mappings", []),
                    )
                    st.rerun()
            else:
                st.caption("아직 저장된 구성이 없습니다.")
        except Exception:
            st.warning("저장 목록을 불러오지 못했습니다. Supabase 설정을 확인하세요.")

st.markdown('<div class="atlas-kicker">Operation governance workspace</div>', unsafe_allow_html=True)
st.markdown(
    '<h1 class="atlas-title">도구와 API 사이의 관계를<br>한눈에 정리하세요.</h1>',
    unsafe_allow_html=True,
)
st.markdown(
    """
    <p class="atlas-subtitle">
      tool마다 대응되는 OpenAPI operation, 허용 동작, 리소스 접근 범위를 지정하고
      서버 단위 구성으로 저장합니다.
    </p>
    <div>
      <span class="atlas-step"><b>1</b> JSON 입력</span>
      <span class="atlas-step"><b>2</b> 매핑 검토</span>
      <span class="atlas-step"><b>3</b> 분류 및 저장</span>
    </div>
    """,
    unsafe_allow_html=True,
)

workspace = st.session_state.get("workspace")
if not workspace:
    st.markdown(
        """
        <div class="atlas-empty">
          <strong>왼쪽에서 첫 구성을 시작하세요.</strong><br>
          서버 이름, tools.json, openapi.json을 입력하면 자동 매핑 초안을 만듭니다.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

st.divider()
st.markdown(f"### `{server_name_input.strip() or workspace['server_name']}` 매핑")
st.caption(
    "자동으로 연결된 초안을 검토하세요. 미매핑을 의도적으로 선택해 저장할 수도 있습니다."
)

rows = workspace["rows"]
operations = workspace["operations"]
metric_cols = st.columns(4)
metric_cols[0].metric("Tools", len(rows))
metric_cols[1].metric("Operations", len(operations))
metric_cols[2].metric(
    "자동 매핑", sum(row["openapi_operation"] != UNMAPPED for row in rows)
)
metric_cols[3].metric(
    "미매핑", sum(row["openapi_operation"] == UNMAPPED for row in rows)
)

operation_options = [UNMAPPED] + [operation["key"] for operation in operations]
editor_frame = pd.DataFrame(rows)
edited_frame = st.data_editor(
    editor_frame,
    key=f"mapping_editor_{st.session_state.get('editor_version', 0)}",
    width="stretch",
    hide_index=True,
    num_rows="fixed",
    height=min(800, 42 + max(1, len(rows)) * 35),
    column_order=[
        "tool_name",
        "tool_description",
        "openapi_operation",
        "actions",
        "resource_access",
    ],
    column_config={
        "tool_name": st.column_config.TextColumn(
            "Tool", help="tools.json의 tool 이름", disabled=True, width="medium"
        ),
        "tool_description": st.column_config.TextColumn(
            "Description",
            help="tools.json의 tool 설명",
            disabled=True,
            width="large",
        ),
        "openapi_operation": st.column_config.SelectboxColumn(
            "OpenAPI operation",
            options=operation_options,
            required=True,
            width="large",
        ),
        "actions": st.column_config.MultiselectColumn(
            "동작",
            options=list(ACTIONS),
            required=True,
            width="medium",
        ),
        "resource_access": st.column_config.SelectboxColumn(
            "Resource access",
            options=list(RESOURCE_ACCESS),
            required=True,
            width="medium",
        ),
    },
)
edited_rows = parse_editor_rows(edited_frame)
workspace["rows"] = edited_rows

errors = validate_mapping_rows(workspace["tools"], operations, edited_rows)
unmapped_count = sum(row["openapi_operation"] == UNMAPPED for row in edited_rows)
if errors:
    st.error(errors[0] if len(errors) == 1 else f"{len(errors)}개 항목을 확인하세요: {errors[0]}")
elif unmapped_count:
    st.info(f"미매핑 tool {unmapped_count}개가 있습니다. 의도한 상태라면 그대로 저장할 수 있습니다.")

try:
    configuration = build_configuration(
        server_name_input,
        workspace["tools"],
        workspace["openapi"],
        operations,
        edited_rows,
    )
except DocumentValidationError:
    configuration = None

action_cols = st.columns([1.2, 1.2, 4])
with action_cols[0]:
    save_clicked = st.button(
        "Supabase에 저장",
        type="primary",
        width="stretch",
        disabled=repo is None or configuration is None,
    )
with action_cols[1]:
    if configuration:
        st.download_button(
            "JSON 내보내기",
            data=json.dumps(configuration, ensure_ascii=False, indent=2),
            file_name=f"{configuration['server_name']}-tool-mapping.json",
            mime="application/json",
            width="stretch",
        )
with action_cols[2]:
    if repo is None:
        st.caption("저장을 활성화하려면 Supabase URL과 service role key를 설정하세요.")

if save_clicked and repo and configuration:
    try:
        repo.save_configuration(configuration)
        st.toast("구성을 Supabase에 저장했습니다.", icon="✅")
    except Exception:
        st.error("저장하지 못했습니다. Supabase 테이블과 연결 설정을 확인하세요.")
