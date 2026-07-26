# Operation Atlas

`tools.json`의 각 tool을 OpenAPI operation과 연결하고, 동작 분류 및 리소스 접근
범위를 지정해 Supabase에 저장하는 로그인 없는 Streamlit 앱입니다.

## 기능

- 서버 이름 + `tools.json` + `openapi.json` 입력
- tool `name`/`description`과 OpenAPI `operationId`/`summary` 기반 자동 매핑 초안
- tool별 OpenAPI operation 직접 선택 및 의도적 미매핑
- `Read` / `Write` / `Modify` 복수 선택
- `Private` / `Open-public` / `target-access` 선택
- 서버 이름 기준 Supabase upsert, 저장 목록 불러오기
- 전체 원본 JSON과 매핑 결과 JSON 내보내기

## 실행

Python 3.10 이상이 필요합니다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Supabase 설정

1. Supabase SQL Editor에서
   `supabase/migrations/20260726000000_create_tool_mapping_configs.sql`을 실행합니다.
2. `.streamlit/secrets.toml.example`을 `.streamlit/secrets.toml`로 복사합니다.
3. `SUPABASE_URL`과 `SUPABASE_SERVICE_ROLE_KEY` 값을 입력합니다.

환경 변수로 같은 키를 제공해도 됩니다. service role key는 브라우저에 전달되지
않는 서버 비밀값이므로 저장소에 커밋하지 마세요. 테이블은 RLS를 활성화하고
`anon`/`authenticated` 접근을 제거했기 때문에 앱 서버만 읽고 쓸 수 있습니다.

로그인은 없으므로 앱 URL에 접근 가능한 사람은 모든 서버 구성을 열람하고
수정할 수 있습니다. 필요한 경우 배포 플랫폼의 네트워크 접근 제한을 함께
사용하세요.

## 테스트

```bash
python -m unittest discover -s tests -v
```
