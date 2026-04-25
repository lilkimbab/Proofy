CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS auth_users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app_state (
    user_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    content_bundle_id TEXT NOT NULL,
    active_lesson_id TEXT NOT NULL,
    active_problem_set_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    profile JSONB NOT NULL,
    mastery JSONB NOT NULL,
    plan JSONB NOT NULL,
    lesson JSONB NOT NULL,
    practice_problem_set JSONB NOT NULL,
    practice_problem JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_bundles (
    bundle_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    version TEXT NOT NULL,
    domain TEXT NOT NULL,
    lesson_pack_count INTEGER NOT NULL DEFAULT 0,
    problem_set_count INTEGER NOT NULL DEFAULT 0,
    diagnostic_question_count INTEGER NOT NULL DEFAULT 0,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_diagnostic_questions (
    question_id TEXT PRIMARY KEY,
    bundle_id TEXT NOT NULL,
    ordering INTEGER NOT NULL,
    concept_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    options JSONB NOT NULL,
    answer_index INTEGER NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_lesson_packs (
    lesson_pack_id TEXT PRIMARY KEY,
    bundle_id TEXT NOT NULL,
    title TEXT NOT NULL,
    unit_title TEXT NOT NULL,
    teacher_name TEXT NOT NULL,
    concept_ids JSONB NOT NULL,
    question_starters JSONB NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_lesson_scenes (
    scene_id TEXT PRIMARY KEY,
    lesson_pack_id TEXT NOT NULL,
    ordering INTEGER NOT NULL,
    title TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_problem_sets (
    problem_set_id TEXT PRIMARY KEY,
    bundle_id TEXT NOT NULL,
    lesson_pack_id TEXT NOT NULL,
    title TEXT NOT NULL,
    concept_ids JSONB NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_curriculum_nodes (
    node_id TEXT PRIMARY KEY,
    bundle_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    course_title TEXT NOT NULL,
    unit_title TEXT NOT NULL,
    pdf_pages TEXT NOT NULL,
    content_elements JSONB NOT NULL,
    achievement_codes JSONB NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_problems (
    problem_id TEXT PRIMARY KEY,
    problem_set_id TEXT NOT NULL,
    ordering INTEGER NOT NULL,
    title TEXT NOT NULL,
    statement TEXT NOT NULL,
    function_spec JSONB NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS problem_attempts (
    attempt_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    problem_id TEXT NOT NULL,
    solved BOOLEAN NOT NULL,
    score INTEGER NOT NULL,
    summary TEXT NOT NULL,
    submitted JSONB NOT NULL,
    evaluated_steps JSONB NOT NULL,
    recovery_plan JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_problem_attempts_user_created_at
    ON problem_attempts (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS content_review_jobs (
    review_job_id TEXT PRIMARY KEY,
    source_provider TEXT NOT NULL,
    bundle_id TEXT NOT NULL,
    status TEXT NOT NULL,
    approved_problem_count INTEGER NOT NULL DEFAULT 0,
    rejected_problem_count INTEGER NOT NULL DEFAULT 0,
    raw_bundle JSONB NOT NULL,
    approved_bundle JSONB NOT NULL,
    report JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_review_items (
    item_id TEXT PRIMARY KEY,
    review_job_id TEXT NOT NULL,
    problem_id TEXT NOT NULL,
    problem_set_id TEXT NOT NULL,
    status TEXT NOT NULL,
    reasons JSONB NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS session_events (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_session_events_session_created_at
    ON session_events (session_id, created_at ASC);
