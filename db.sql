CREATE TABLE "games" (
	"id"	VARCHAR(50)		NOT NULL,
	"status"	VARCHAR(20)	DEFAULT 'scheduled'	NOT NULL,
	"dh"	INTEGER	DEFAULT 0	NOT NULL,
	"score"	VARCHAR(10)		NULL,
	"time"	TIMESTAMP		NULL,
	"home_team"	VARCHAR(5)		NOT NULL,
	"away_team"	VARCHAR(5)		NOT NULL
);

CREATE TABLE "pitches" (
	"id"	SERIAL		NULL,
	"at_bats_id"	SERIAL		NULL,
	"pitch_num"	INTEGER		NULL,
	"pitch_type"	VARCHAR(50)		NULL,
	"speed"	FLOAT		NULL,
	"count"	VARCHAR(10)		NULL,
	"pitch_result"	VARCHAR(50)		NULL
);

CREATE TABLE "players" (
	"id"	SERIAL		NOT NULL,
	"player_name"	VARCHAR(20)		NOT NULL,
	"position"	VARCHAR(10)		NULL,
	"player_code"	VARCHAR(50)		NULL,
	"team_id"	VARCHAR(5)		NOT NULL,
	"player_bdate"	DATE		NULL
);

CREATE TABLE "at_bats" (
	"id"	SERIAL		NULL,
	"inning_id"	SERIAL		NULL,
	"bat_order"	INTEGER		NULL,
	"result"	VARCHAR(255)		NULL,
	"original_player_id"	SERIAL		NULL,
	"actual_player_id"	SERIAL		NOT NULL,
	"appearance_num"	INTEGER	DEFAULT 1	NOT NULL
);

CREATE TABLE "users" (
	"id"	SERIAL		NOT NULL,
	"user_nickname"	VARCHAR(10)		NULL,
	"created_at"	TIMESTAMP		NULL,
	"team_id"	VARCHAR(5)		NOT NULL,
	"password"	VARCHAR(1)		NULL,
	"last_login"	TIMESTAMP		NULL,
	"is_superuser"	BOOLEAN	DEFAULT 0	NOT NULL,
	"is_active"	BOOLEAN	DEFAULT 0	NOT NULL
);

CREATE TABLE "teams" (
	"id"	VARCHAR(5)		NOT NULL,
	"team_name"	VARCHAR(100)		NULL,
	"team_logo"	VARCHAR(255)		NULL,
	"field"	VARCHAR(255)		NULL
);

CREATE TABLE "player_team_history" (
	"id"	INTEGER		NOT NULL,
	"player_id"	SERIAL		NOT NULL,
	"start_year"	VARCHAR(5)		NULL,
	"end_year"	VARCHAR(5)		NULL,
	"team_id"	VARCHAR(5)		NOT NULL,
	"is_current_team"	BOOLEAN	DEFAULT 1	NOT NULL
);

CREATE TABLE "comments" (
	"id"	SERIAL		NOT NULL,
	"user_id"	SERIAL		NOT NULL,
	"comment_content"	TEXT		NOT NULL,
	"comment_created_at"	TIMESTAMP		NULL,
	"post_id"	SERIAL		NOT NULL
);

CREATE TABLE "posts" (
	"id"	SERIAL		NOT NULL,
	"user_id"	SERIAL		NOT NULL,
	"post_title"	VARCHAR(30)		NOT NULL,
	"post_content"	TEXT		NOT NULL,
	"post_created_at"	TIMESTAMP		NULL,
	"is_pinned"	BOOLEAN	DEFAULT 1	NOT NULL
);

CREATE TABLE "innings" (
	"id"	SERIAL		NULL,
	"game_id"	VARCHAR(50)		NOT NULL,
	"inning_number"	INTEGER		NOT NULL,
	"half"	VARCHAR(5)		NULL
);

ALTER TABLE "games" ADD CONSTRAINT "PK_GAMES" PRIMARY KEY (
	"id"
);

ALTER TABLE "pitches" ADD CONSTRAINT "PK_PITCHES" PRIMARY KEY (
	"id",
	"at_bats_id"
);

ALTER TABLE "players" ADD CONSTRAINT "PK_PLAYERS" PRIMARY KEY (
	"id"
);

ALTER TABLE "at_bats" ADD CONSTRAINT "PK_AT_BATS" PRIMARY KEY (
	"id",
	"inning_id"
);

ALTER TABLE "users" ADD CONSTRAINT "PK_USERS" PRIMARY KEY (
	"id"
);

ALTER TABLE "teams" ADD CONSTRAINT "PK_TEAMS" PRIMARY KEY (
	"id"
);

ALTER TABLE "player_team_history" ADD CONSTRAINT "PK_PLAYER_TEAM_HISTORY" PRIMARY KEY (
	"id",
	"player_id"
);

ALTER TABLE "comments" ADD CONSTRAINT "PK_COMMENTS" PRIMARY KEY (
	"id",
	"user_id"
);

ALTER TABLE "posts" ADD CONSTRAINT "PK_POSTS" PRIMARY KEY (
	"id",
	"user_id"
);

ALTER TABLE "innings" ADD CONSTRAINT "PK_INNINGS" PRIMARY KEY (
	"id",
	"game_id"
);

ALTER TABLE "pitches" ADD CONSTRAINT "FK_at_bats_TO_pitches_1" FOREIGN KEY (
	"at_bats_id"
)
REFERENCES "at_bats" (
	"id"
);

ALTER TABLE "at_bats" ADD CONSTRAINT "FK_innings_TO_at_bats_1" FOREIGN KEY (
	"inning_id"
)
REFERENCES "innings" (
	"id"
);

ALTER TABLE "player_team_history" ADD CONSTRAINT "FK_players_TO_player_team_history_1" FOREIGN KEY (
	"player_id"
)
REFERENCES "players" (
	"id"
);

ALTER TABLE "comments" ADD CONSTRAINT "FK_users_TO_comments_1" FOREIGN KEY (
	"user_id"
)
REFERENCES "users" (
	"id"
);

ALTER TABLE "posts" ADD CONSTRAINT "FK_users_TO_posts_1" FOREIGN KEY (
	"user_id"
)
REFERENCES "users" (
	"id"
);

ALTER TABLE "innings" ADD CONSTRAINT "FK_games_TO_innings_1" FOREIGN KEY (
	"game_id"
)
REFERENCES "games" (
	"id"
);

