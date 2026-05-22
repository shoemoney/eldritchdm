-- EldritchDM local SQLite schema
-- This file is the verbatim DDL from CONTEXT D-18.
-- It holds Discord-specific bookkeeping ONLY.
-- Gameplay state lives in dm20's ~/.omlx/dm.db — we never touch it.
--
-- Bootstrap: python -m eldritch_dm.persistence.bootstrap
-- Run idempotently: CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS
--
-- WARNING: schema.sql is read by bootstrap.py from a package-relative path.
-- Its sha256 is logged at every bootstrap run for tamper-observability (T-01-01, T-01-05).

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS channel_sessions (
    channel_id TEXT PRIMARY KEY,
    campaign_name TEXT NOT NULL,
    claudmaster_session_id TEXT,
    dm20_party_token TEXT,
    state TEXT NOT NULL DEFAULT 'LOBBY'
        CHECK(state IN ('LOBBY','EXPLORATION','COMBAT_INIT','COMBAT','NPC_DLG','PAUSED')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS persistent_views (
    custom_id TEXT PRIMARY KEY,
    view_class TEXT NOT NULL,
    message_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(channel_id) REFERENCES channel_sessions(channel_id) ON DELETE CASCADE
);

-- Phase 5 Plan 01 note: an additive `consumed_in_round INTEGER` column is added
-- at bootstrap time via an idempotent ALTER TABLE in persistence/bootstrap.py.
-- It is NOT included in this CREATE TABLE so existing self-host DBs (Phase 1+)
-- remain compatible — the migration is a no-op on already-migrated DBs.
-- The column shimmies dm20's missing reaction-budget tracking (RESEARCH Q1):
-- when a Riposte is consumed, we record the round so the eligibility check can
-- enforce "one reaction per round per PC".
CREATE TABLE IF NOT EXISTS riposte_timers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    character_id TEXT NOT NULL,        -- dm20 character id
    user_id TEXT NOT NULL,             -- Discord user id (gatekeeping)
    monster_uuid TEXT,                  -- dm20 monster uuid that missed
    weapon_used TEXT,
    message_id TEXT NOT NULL,          -- the ephemeral message hosting the button
    custom_id TEXT NOT NULL,
    deadline_ts TIMESTAMP NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','consumed','expired','cancelled')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(channel_id) REFERENCES channel_sessions(channel_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sanitizer_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    raw_input TEXT NOT NULL,
    stripped_tokens TEXT NOT NULL DEFAULT '[]', -- JSON array of strings
    redacted_output TEXT NOT NULL,
    truncated INTEGER NOT NULL DEFAULT 0 CHECK(truncated IN (0,1)),
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- combat_conditions: local tracking for dm20-shimmed conditions (e.g. dodging).
-- dm20 has no built-in "dodging" condition (04-RESEARCH.md Q2 finding).
-- This table stores bot-side condition timers; expires_round clears on dodger's
-- next turn start. The LLM receives "X is dodging" in the narrative context;
-- v1 dodge is narrative-only (no mechanical to-hit modification in combat_action).
-- Phase 5 will wire disadvantage to incoming attacks when dm20 supports it.
CREATE TABLE IF NOT EXISTS combat_conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    condition_kind TEXT NOT NULL,        -- 'dodging' for v1; expand later
    expires_round INTEGER NOT NULL,      -- cleared at start of dodger next turn
    applied_round INTEGER NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(channel_id) REFERENCES channel_sessions(channel_id) ON DELETE CASCADE
);

-- Phase 5 Plan 01: per-character subclass at Discord-bot side.
-- dm20's `get_character` text output OMITS subclass (RESEARCH Q2 finding),
-- so the bot must persist (class_name, subclass) at character-ingest time
-- to perform Riposte eligibility checks (Battle Master Fighter, RAW).
-- class_name and subclass are stored case-folded + whitespace-collapsed by the
-- repo so eligibility comparisons are stable regardless of input casing.
CREATE TABLE IF NOT EXISTS pc_classes (
    channel_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    class_name TEXT NOT NULL,
    subclass TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (channel_id, character_id),
    FOREIGN KEY (channel_id) REFERENCES channel_sessions(channel_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_views_channel ON persistent_views(channel_id);
CREATE INDEX IF NOT EXISTS idx_riposte_channel ON riposte_timers(channel_id);
CREATE INDEX IF NOT EXISTS idx_riposte_pending_deadline
    ON riposte_timers(status, deadline_ts) WHERE status='pending';
CREATE INDEX IF NOT EXISTS idx_conditions_channel_active ON combat_conditions(channel_id, character_id, condition_kind);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON sanitizer_audit(ts);
