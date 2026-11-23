# Supabase Auth 연결

이 앱은 Supabase Auth 이메일/비밀번호 로그인을 사용합니다.

## 필요한 환경 변수

서버에서는 기존 값을 그대로 사용합니다.

```bash
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
```

브라우저 로그인 클라이언트는 `/api/auth/config`에서 `SUPABASE_URL`과 `SUPABASE_ANON_KEY`만 받아 사용합니다.
`SUPABASE_SERVICE_ROLE_KEY`는 브라우저로 전달하지 않습니다.

## Supabase 설정

1. Supabase Dashboard에서 Authentication으로 이동합니다.
2. Providers에서 Email을 활성화합니다.
3. 개발 중 빠른 테스트가 필요하면 Confirm email을 끌 수 있습니다.
4. 실제 서비스에서는 Confirm email을 켜고, Site URL과 Redirect URLs를 배포 주소로 설정합니다.

## 구현된 흐름

- `/login`: 로그인/회원가입 화면
- `supabase.auth.signInWithPassword`: 이메일 로그인
- `supabase.auth.signUp`: 이메일 회원가입
- `supabase.auth.getSession`: 브라우저 세션 유지
- `supabase.auth.onAuthStateChange`: 로그인/로그아웃 상태 반영
- 모든 앱 API 요청에 `Authorization: Bearer <access_token>` 자동 첨부
- 서버 API는 `lib/auth.js`에서 token을 검증하고 `user.id` 기준으로 데이터를 분리

## 주의

기존 guest 문서는 `user_id = null`로 저장되어 있습니다.
로그인 후에는 로그인한 사용자의 `user_id`에 연결된 문서만 보입니다.
