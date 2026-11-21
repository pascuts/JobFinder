# ------------------------------------------------------------------------------
# Copyright (c) 2026 Adrian Pascut (ESLAMERA LIMITED). All rights reserved.
#
# LICENCE NOTICE:
# Permitted ONLY for free, non-commercial personal job-search use by Private
# Individuals. Any use, copying, or modification by a Commercial Entity—or for
# non-job-search purposes—requires prior written permission from the author.
#
# BREACH PENALTIES (Liquidated Damages):
# - Commercial Entity Breach: £100,000 per breach/deployment + legal fees.
# - Private Individual Breach: £10,000 per breach + legal fees.
#
# See the root LICENSE file for full legal terms, restrictions, and disclaimers.
# ------------------------------------------------------------------------------

import os
import sqlite3
import json
from contextlib import closing
from datetime import datetime

# Gemini requests allowed per day. Hard ceiling: config.txt may lower it, never raise it.
HARD_MAX_AI_CALLS_PER_DAY = 250


class DailyAIQuotaReached(Exception):
    """Raised instead of calling Gemini once the daily request allowance is used up."""


class DatabaseTracker:

    def __init__(
        self, db_filename=r"..\..\myprivatedata\jobseeking.db"
    ):
        self.db_filename = db_filename
        self.init_db()

    def get_connection(self):
        """Creates a database connection with Foreign Key support enabled."""
        conn = sqlite3.connect(self.db_filename)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self):
        """Creates required tables automatically if they do not exist."""
        schema = """
        CREATE TABLE IF NOT EXISTS searches (
            search_id INTEGER PRIMARY KEY AUTOINCREMENT,
            keywords TEXT,
            location TEXT,
            site TEXT,
            work_type TEXT,
            target_url TEXT,
            total_found INTEGER DEFAULT 0,
            to_apply_count INTEGER DEFAULT 0,
            maybe_count INTEGER DEFAULT 0,
            do_not_apply_count INTEGER DEFAULT 0,
            no_ai_calls INTEGER NOT NULL DEFAULT 0,
            active CHAR(1) DEFAULT 'Y' CHECK (active IN ('Y', 'N')),
            search_date DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS jobs(
          job_id TEXT,
          title TEXT,
          location TEXT,
          salary_range TEXT,
          work_type TEXT,
          is_hybrid_remote TEXT,
          job_url TEXT,
          created_at NUM,
          contact TEXT,
          company TEXT,
          match_score INT,
          job_status TEXT,
          cvtmpl_no INT,
          date_scoring TEXT,
          date_cv_change TEXT
        );

        CREATE TABLE IF NOT EXISTS job_evaluations (
            evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            description TEXT,
            evaluation_xml_response TEXT,
            cv_xml_response TEXT,
            cover_letter TEXT,
            evaluated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            changes_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS profile_cache (
            cache_id TEXT PRIMARY KEY,
            cache_for TEXT NOT NULL DEFAULT 'score',
            display_name TEXT,
            model TEXT,
            token_count INTEGER,
            expires_at DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS prefilter_jobs (
            job_id TEXT PRIMARY KEY,
            passed TEXT CHECK(passed IN ('Y', 'N')),
            score INTEGER DEFAULT 0,
            reason TEXT,
            evaluated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS ai_usage (
            day   TEXT PRIMARY KEY,          -- yyyy-MM-dd (local)
            calls INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS search_keywords (
            nocrt                  INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword                TEXT PRIMARY KEY,
            domain                 TEXT,
            query                  TEXT,
            base_score             REAL NOT NULL,          -- historical / configured score
            current_score          REAL,                   -- adjusted by yield, interviews, prefilter failures
            boost                  REAL NOT NULL DEFAULT 1.0,
            enabled                INTEGER NOT NULL DEFAULT 1,
            max_pages              INTEGER,                -- per-keyword overrides; NULL = use config.txt
            max_jobs               INTEGER,
            max_success            INTEGER,
            max_prefilter_fail     INTEGER,
            interviews             INTEGER NOT NULL DEFAULT 0,
            total_searches         INTEGER NOT NULL DEFAULT 0,
            total_pages            INTEGER NOT NULL DEFAULT 0,
            total_reads            INTEGER NOT NULL DEFAULT 0,
            total_prefilter_failed INTEGER NOT NULL DEFAULT 0,
            total_ai_jobs          INTEGER NOT NULL DEFAULT 0,
            total_successes        INTEGER NOT NULL DEFAULT 0,
            total_maybes           INTEGER NOT NULL DEFAULT 0,
            success_rate           REAL NOT NULL DEFAULT 0, -- successes / jobs that passed preselection (all time)
            recent_success_rate    REAL,                    -- same, time-decayed
            last_searched_at       TEXT,
            last_searched_display  TEXT
        );

        CREATE TABLE IF NOT EXISTS keyword_searches (
            ks_id            INTEGER PRIMARY KEY AUTOINCREMENT,
            search_id        INTEGER,                      -- link to searches.search_id
            keyword          TEXT NOT NULL,
            domain           TEXT,
            run_at           TEXT NOT NULL,                -- yyyy-MM-dd HH:mm:ss (sortable)
            run_at_display   TEXT,                         -- dd/MM/yyyy HH:mm
            score_before     REAL,                         -- historical score going into the search
            score_after      REAL,                         -- current score after the search
            target_pct       REAL,                         -- share of the daily target given to this search (%)
            quota            INTEGER,
            pages            INTEGER NOT NULL DEFAULT 0,
            reads            INTEGER NOT NULL DEFAULT 0,   -- job pages opened
            title_rejected   INTEGER NOT NULL DEFAULT 0,   -- failed stage A on the results card
            prefilter_failed INTEGER NOT NULL DEFAULT 0,   -- failed preselection in total (stage A + B)
            ai_jobs          INTEGER NOT NULL DEFAULT 0,   -- passed preselection and evaluated by Gemini
            ai_calls         INTEGER NOT NULL DEFAULT 0,   -- Gemini API requests used (incl. retries)
            successes        INTEGER NOT NULL DEFAULT 0,
            maybes           INTEGER NOT NULL DEFAULT 0,
            success_rate     REAL NOT NULL DEFAULT 0,      -- successes / ai_jobs
            bad_pages        INTEGER NOT NULL DEFAULT 0,   -- pages that exceeded the prefilter-failure limit
            interviews       INTEGER NOT NULL DEFAULT 0,
            stop_reason      TEXT,
            FOREIGN KEY (keyword) REFERENCES search_keywords(keyword)
        );

        CREATE TABLE IF NOT EXISTS blacklisted (
            key INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            reason TEXT,
            date DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_searches_date ON searches(search_date);
        CREATE INDEX IF NOT EXISTS idx_profile_cache ON profile_cache(cache_id);
        CREATE UNIQUE INDEX  IF NOT EXISTS idx_jobs_job_id ON jobs(job_id);

        CREATE INDEX IF NOT EXISTS idx_ks_run_at  ON keyword_searches(run_at);
        CREATE INDEX IF NOT EXISTS idx_ks_keyword ON keyword_searches(keyword);
        CREATE INDEX IF NOT EXISTS idx_ks_search  ON keyword_searches(search_id);
        """
        with closing(self.get_connection()) as conn:
            conn.executescript(schema)
            # jobs.search_id: which search first found the job (panel shows only that search's jobs)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
            if "search_id" not in cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN search_id INTEGER")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_search ON jobs(search_id)")
            conn.commit()
            from keyword_store import ensure_schema     # search_keywords + keyword_searches
            ensure_schema(conn)
            # searches.no_ai_calls: added to databases created before it existed, then filled from the
            # per-keyword search records so older searches show their AI calls too
            if "no_ai_calls" not in {r[1] for r in conn.execute("PRAGMA table_info(searches)")}:
                conn.execute("ALTER TABLE searches ADD COLUMN no_ai_calls INTEGER NOT NULL DEFAULT 0")
                conn.execute(
                    """UPDATE searches SET no_ai_calls = COALESCE(
                           (SELECT SUM(ks.ai_calls) FROM keyword_searches ks WHERE ks.search_id = searches.search_id), 0)""")
                conn.commit()

    def job_exists(self, cursor: sqlite3.Cursor, job_id: str) -> bool:
        """Checks whether a primary key job_id already exists in the jobs table."""
        clean_id = str(job_id).strip()
        cursor.execute("SELECT 1 FROM jobs WHERE CAST(job_id AS TEXT) = ?", (clean_id,))
        return cursor.fetchone() is not None

    def log_job(self, job_dict: dict, eval_dict: dict, search_id: int | None = None):
        job_id = str(job_dict.get("id") or job_dict.get("job_id") or "").strip()
        if not job_id:
            return

        # Helper function to prevent non-primitive binding errors (e.g., dict passed as param)
        def clean_val(val):
            if isinstance(val, (dict, list)):
                return json.dumps(val)
            return val

        job_fields = []

        # 1. Map and append fields passed in job_dict only if they exist and are not None
        job_mapping = {
            "title": "title",
            "location": "location",
            "salary": "salary_range",
            "salary_range": "salary_range",
            "work_type": "work_type",
            "hybrid": "is_hybrid_remote",
            "is_hybrid_remote": "is_hybrid_remote",
            "job_url": "job_url",
            "date_scoring": "date_scoring",
            "cvtmpl_no": "cvtmpl_no",
            "point_of_contact": "contact",
            "contact": "contact",
            "company": "company",
            "match_score": "match_score",
            "job_status": "job_status"
        }

        for key, col_name in job_mapping.items():
            if key in job_dict and job_dict[key] is not None:
                # Prevent duplicate columns if multiple aliases map to the same column
                if not any(f[0] == col_name for f in job_fields):
                    job_fields.append((col_name, clean_val(job_dict[key])))

        # Also support evaluation metrics if passed directly in eval_dict
        eval_job_mapping = {
            "score": "match_score",
            "match_score": "match_score",
            "job_status": "job_status",
            "cvtmpl_no": "cvtmpl_no"
        }

        for key, col_name in eval_job_mapping.items():
            if key in eval_dict and eval_dict[key] is not None:
                if not any(f[0] == col_name for f in job_fields):
                    job_fields.append((col_name, clean_val(eval_dict[key])))

        if search_id is not None:
            job_fields.append(("search_id", search_id))

        # Call update_job_fields ONLY if job_fields is not empty
        if job_fields:
            self.update_job_fields(job_id, job_fields)

        # 2. Prepare evaluation fields dynamically
        eval_fields = []
        eval_mapping = {
            "description": "description",
            "job_score_result": "evaluation_xml_response",
            "evaluation_xml_response": "evaluation_xml_response",
            "cv_xml_response": "cv_xml_response",
            "cover_letter": "cover_letter"
        }

        for key, col_name in eval_mapping.items():
            val = eval_dict.get(key)
            if val is not None and str(val).strip() != "":
                if not any(f[0] == col_name for f in eval_fields):
                    eval_fields.append((col_name, clean_val(val)))

        # Fallback check for description inside job_dict
        desc_val = job_dict.get("description")
        if desc_val is not None and str(desc_val).strip() != "":
            if not any(f[0] == "description" for f in eval_fields):
                eval_fields.append(("description", clean_val(desc_val)))

        # Call update_job_evaluation_fields ONLY if eval_fields is not empty
        if eval_fields:
            self.update_job_evaluation_fields(job_id, eval_fields)
            
    def getJobRecord(self, job_id: str) -> dict:
        if not job_id:
            return None

        clean_id = str(job_id).strip()

        query = """
            SELECT 
                j.job_id AS "Job ID",
                j.title AS "Job Title",
                j.created_at AS "Date Extracted",
                j.match_score AS "Match Score",
                j.company AS "Company",
                j.contact AS "Point of Contact",
                j.location AS "Location",
                j.salary_range AS "Salary",
                j.is_hybrid_remote AS "Hybrid Y/N",
                j.work_type AS "Work Type",
                j.job_url,
                e.description AS "Job Description",
                j.job_status,
                j.cvtmpl_no,
                e.evaluation_xml_response AS "EvaluationXML",
                e.cv_xml_response AS "CV4Job"
            FROM jobs j
            LEFT JOIN (
                SELECT job_id, description, evaluation_xml_response, cv_xml_response, cover_letter
                FROM job_evaluations 
                ORDER BY evaluated_at DESC
            ) e ON j.job_id = e.job_id
            WHERE CAST(j.job_id AS TEXT) = ?
            LIMIT 1;
        """

        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, (clean_id,))
            row = cursor.fetchone()

            if row:
                return dict(row)
            return None

    def is_job_processed_or_excluded(self, job_id: str) -> bool:
        """Checks if a job has already been stored."""
        if not job_id:
            return False

        clean_id = str(job_id).strip()

        query = "SELECT 1 FROM jobs WHERE CAST(job_id AS TEXT) = ? LIMIT 1;"

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (clean_id,))
                return cursor.fetchone() is not None
        except sqlite3.Error as e:
            print(f"Error checking job status: {e}")
            return False

    def log_search_start(self, search_params: dict) -> int:
        location = search_params.get("location", "UK")
        f_tpr = search_params.get("date_posted") or "r604800"
        f_e = search_params.get("experience") or "3,4,5,6"
        f_jt = search_params.get("contract_type") or "F,P,C"
        f_wt = search_params.get("workplace_type")
        sort_by = search_params.get("sort_by") or None
        keywords = search_params.get("keyword")
        target_url = search_params.get("target_input") 
        distance = search_params.get("distance") or None

        record =  f"📊 [Search]: {keywords} |d[{distance}] | f_wt[{f_wt}] | f_tpr[{f_tpr}] | f_e[{f_e}] | f_jt[{f_jt}] | {location} | sort_by[{sort_by}] |"

        site_str = search_params.get("portal", "")
        if "linkedin" in site_str.lower():
            site_code = "lnkin"
        elif "gov" in site_str.lower():
            site_code = "gov"

        query = """
            INSERT INTO searches (keywords, location, site, work_type, target_url)
            VALUES (?, ?, ?, ?, ?)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                query,
                (
                    search_params.get("keyword"),
                    search_params.get("location"),
                    site_code,
                    record,
                    search_params.get("target_input"),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def update_search_metrics(self, search_id: int, total_found: int, to_apply: int, maybe: int,
                              do_not_apply: int, no_ai_calls: int | None = None):
        """Results of a search. no_ai_calls = Gemini requests it used (None = leave unchanged)."""
        if not search_id:
            return

        query = """
            UPDATE searches
            SET total_found = ?,
                to_apply_count = ?,
                maybe_count = ?,
                do_not_apply_count = ?,
                no_ai_calls = COALESCE(?, no_ai_calls)
            WHERE search_id = ? and active='Y'
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (total_found, to_apply, maybe, do_not_apply, no_ai_calls, search_id))
            conn.commit()
        return True

    def update_status(self, job_id: str, status: str):
        with self.get_connection() as conn:
            # Also update the jobs table status and timestamp
            conn.execute("""
                UPDATE jobs 
                SET date_cv_change = CURRENT_TIMESTAMP,
                    job_status = ?
                WHERE job_id = ?
            """, (status, job_id,))
            conn.commit()

    def save_profile_cache(
        self,
        cache_id: str,
        display_name: str,
        model: str,
        token_count: int,
        expires_at_iso: str,
        cache_for: str = "score",
    ) -> bool:
        if not cache_id:
            return False

        clean_cache_for = "cv" if cache_for.lower() == "cv" else "score"

        query = """
            INSERT INTO profile_cache (cache_id, cache_for, display_name, model, token_count, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_id) DO UPDATE SET
                cache_for = excluded.cache_for,
                display_name = excluded.display_name,
                model = excluded.model,
                token_count = excluded.token_count,
                expires_at = excluded.expires_at,
                created_at = CURRENT_TIMESTAMP;
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                query,
                (cache_id, clean_cache_for, display_name, model, token_count, expires_at_iso),
            )
            conn.commit()
            return True

    def get_valid_profile_cache(self, cache_for: str = "score", buffer_minutes: int = 3) -> dict:
        clean_cache_for = "cv" if cache_for.lower() == "cv" else "score"
        buffer_param = f"+{buffer_minutes}"

        query = """
            SELECT cache_id, cache_for, display_name, model, token_count, expires_at
            FROM profile_cache
            WHERE cache_for = ? AND DATETIME(expires_at) > DATETIME('now', ? || ' minutes')
            ORDER BY expires_at DESC
            LIMIT 1;
        """
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, (clean_cache_for, buffer_param))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None


    def get_all_searches(self) -> list[dict]:
        """All search executions, newest first, joined with the keyword-search results."""
        query = """
            SELECT
                s.search_id, s.search_date, s.keywords, s.location, s.site, s.work_type,
                s.total_found, s.to_apply_count, s.maybe_count, s.do_not_apply_count, s.target_url,
                s.no_ai_calls,
                ks.keyword AS kw_keyword, ks.domain AS kw_domain, ks.run_at_display,
                ks.score_before, ks.score_after, ks.target_pct, ks.quota, ks.pages, ks.reads,
                ks.prefilter_failed, ks.ai_jobs, ks.ai_calls, ks.success_rate,
                ks.interviews, ks.stop_reason,
                sk.current_score AS kw_score_now, sk.interviews AS kw_interviews,
                sk.total_searches AS kw_searches, sk.success_rate AS kw_success_rate,
                sk.total_ai_jobs AS kw_ai_jobs, sk.total_successes AS kw_successes
            FROM searches s 
            LEFT JOIN keyword_searches ks ON ks.search_id = s.search_id
            LEFT JOIN search_keywords sk ON sk.keyword = ks.keyword
            WHERE s.active = 'Y'
            ORDER BY s.search_id DESC;
        """
        with closing(self.get_connection()) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(query).fetchall()]

    def get_jobs_by_search_id(self, search_id, status: str | None = None) -> list[dict]:
        """Only the jobs this search found; optionally only those with one status (case-insensitive)."""
        query = """
            SELECT job_id, title, company, match_score, job_status,
                   location, work_type, is_hybrid_remote
            FROM jobs WHERE search_id = ?
        """
        args: list = [int(search_id)]
        if status:
            query += " AND LOWER(COALESCE(job_status, '')) = LOWER(?)"
            args.append(status)
        query += " ORDER BY match_score DESC;"
        with closing(self.get_connection()) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(query, args).fetchall()]

    def get_search_stats(self, search_id) -> dict:
        """Job counts per status for one search (lower-cased status -> count) and the average AI score."""
        with closing(self.get_connection()) as conn:
            by_status = {r[0]: r[1] for r in conn.execute(
                """SELECT LOWER(COALESCE(job_status, '')), COUNT(*) FROM jobs
                   WHERE search_id = ? GROUP BY 1""", (int(search_id),))}
            avg = conn.execute("SELECT AVG(match_score) FROM jobs WHERE search_id = ? AND match_score >= 0",
                               (int(search_id),)).fetchone()[0]
        return {"total": sum(by_status.values()), "by_status": by_status, "avg_score": avg}

    # ------------------------------------------------------------------ #
    # Backup tab (database only - Excel is no longer used)
    # ------------------------------------------------------------------ #
    def backup_database(self, dest_dir: str | None = None) -> str:
        """Consistent copy of the whole database (SQLite online backup, safe while the app is running)."""
        dest_dir = dest_dir or os.path.join(os.path.dirname(os.path.abspath(self.db_filename)), "backups")
        os.makedirs(dest_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(self.db_filename))[0]
        dest = os.path.join(dest_dir, f"{base}_BkUp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        with closing(self.get_connection()) as src, closing(sqlite3.connect(dest)) as dst:
            src.backup(dst)
        return dest

    def get_status_metrics(self) -> list[dict]:
        """Per status: how many jobs and their lowest/highest score (-1000 = AI error, counted apart)."""
        query = """
            SELECT LOWER(COALESCE(job_status, '')) AS job_status, COUNT(*) AS n,
                   MIN(CASE WHEN match_score <> -1000 THEN match_score END) AS lo,
                   MAX(CASE WHEN match_score <> -1000 THEN match_score END) AS hi,
                   SUM(CASE WHEN match_score = -1000 THEN 1 ELSE 0 END) AS errors
            FROM jobs GROUP BY 1;
        """
        with closing(self.get_connection()) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(query).fetchall()]

    # ------------------------------------------------------------------ #
    # Gemini daily request allowance (hard ceiling, survives restarts)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _today() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def ai_calls_today(self) -> int:
        with closing(self.get_connection()) as conn:
            row = conn.execute("SELECT calls FROM ai_usage WHERE day = ?", (self._today(),)).fetchone()
        return int(row[0]) if row else 0

    def try_reserve_ai_call(self, limit: int = HARD_MAX_AI_CALLS_PER_DAY) -> bool:
        """Atomically take ONE request from today's allowance. False = allowance used up.
        Call it immediately before every Gemini generate_content attempt (retries included)."""
        limit = min(int(limit), HARD_MAX_AI_CALLS_PER_DAY)
        day = self._today()
        with closing(self.get_connection()) as conn:
            conn.execute("INSERT OR IGNORE INTO ai_usage (day, calls) VALUES (?, 0)", (day,))
            cur = conn.execute("UPDATE ai_usage SET calls = calls + 1 WHERE day = ? AND calls < ?", (day, limit))
            conn.commit()
            return cur.rowcount == 1

    def save_prefilter_result(self, job_id: str, passed: str, score: int, reason: str):
        """Inserts or updates a job's prefilter evaluation status."""
        query = """
            INSERT INTO prefilter_jobs (job_id, passed, score, reason, evaluated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(job_id) DO UPDATE SET
                passed = excluded.passed,
                score = excluded.score,
                reason = excluded.reason,
                evaluated_at = CURRENT_TIMESTAMP;
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (str(job_id).strip(), passed, score, reason))
            conn.commit()

    def get_all_jobs_for_prefilter(self) -> list[dict]:
        """Retrieves all jobs from the database for prefilter evaluation."""
        query = """
            SELECT job_id, title, location, salary_range AS salary, 
                   work_type, is_hybrid_remote AS hybrid, description 
            FROM jobs;
        """
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]


    def get_aggregate_metrics(self) -> dict:
        """Returns metrics grouped by Day (d), Month (M), Year (Y), and Total (T)."""
        query = """
            SELECT 
                -- Today (d) - Convert search_date to local time before checking date
                SUM(CASE WHEN date(search_date, 'localtime') = date('now', 'localtime') THEN 1 ELSE 0 END) AS searches_d,
                SUM(CASE WHEN date(search_date, 'localtime') = date('now', 'localtime') THEN total_found ELSE 0 END) AS extracted_d,
                SUM(CASE WHEN date(search_date, 'localtime') = date('now', 'localtime') THEN to_apply_count ELSE 0 END) AS to_apply_d,
                SUM(CASE WHEN date(search_date, 'localtime') = date('now', 'localtime') THEN maybe_count ELSE 0 END) AS maybe_d,
                SUM(CASE WHEN date(search_date, 'localtime') = date('now', 'localtime') THEN do_not_apply_count ELSE 0 END) AS dna_d,
                SUM(CASE WHEN date(search_date, 'localtime') = date('now', 'localtime') THEN no_ai_calls ELSE 0 END) AS calls_d,

                -- Month (M)
                SUM(CASE WHEN strftime('%Y-%m', search_date, 'localtime') = strftime('%Y-%m', 'now', 'localtime') THEN 1 ELSE 0 END) AS searches_M,
                SUM(CASE WHEN strftime('%Y-%m', search_date, 'localtime') = strftime('%Y-%m', 'now', 'localtime') THEN total_found ELSE 0 END) AS extracted_M,
                SUM(CASE WHEN strftime('%Y-%m', search_date, 'localtime') = strftime('%Y-%m', 'now', 'localtime') THEN to_apply_count ELSE 0 END) AS to_apply_M,
                SUM(CASE WHEN strftime('%Y-%m', search_date, 'localtime') = strftime('%Y-%m', 'now', 'localtime') THEN maybe_count ELSE 0 END) AS maybe_M,
                SUM(CASE WHEN strftime('%Y-%m', search_date, 'localtime') = strftime('%Y-%m', 'now', 'localtime') THEN do_not_apply_count ELSE 0 END) AS dna_M,
                SUM(CASE WHEN strftime('%Y-%m', search_date, 'localtime') = strftime('%Y-%m', 'now', 'localtime') THEN no_ai_calls ELSE 0 END) AS calls_M,

                -- Year (Y)
                SUM(CASE WHEN strftime('%Y', search_date, 'localtime') = strftime('%Y', 'now', 'localtime') THEN 1 ELSE 0 END) AS searches_Y,
                SUM(CASE WHEN strftime('%Y', search_date, 'localtime') = strftime('%Y', 'now', 'localtime') THEN total_found ELSE 0 END) AS extracted_Y,
                SUM(CASE WHEN strftime('%Y', search_date, 'localtime') = strftime('%Y', 'now', 'localtime') THEN to_apply_count ELSE 0 END) AS to_apply_Y,
                SUM(CASE WHEN strftime('%Y', search_date, 'localtime') = strftime('%Y', 'now', 'localtime') THEN maybe_count ELSE 0 END) AS maybe_Y,
                SUM(CASE WHEN strftime('%Y', search_date, 'localtime') = strftime('%Y', 'now', 'localtime') THEN do_not_apply_count ELSE 0 END) AS dna_Y,
                SUM(CASE WHEN strftime('%Y', search_date, 'localtime') = strftime('%Y', 'now', 'localtime') THEN no_ai_calls ELSE 0 END) AS calls_Y,

                -- Total (T)
                COUNT(*) AS searches_T,
                SUM(total_found) AS extracted_T,
                SUM(to_apply_count) AS to_apply_T,
                SUM(maybe_count) AS maybe_T,
                SUM(do_not_apply_count) AS dna_T,
                SUM(no_ai_calls) AS calls_T
            FROM searches
            WHERE active = 'Y';
        """
        with closing(self.get_connection()) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(query).fetchone()
            return dict(row) if row else {}


    def get_keyword_for_job(self, job_id: str) -> str:
        """Traces back and returns the keyword associated with a job via search_id."""
        query = """
            SELECT ks.keyword 
            FROM jobs j
            JOIN keyword_searches ks ON j.search_id = ks.search_id
            WHERE j.job_id = ?
            LIMIT 1;
        """
        with self.get_connection() as conn:
            row = conn.execute(query, (str(job_id).strip(),)).fetchone()
            return row[0] if row else None

    def get_jobs_by_status_and_date(self, criteria: dict, limit: int | None = None) -> list:
        """Executes a dynamic multi-criteria search on jobs and evaluations, maintaining status-specific or custom sorting."""
        query = """
            SELECT 
                j.job_id,
                COALESCE(j.company, 'Unknown') as company,
                j.title,
                j.location,
                j.salary_range,
                COALESCE(j.match_score, -1000) as match_score,
                COALESCE(j.job_status, '') as job_status,
                j.created_at,
                j.cvtmpl_no,
                j.contact,
                j.is_hybrid_remote,
                e.description
            FROM jobs j
            LEFT JOIN job_evaluations e ON j.job_id = e.job_id
            WHERE 1=1
        """
        params = []

        # Job ID filter
        if criteria.get("job_id"):
            query += " AND j.job_id LIKE ?"
            params.append(f"%{criteria['job_id']}%")

        # Company filter
        if criteria.get("company"):
            query += " AND j.company LIKE ?"
            params.append(f"%{criteria['company']}%")

        # Title filter
        if criteria.get("title"):
            query += " AND j.title LIKE ?"
            params.append(f"%{criteria['title']}%")

        # Description substring search using INSTR (case-insensitive via LOWER)
        description_sub = criteria.get("description")
        if description_sub and str(description_sub).strip():
            query += " AND INSTR(LOWER(COALESCE(e.description, '')), LOWER(?)) > 0"
            params.append(str(description_sub).strip())

        # Job Status filter
        status = criteria.get("job_status")
        clean_status = str(status).strip().lower() if status else ""
        if clean_status and clean_status != "all":
            query += " AND LOWER(j.job_status) = LOWER(?)"
            params.append(str(status).strip())

        # Target date filter mapped to created_at (e.g., target_date_str)
        created_at_val = criteria.get("created_at") or criteria.get("target_date_str")
        if created_at_val and str(created_at_val).strip():
            query += " AND DATE(j.created_at) >= DATE(?)"
            params.append(str(created_at_val).strip())
        # Days back filter (related to created_at)
        if criteria.get("days_back") is not None:
            try:
                query += " AND date(j.created_at) >= date('now', '-' || ? || ' days')"
                params.append(int(criteria["days_back"]))
            except ValueError:
                pass
                
        # Score filter
        if criteria.get("score") is not None and str(criteria.get("score")).strip():
            try:
                query += " AND j.match_score >= ?"
                params.append(int(criteria["score"]))
            except ValueError:
                pass

        # Salary filter
        if criteria.get("salary"):
            query += " AND j.salary_range LIKE ?"
            params.append(f"%{criteria['salary']}%")

        # Sorting logic: toapply gets priority, otherwise check custom sort parameter or default to created_at DESC
        if clean_status == 'toapply':
            order_clause = " ORDER BY j.created_at DESC, j.match_score DESC"
        elif criteria.get("order by"):
            sort_field = str(criteria["order by"])
            direction = str(criteria.get("direction", "DESC")).upper()
            if direction not in ("ASC", "DESC"):
                direction = "DESC"
            order_clause = f" ORDER BY {sort_field} {direction}"
        else:
            order_clause = " ORDER BY j.created_at DESC"
        
        query += order_clause

        # Optional Limit
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))

        try:
            with self.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as err:
            print(f"Database Query Error: {err}")
            return []
            
    def populate_job_status(self):
        """Fetches distinct job_status values from the jobs table, excluding 'donotapply'."""
        statuses = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT DISTINCT job_status 
                    FROM jobs 
                    WHERE job_status IS NOT NULL 
                        AND TRIM(job_status) != ''
                    ORDER BY job_status Desc
                """)
                rows = cursor.fetchall()
                for row in rows:
                    status = str(row[0]).strip()
                    if status.lower() not in ("donotapply", "do not apply"):
                        statuses.append(status)
            except Exception as e:
                print(f"Error loading status recommendations: {e}")
                return statuses
        return statuses

    def update_job_evaluation_fields(self, job_id: str, fields_set):
        """Updates up to 4 specified fields in the job_evaluations table for a given job_id,
        or inserts a new record if one does not already exist. 
        Conditionally sets evaluated_at and changes_at if their respective XML responses are non-empty.
        fields_set: A set or iterable of (field_name, value) tuples.
        """
        allowed_fields = {"description", "evaluation_xml_response", "cv_xml_response", "cover_letter"}
    
        # 1. Enforce maximum 4 elements constraint
        if len(fields_set) > 4:
            raise ValueError("A maximum of 4 fields can be updated at a time.")

        # 2. Validate all fields against allowed_fields first, and map them
        field_dict = {}
        for field_name, value in fields_set:
            if field_name not in allowed_fields:
                raise ValueError(f"Invalid field name '{field_name}' for job_evaluations table.")
            field_dict[field_name] = value

        with self.get_connection() as conn:
            cursor = conn.cursor()
            clean_job_id = str(job_id).strip()
        
            # Check if an evaluation record already exists for this job
            cursor.execute("SELECT evaluation_id FROM job_evaluations WHERE CAST(job_id AS TEXT) = ? LIMIT 1", (clean_job_id,))
            row = cursor.fetchone()

            # Determine if timestamps should be updated based on non-empty values
            eval_xml = field_dict.get("evaluation_xml_response")
            has_eval_xml = eval_xml is not None and str(eval_xml).strip() != ""

            cv_xml = field_dict.get("cv_xml_response")
            has_cv_xml = cv_xml is not None and str(cv_xml).strip() != ""

            if row:
                # Build dynamic UPDATE query based on the pre-validated fields
                set_clauses = []
                values = []
                for field_name, value in field_dict.items():
                    set_clauses.append(f"{field_name} = ?")
                    values.append(value)
            
                # Conditionally update timestamps
                if has_eval_xml:
                    set_clauses.append("evaluated_at = CURRENT_TIMESTAMP")
                if has_cv_xml:
                    set_clauses.append("changes_at = CURRENT_TIMESTAMP")

                values.append(clean_job_id)
                query = f"UPDATE job_evaluations SET {', '.join(set_clauses)} WHERE CAST(job_id AS TEXT) = ?"
                cursor.execute(query, tuple(values))
            else:
                # Insert a new record if none exists
                columns = ["job_id"]
                values = [clean_job_id]
                placeholders = ["?"]
                
                for field_name, value in field_dict.items():
                    columns.append(field_name)
                    values.append(value)
                    placeholders.append("?")
                
                # Conditionally include timestamps on insert
                if has_eval_xml:
                    columns.append("evaluated_at")
                    placeholders.append("CURRENT_TIMESTAMP")
                if has_cv_xml:
                    columns.append("changes_at")
                    placeholders.append("CURRENT_TIMESTAMP")
                    
                query = f"INSERT INTO job_evaluations ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
                cursor.execute(query, tuple(values))
                
            conn.commit()
    def is_company_blacklisted(self, company_name: str) -> bool:
        """Checks if a given company name exists in the blacklisted table."""
        if not company_name or not str(company_name).strip():
            return False
        
        clean_company = str(company_name).strip().lower()
        query = "SELECT 1 FROM blacklisted WHERE LOWER(company) = ? LIMIT 1;"
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (clean_company,))
                return cursor.fetchone() is not None
        except sqlite3.Error as e:
            print(f"Error checking blacklisted company: {e}")
            return False

    def update_job_fields(self, job_id: str, fields_set):
        """Updates specified fields in the jobs table for a given job_id,
        or inserts a new record if one does not already exist.
        fields_set: A set or iterable of (field_name, value) tuples.
        """
        allowed_fields = {
            "title", "location", "salary_range", "work_type", "is_hybrid_remote", "job_url",  
            "contact", "company", "match_score", "job_status", 
            "cvtmpl_no", "date_scoring", "date_cv_change", "search_id"
        }
    
        # Validate all fields against allowed_fields first, and map them
        field_dict = {}
        for field_name, value in fields_set:
            if field_name not in allowed_fields:
                raise ValueError(f"Invalid field name '{field_name}' for jobs table.")
            field_dict[field_name] = value

        with self.get_connection() as conn:
            cursor = conn.cursor()
            clean_job_id = str(job_id).strip()
        
            # Check if job record already exists
            if self.job_exists(cursor, clean_job_id):
                # Build dynamic UPDATE query
                set_clauses = []
                values = []
                for field_name, value in field_dict.items():
                    set_clauses.append(f"{field_name} = ?")
                    values.append(value)
            
                values.append(clean_job_id)
                query = f"UPDATE jobs SET {', '.join(set_clauses)} WHERE CAST(job_id AS TEXT) = ?"
                cursor.execute(query, tuple(values))
            else:
                # Insert a new record including created_at timestamp
                columns = ["job_id", "created_at"]
                values = [clean_job_id, "CURRENT_TIMESTAMP"]
                placeholders = ["?", "CURRENT_TIMESTAMP"]
                               
                for field_name, value in field_dict.items():
                    columns.append(field_name)
                    values.append(value)
                    placeholders.append("?")
                    
                query = f"INSERT INTO jobs ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
                # Filter out literal "CURRENT_TIMESTAMP" string from parameter bindings
                bind_values = [v for v, p in zip(values, placeholders) if p != "CURRENT_TIMESTAMP"]
                cursor.execute(query, tuple(bind_values))
                
            conn.commit()