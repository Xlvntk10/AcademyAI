-- Frozen V4.5 schema derived from SQLite revision 0009_offline_sync.

CREATE SCHEMA academy;

CREATE SCHEMA academy_auth;

REVOKE ALL ON SCHEMA academy, academy_auth FROM PUBLIC;

CREATE SEQUENCE academy.skill_id_seq;

CREATE SEQUENCE academy.studysettings_id_seq;

CREATE SEQUENCE academy.syncidentity_id_seq;

CREATE SEQUENCE academy.lesson_id_seq;

CREATE SEQUENCE academy.exercise_id_seq;

CREATE SEQUENCE academy.lessonprerequisite_id_seq;

CREATE SEQUENCE academy.vocabularycard_id_seq;

CREATE SEQUENCE academy.attempt_id_seq;

CREATE SEQUENCE academy.runanswer_id_seq;

CREATE SEQUENCE academy.taskmove_id_seq;


CREATE TABLE academy.ieltstest (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	id VARCHAR NOT NULL,
	section VARCHAR NOT NULL,
	title VARCHAR NOT NULL,
	instructions VARCHAR NOT NULL,
	duration_seconds INTEGER NOT NULL,
	content JSON NOT NULL,
	PRIMARY KEY (user_id, id)
)

;

CREATE INDEX ix_ieltstest_section ON academy.ieltstest (user_id, section);

ALTER TABLE academy.ieltstest ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.ieltstest FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.ieltstest USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.planweek (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	week_start DATE NOT NULL,
	revision INTEGER NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (user_id, week_start)
)

;

ALTER TABLE academy.planweek ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.planweek FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.planweek USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.skill (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	id INTEGER DEFAULT nextval('academy.skill_id_seq') NOT NULL,
	name VARCHAR NOT NULL,
	description VARCHAR NOT NULL,
	PRIMARY KEY (user_id, id)
)

;

CREATE UNIQUE INDEX ix_skill_name ON academy.skill (user_id, name);

ALTER TABLE academy.skill ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.skill FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.skill USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.studysettings (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	id INTEGER DEFAULT nextval('academy.studysettings_id_seq') NOT NULL,
	available_minutes JSON NOT NULL,
	daily_goal_minutes INTEGER NOT NULL,
	weekly_goal_minutes INTEGER NOT NULL,
	reminder_enabled BOOLEAN NOT NULL,
	reminder_time VARCHAR NOT NULL,
	timezone VARCHAR NOT NULL,
	english_percent INTEGER DEFAULT '65' NOT NULL,
	monthly_goal_minutes INTEGER DEFAULT '900' NOT NULL,
	target_month VARCHAR,
	reminder_days JSON DEFAULT '[0,1,2,3,4,5,6]' NOT NULL,
	masters_target_date DATE,
	PRIMARY KEY (user_id, id)
)

;

ALTER TABLE academy.studysettings ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.studysettings FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.studysettings USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.syncidentity (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	id INTEGER DEFAULT nextval('academy.syncidentity_id_seq') NOT NULL,
	server_id VARCHAR NOT NULL,
	PRIMARY KEY (user_id, id)
)

;

ALTER TABLE academy.syncidentity ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.syncidentity FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.syncidentity USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.ieltsrun (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	id VARCHAR NOT NULL,
	test_id VARCHAR NOT NULL,
	started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	submitted_at TIMESTAMP WITHOUT TIME ZONE,
	revision INTEGER NOT NULL,
	answers JSON NOT NULL,
	text VARCHAR NOT NULL,
	mode VARCHAR NOT NULL,
	result JSON,
	PRIMARY KEY (user_id, id),
	CONSTRAINT fk_ieltsrun_test_id FOREIGN KEY(user_id, test_id) REFERENCES academy.ieltstest (user_id, id)
)

;

CREATE INDEX ix_ieltsrun_test_id ON academy.ieltsrun (user_id, test_id);

ALTER TABLE academy.ieltsrun ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.ieltsrun FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.ieltsrun USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.lesson (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	id INTEGER DEFAULT nextval('academy.lesson_id_seq') NOT NULL,
	skill_id INTEGER NOT NULL,
	title VARCHAR NOT NULL,
	level VARCHAR NOT NULL,
	PRIMARY KEY (user_id, id),
	CONSTRAINT fk_lesson_skill_id FOREIGN KEY(user_id, skill_id) REFERENCES academy.skill (user_id, id)
)

;

CREATE INDEX ix_lesson_skill_id ON academy.lesson (user_id, skill_id);

CREATE INDEX ix_lesson_title ON academy.lesson (user_id, title);

ALTER TABLE academy.lesson ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.lesson FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.lesson USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.exercise (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	id INTEGER DEFAULT nextval('academy.exercise_id_seq') NOT NULL,
	lesson_id INTEGER NOT NULL,
	question VARCHAR NOT NULL,
	correct_answer VARCHAR NOT NULL,
	points INTEGER NOT NULL,
	PRIMARY KEY (user_id, id),
	CONSTRAINT fk_exercise_lesson_id FOREIGN KEY(user_id, lesson_id) REFERENCES academy.lesson (user_id, id)
)

;

CREATE INDEX ix_exercise_lesson_id ON academy.exercise (user_id, lesson_id);

ALTER TABLE academy.exercise ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.exercise FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.exercise USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.lessoncontent (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	lesson_id INTEGER NOT NULL,
	slug VARCHAR NOT NULL,
	summary VARCHAR NOT NULL,
	duration_minutes INTEGER NOT NULL,
	version INTEGER NOT NULL,
	theory JSON NOT NULL,
	PRIMARY KEY (user_id, lesson_id),
	CONSTRAINT fk_lessoncontent_lesson_id FOREIGN KEY(user_id, lesson_id) REFERENCES academy.lesson (user_id, id)
)

;

CREATE UNIQUE INDEX ix_lessoncontent_slug ON academy.lessoncontent (user_id, slug);

ALTER TABLE academy.lessoncontent ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.lessoncontent FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.lessoncontent USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.lessonmeta (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	lesson_id INTEGER NOT NULL,
	subject VARCHAR NOT NULL,
	topic VARCHAR NOT NULL,
	position INTEGER NOT NULL,
	PRIMARY KEY (user_id, lesson_id),
	CONSTRAINT fk_lessonmeta_lesson_id FOREIGN KEY(user_id, lesson_id) REFERENCES academy.lesson (user_id, id)
)

;

CREATE INDEX ix_lessonmeta_subject ON academy.lessonmeta (user_id, subject);

ALTER TABLE academy.lessonmeta ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.lessonmeta FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.lessonmeta USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.lessonprerequisite (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	id INTEGER DEFAULT nextval('academy.lessonprerequisite_id_seq') NOT NULL,
	lesson_id INTEGER NOT NULL,
	prerequisite_id INTEGER NOT NULL,
	PRIMARY KEY (user_id, id),
	CONSTRAINT fk_lessonprerequisite_prerequisite_id FOREIGN KEY(user_id, prerequisite_id) REFERENCES academy.lesson (user_id, id),
	CONSTRAINT fk_lessonprerequisite_lesson_id FOREIGN KEY(user_id, lesson_id) REFERENCES academy.lesson (user_id, id),
	CONSTRAINT uq_lesson_prerequisite UNIQUE (user_id, lesson_id, prerequisite_id)
)

;

CREATE INDEX ix_lessonprerequisite_lesson_id ON academy.lessonprerequisite (user_id, lesson_id);

ALTER TABLE academy.lessonprerequisite ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.lessonprerequisite FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.lessonprerequisite USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.lessonrun (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	id VARCHAR NOT NULL,
	lesson_id INTEGER NOT NULL,
	content_version INTEGER NOT NULL,
	started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	completed_at TIMESTAMP WITHOUT TIME ZONE,
	PRIMARY KEY (user_id, id),
	CONSTRAINT fk_lessonrun_lesson_id FOREIGN KEY(user_id, lesson_id) REFERENCES academy.lesson (user_id, id)
)

;

CREATE INDEX ix_lessonrun_lesson_id ON academy.lessonrun (user_id, lesson_id);

ALTER TABLE academy.lessonrun ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.lessonrun FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.lessonrun USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.vocabularycard (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	id INTEGER DEFAULT nextval('academy.vocabularycard_id_seq') NOT NULL,
	lesson_id INTEGER NOT NULL,
	term VARCHAR NOT NULL,
	translation VARCHAR NOT NULL,
	example VARCHAR NOT NULL,
	PRIMARY KEY (user_id, id),
	CONSTRAINT fk_vocabularycard_lesson_id FOREIGN KEY(user_id, lesson_id) REFERENCES academy.lesson (user_id, id),
	UNIQUE (user_id, term)
)

;

CREATE INDEX ix_vocabularycard_lesson_id ON academy.vocabularycard (user_id, lesson_id);

ALTER TABLE academy.vocabularycard ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.vocabularycard FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.vocabularycard USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.attempt (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	id INTEGER DEFAULT nextval('academy.attempt_id_seq') NOT NULL,
	exercise_id INTEGER NOT NULL,
	answer VARCHAR NOT NULL,
	is_correct BOOLEAN NOT NULL,
	earned_points INTEGER NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (user_id, id),
	CONSTRAINT fk_attempt_exercise_id FOREIGN KEY(user_id, exercise_id) REFERENCES academy.exercise (user_id, id)
)

;

CREATE INDEX ix_attempt_exercise_id ON academy.attempt (user_id, exercise_id);

ALTER TABLE academy.attempt ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.attempt FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.attempt USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.exercisecontent (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	exercise_id INTEGER NOT NULL,
	position INTEGER NOT NULL,
	kind VARCHAR NOT NULL,
	options JSON NOT NULL,
	explanation VARCHAR NOT NULL,
	accepted_answers JSON NOT NULL,
	case_sensitive BOOLEAN DEFAULT false NOT NULL,
	PRIMARY KEY (user_id, exercise_id),
	CONSTRAINT fk_exercisecontent_exercise_id FOREIGN KEY(user_id, exercise_id) REFERENCES academy.exercise (user_id, id)
)

;

ALTER TABLE academy.exercisecontent ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.exercisecontent FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.exercisecontent USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.offlinereceipt (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	id VARCHAR NOT NULL,
	payload_hash VARCHAR NOT NULL,
	client_started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	client_completed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	received_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	result JSON NOT NULL,
	PRIMARY KEY (user_id, id),
	CONSTRAINT fk_offlinereceipt_id FOREIGN KEY(user_id, id) REFERENCES academy.lessonrun (user_id, id)
)

;

ALTER TABLE academy.offlinereceipt ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.offlinereceipt FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.offlinereceipt USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.studytask (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	id VARCHAR NOT NULL,
	plan_week DATE NOT NULL,
	scheduled_date DATE NOT NULL,
	original_date DATE NOT NULL,
	subject VARCHAR NOT NULL,
	kind VARCHAR NOT NULL,
	title VARCHAR NOT NULL,
	instructions VARCHAR NOT NULL,
	planned_minutes INTEGER NOT NULL,
	lesson_id INTEGER,
	status VARCHAR NOT NULL,
	actual_minutes INTEGER,
	completed_at TIMESTAMP WITHOUT TIME ZONE,
	completed_run_id VARCHAR,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (user_id, id),
	CONSTRAINT fk_studytask_completed_run_id FOREIGN KEY(user_id, completed_run_id) REFERENCES academy.lessonrun (user_id, id),
	CONSTRAINT fk_studytask_lesson_id FOREIGN KEY(user_id, lesson_id) REFERENCES academy.lesson (user_id, id),
	CONSTRAINT fk_studytask_plan_week FOREIGN KEY(user_id, plan_week) REFERENCES academy.planweek (user_id, week_start),
	CONSTRAINT ck_task_status CHECK (status IN ('pending', 'completed', 'cancelled')),
	CONSTRAINT ck_task_planned CHECK (planned_minutes > 0),
	CONSTRAINT ck_task_actual CHECK (actual_minutes IS NULL OR actual_minutes BETWEEN 1 AND 480)
)

;

CREATE INDEX ix_studytask_scheduled_date ON academy.studytask (user_id, scheduled_date);

CREATE INDEX ix_studytask_plan_week ON academy.studytask (user_id, plan_week);

ALTER TABLE academy.studytask ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.studytask FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.studytask USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.vocabularyprogress (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	card_id INTEGER NOT NULL,
	box INTEGER NOT NULL,
	due_on DATE NOT NULL,
	added_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	review_count INTEGER NOT NULL,
	correct_count INTEGER NOT NULL,
	PRIMARY KEY (user_id, card_id),
	CONSTRAINT fk_vocabularyprogress_card_id FOREIGN KEY(user_id, card_id) REFERENCES academy.vocabularycard (user_id, id),
	CONSTRAINT ck_vocab_box CHECK (box BETWEEN 0 AND 5)
)

;

ALTER TABLE academy.vocabularyprogress ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.vocabularyprogress FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.vocabularyprogress USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.vocabularyreview (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	id VARCHAR NOT NULL,
	card_id INTEGER NOT NULL,
	answer VARCHAR NOT NULL,
	is_correct BOOLEAN NOT NULL,
	reviewed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	due_on DATE NOT NULL,
	box INTEGER NOT NULL,
	PRIMARY KEY (user_id, id),
	CONSTRAINT fk_vocabularyreview_card_id FOREIGN KEY(user_id, card_id) REFERENCES academy.vocabularycard (user_id, id)
)

;

CREATE INDEX ix_vocabularyreview_card_id ON academy.vocabularyreview (user_id, card_id);

ALTER TABLE academy.vocabularyreview ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.vocabularyreview FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.vocabularyreview USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.runanswer (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	id INTEGER DEFAULT nextval('academy.runanswer_id_seq') NOT NULL,
	run_id VARCHAR NOT NULL,
	exercise_id INTEGER NOT NULL,
	attempt_id INTEGER NOT NULL,
	PRIMARY KEY (user_id, id),
	CONSTRAINT fk_runanswer_attempt_id FOREIGN KEY(user_id, attempt_id) REFERENCES academy.attempt (user_id, id),
	CONSTRAINT fk_runanswer_exercise_id FOREIGN KEY(user_id, exercise_id) REFERENCES academy.exercise (user_id, id),
	CONSTRAINT fk_runanswer_run_id FOREIGN KEY(user_id, run_id) REFERENCES academy.lessonrun (user_id, id),
	CONSTRAINT uq_run_exercise UNIQUE (user_id, run_id, exercise_id),
	UNIQUE (user_id, attempt_id)
)

;

CREATE INDEX ix_runanswer_run_id ON academy.runanswer (user_id, run_id);

ALTER TABLE academy.runanswer ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.runanswer FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.runanswer USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));


CREATE TABLE academy.taskmove (
	user_id VARCHAR(36) DEFAULT nullif(current_setting('app.user_id', true), '') NOT NULL,
	id INTEGER DEFAULT nextval('academy.taskmove_id_seq') NOT NULL,
	task_id VARCHAR NOT NULL,
	from_date DATE NOT NULL,
	to_date DATE NOT NULL,
	moved_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (user_id, id),
	CONSTRAINT fk_taskmove_task_id FOREIGN KEY(user_id, task_id) REFERENCES academy.studytask (user_id, id)
)

;

CREATE INDEX ix_taskmove_task_id ON academy.taskmove (user_id, task_id);

ALTER TABLE academy.taskmove ENABLE ROW LEVEL SECURITY;

ALTER TABLE academy.taskmove FORCE ROW LEVEL SECURITY;

CREATE POLICY owner_access ON academy.taskmove USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''));
