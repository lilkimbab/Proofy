이 폴더는 강의/문제 번들을 JSON 파일로 관리하는 저장소입니다.

- 각 파일은 `bundleId.json` 형식으로 저장됩니다.
- 기본 번들은 `python3 apps/api/scripts/sync_content_data.py` 로 다시 생성할 수 있습니다.
- 새 번들을 추가하면 메모리 저장소와 Postgres 저장소가 모두 이 폴더를 기준으로 읽습니다.
- 번들 삭제는 `DELETE /api/admin/content/{bundle_id}` 로 처리할 수 있습니다.

운영 원칙:

- 강의/문제 자산은 가능하면 코드보다 이 폴더에서 관리합니다.
- 코드에 있는 seed builder는 초기 번들을 생성하거나 업데이트할 때만 사용합니다.
- 실제 서비스에서는 이 폴더의 JSON 파일이 가장 먼저 로드됩니다.
