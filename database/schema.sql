-- StudentCabinet PostgreSQL schema (3NF)
-- Run via: python database/init_db.py

CREATE SCHEMA IF NOT EXISTS content;

-- Roles
CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    code VARCHAR(32) UNIQUE NOT NULL,
    title VARCHAR(128) NOT NULL
);

-- Academic groups (from schedule Excel)
CREATE TABLE IF NOT EXISTS groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) UNIQUE NOT NULL
);

-- Users (all roles)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role_id INTEGER NOT NULL REFERENCES roles(id),
    last_name VARCHAR(128) NOT NULL,
    first_name VARCHAR(128) NOT NULL,
    middle_name VARCHAR(128),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Student profile (1:1 users with role student)
CREATE TABLE IF NOT EXISTS student_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    group_id INTEGER REFERENCES groups(id),
    student_id VARCHAR(64),
    course INTEGER,
    card_number_hash TEXT UNIQUE,
    card_number_last4 VARCHAR(8),
    pass_number VARCHAR(64),
    face_photo_path TEXT,
    study_form VARCHAR(32),
    issue_date DATE,
    course_number INTEGER,
    verification_signature TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_student_profiles_group ON student_profiles(group_id);

-- Schedule teachers reference (names from Excel)
CREATE TABLE IF NOT EXISTS schedule_teachers (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

-- Teacher profile (1:1 users with role teacher)
CREATE TABLE IF NOT EXISTS teacher_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    position_title VARCHAR(255),
    pass_number VARCHAR(64),
    department VARCHAR(255),
    office_room VARCHAR(32),
    schedule_teacher_id INTEGER REFERENCES schedule_teachers(id)
);

-- Campus places (academic buildings + dorms) in one table — already 3NF.
-- kind distinguishes objects with the same number (e.g. building 5 vs dorm 5).
-- Optional future refactor (not required for normalization): campus_place_types
-- + type_id FK (same pattern as roles), without a separate 1:1 details table.
-- See SYSTEM_OVERVIEW.txt «Карта кампуса (buildings)».
CREATE TABLE IF NOT EXISTS buildings (
    id SERIAL PRIMARY KEY,
    number INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    address TEXT,
    phone VARCHAR(64),
    image_url TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    kind VARCHAR(16) NOT NULL DEFAULT 'building' CHECK (kind IN ('building', 'dorm')),
    contact_person VARCHAR(255),
    contact_role VARCHAR(128),
    extra_info TEXT,
    UNIQUE (number, kind)
);

-- Classrooms (building-room format e.g. 5-104)
CREATE TABLE IF NOT EXISTS classrooms (
    id SERIAL PRIMARY KEY,
    building_id INTEGER REFERENCES buildings(id),
    room_suffix VARCHAR(32),
    display_name TEXT UNIQUE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_classrooms_building ON classrooms(building_id);

-- Schedule uploads
CREATE TABLE IF NOT EXISTS uploads (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(512),
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_from DATE,
    source VARCHAR(16) NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'vk')),
    vk_post_id BIGINT
);

-- Lessons (weekly template)
CREATE TABLE IF NOT EXISTS lessons (
    id SERIAL PRIMARY KEY,
    upload_id INTEGER REFERENCES uploads(id) ON DELETE SET NULL,
    group_id INTEGER NOT NULL REFERENCES groups(id),
    schedule_teacher_id INTEGER REFERENCES schedule_teachers(id),
    classroom_id INTEGER REFERENCES classrooms(id),
    day_name TEXT NOT NULL,
    lesson_number INTEGER NOT NULL,
    time_start VARCHAR(16),
    time_end VARCHAR(16),
    subject TEXT NOT NULL,
    lesson_type TEXT
);

CREATE INDEX IF NOT EXISTS idx_lessons_group ON lessons(group_id);
CREATE INDEX IF NOT EXISTS idx_lessons_day ON lessons(day_name);
CREATE INDEX IF NOT EXISTS idx_lessons_teacher ON lessons(schedule_teacher_id);

-- Cached university (vyatsu.ru) teacher busy schedule
CREATE TABLE IF NOT EXISTS teacher_external_schedule (
    teacher_user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    source VARCHAR(32) NOT NULL DEFAULT 'vyatsu',
    matched_name TEXT,
    link_status VARCHAR(64),
    payload JSONB NOT NULL DEFAULT '[]',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Office hours slots (teacher booking windows)
CREATE TABLE IF NOT EXISTS office_slots (
    id SERIAL PRIMARY KEY,
    teacher_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    slot_date DATE NOT NULL,
    time_start TIME NOT NULL,
    time_end TIME NOT NULL,
    classroom_id INTEGER REFERENCES classrooms(id),
    room_display VARCHAR(32),
    topic TEXT NOT NULL,
    max_students INTEGER NOT NULL DEFAULT 1 CHECK (max_students > 0),
    audience_type VARCHAR(16) NOT NULL DEFAULT 'anyone'
        CHECK (audience_type IN ('one_group', 'multi_group', 'anyone')),
    enable_queue BOOLEAN NOT NULL DEFAULT FALSE,
    enable_submission BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_office_slots_teacher_date ON office_slots(teacher_user_id, slot_date);

CREATE TABLE IF NOT EXISTS office_slot_groups (
    slot_id INTEGER NOT NULL REFERENCES office_slots(id) ON DELETE CASCADE,
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    PRIMARY KEY (slot_id, group_id)
);

CREATE TABLE IF NOT EXISTS office_bookings (
    id SERIAL PRIMARY KEY,
    slot_id INTEGER NOT NULL REFERENCES office_slots(id) ON DELETE CASCADE,
    student_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'confirmed', 'rejected', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (slot_id, student_user_id)
);

CREATE INDEX IF NOT EXISTS idx_office_bookings_slot ON office_bookings(slot_id);

CREATE TABLE IF NOT EXISTS office_queue_entries (
    id SERIAL PRIMARY KEY,
    slot_id INTEGER NOT NULL REFERENCES office_slots(id) ON DELETE CASCADE,
    student_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    passed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (slot_id, student_user_id)
);

CREATE INDEX IF NOT EXISTS idx_office_queue_slot ON office_queue_entries(slot_id, position);

CREATE TABLE IF NOT EXISTS office_submissions (
    id SERIAL PRIMARY KEY,
    slot_id INTEGER NOT NULL REFERENCES office_slots(id) ON DELETE CASCADE,
    student_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    stored_path TEXT NOT NULL,
    original_name TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_office_submissions_slot ON office_submissions(slot_id);

CREATE TABLE IF NOT EXISTS teacher_personal_events (
    id SERIAL PRIMARY KEY,
    teacher_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_date DATE NOT NULL,
    time_start TIME NOT NULL,
    time_end TIME NOT NULL,
    title TEXT NOT NULL,
    color VARCHAR(16),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_teacher_personal_date
    ON teacher_personal_events(teacher_user_id, event_date);

-- Calendar notes and teacher attachments per event
CREATE TABLE IF NOT EXISTS calendar_notes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_key VARCHAR(160) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    note_text TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, event_key)
);

CREATE TABLE IF NOT EXISTS calendar_attachments (
    id SERIAL PRIMARY KEY,
    teacher_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_key VARCHAR(160) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    stored_path TEXT NOT NULL,
    original_name TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_calendar_attachments_event ON calendar_attachments(event_key);

CREATE TABLE IF NOT EXISTS calendar_note_files (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_key VARCHAR(160) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    stored_path TEXT NOT NULL,
    original_name TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_calendar_note_files_user_event
    ON calendar_note_files(user_id, event_key);

-- Content schema (VK news, FAQ)
CREATE TABLE IF NOT EXISTS content.vk_news_cache (
    id SERIAL PRIMARY KEY,
    post_id BIGINT UNIQUE,
    title TEXT,
    summary TEXT,
    post_date TEXT,
    post_url TEXT,
    image_url TEXT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS qr_access_tokens (
    id SERIAL PRIMARY KEY,
    token UUID NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_type VARCHAR(16) NOT NULL CHECK (subject_type IN ('student', 'teacher')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_qr_tokens_token ON qr_access_tokens(token);
CREATE INDEX IF NOT EXISTS idx_qr_tokens_user ON qr_access_tokens(user_id);

CREATE TABLE IF NOT EXISTS content.app_settings (
    key VARCHAR(64) PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content.faq (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    source_url TEXT
);
