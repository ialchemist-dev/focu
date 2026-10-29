CREATE TABLE sources (
 source_id TEXT PRIMARY KEY, canonical_url TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL, adapter TEXT NOT NULL, identity_version INTEGER NOT NULL
);
CREATE TABLE subscriptions (
 source_id TEXT PRIMARY KEY REFERENCES sources(source_id), channel_id TEXT NOT NULL,
 enabled INTEGER NOT NULL, settings_json TEXT NOT NULL
);
CREATE TABLE fetch_state (
 source_id TEXT PRIMARY KEY REFERENCES sources(source_id), cursor_json TEXT,
 last_success_at TEXT NOT NULL
);
CREATE TABLE fetch_attempts (
 attempt_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
 status TEXT NOT NULL, error_code TEXT, message TEXT, item_count INTEGER NOT NULL,
 completeness TEXT NOT NULL, finished_at TEXT NOT NULL
);
CREATE TABLE contents (
 content_id TEXT PRIMARY KEY, canonical_url TEXT UNIQUE, provisional INTEGER NOT NULL,
 first_seen_at TEXT NOT NULL, latest_revision_id TEXT
);
CREATE TABLE content_revisions (
 revision_id TEXT PRIMARY KEY, content_id TEXT NOT NULL REFERENCES contents(content_id),
 body_hash TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, kind TEXT NOT NULL,
 published_at TEXT, fetched_at TEXT NOT NULL,
 UNIQUE(content_id, body_hash)
);
CREATE TABLE observations (
 source_id TEXT NOT NULL REFERENCES sources(source_id), native_item_id TEXT NOT NULL,
 content_id TEXT NOT NULL REFERENCES contents(content_id),
 revision_id TEXT NOT NULL REFERENCES content_revisions(revision_id),
 PRIMARY KEY(source_id, native_item_id, revision_id)
);
CREATE TABLE candidates (
 content_id TEXT PRIMARY KEY REFERENCES contents(content_id),
 state TEXT NOT NULL CHECK(state IN ('pending','expired','dismissed')), expires_at TEXT NOT NULL
);
CREATE TABLE runs (
 run_id TEXT PRIMARY KEY, episode_date TEXT NOT NULL UNIQUE, config_hash TEXT NOT NULL,
 config_json TEXT NOT NULL, output_mode TEXT NOT NULL,
 status TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE stage_runs (
 run_id TEXT NOT NULL REFERENCES runs(run_id), stage TEXT NOT NULL,
 status TEXT NOT NULL, report_json TEXT, updated_at TEXT NOT NULL,
 PRIMARY KEY(run_id, stage)
);
CREATE TABLE episodes (
 episode_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),
 channel_id TEXT NOT NULL, status TEXT NOT NULL,
 script TEXT, script_hash TEXT, artifact_manifest TEXT, last_error TEXT,
 UNIQUE(run_id, channel_id)
);
CREATE TABLE episode_items (
 episode_id TEXT NOT NULL REFERENCES episodes(episode_id),
 content_id TEXT NOT NULL REFERENCES contents(content_id),
 revision_id TEXT NOT NULL REFERENCES content_revisions(revision_id),
 position INTEGER NOT NULL, unit_json TEXT NOT NULL,
 PRIMARY KEY(episode_id, content_id)
);
CREATE TABLE coverage (
 content_id TEXT PRIMARY KEY REFERENCES contents(content_id),
 episode_id TEXT NOT NULL REFERENCES episodes(episode_id), finalized_at TEXT NOT NULL
);
CREATE INDEX observations_content ON observations(content_id);
CREATE INDEX candidate_pending ON candidates(state, expires_at);
PRAGMA user_version = 1;
