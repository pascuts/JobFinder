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

# keyword_store.py

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta

USER_DOMAIN = "user_insert"      # domain given to keywords typed in the UI
USER_BASE_SCORE = 6.0            # starting score of a typed keyword (editable in the DB)

TS = "%Y-%m-%d %H:%M:%S"          # sortable, used for all calculations
DISPLAY = "%d/%m/%Y %H:%M"        # dd/MM/yyyy HH:mm, shown to the user


def fmt_display(dt: datetime) -> str:
    return dt.strftime(DISPLAY)

def normalize_keyword(text: str) -> str:
    """Collapse whitespace; drop quotes wrapping a single phrase ("Delivery Manager" == Delivery Manager)."""
    t = " ".join((text or "").split())
    if len(t) >= 2 and t[0] == '"' and t[-1] == '"' and '"' not in t[1:-1]:
        t = t[1:-1].strip()
    return t

def _row_factory(cursor, row) -> dict:
    return {d[0]: row[i] for i, d in enumerate(cursor.description)}


def split_keywords(text: str) -> list[str]:
    """'A, B, "C, D" OR E' -> ['A', 'B', '"C, D" OR E'].  Splits on commas outside quotes/brackets and
    drops duplicates (case-insensitive) while keeping the order."""
    parts, buf, depth, in_q = [], [], 0, False
    for ch in text or "":
        if ch == '"':
            in_q = not in_q
        elif not in_q and ch == "(":
            depth += 1
        elif not in_q and ch == ")":
            depth = max(depth - 1, 0)
        if ch == "," and not in_q and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    seen, out = set(), []
    for p in parts:
        n = normalize_keyword(p)
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


# header key -> SQL expression (whitelist: the UI never passes SQL)
SORT_COLUMNS = {
    "keyword": "keyword COLLATE NOCASE", "domain": "domain COLLATE NOCASE",
    "base_score": "base_score", "current_score": "current_score", "boost": "boost", "enabled": "enabled",
    "max_pages": "max_pages", "max_jobs": "max_jobs", "max_success": "max_success",
    "max_prefilter_fail": "max_prefilter_fail", "interviews": "interviews",
    "total_searches": "total_searches", "total_pages": "total_pages", "total_reads": "total_reads",
    "total_prefilter_failed": "total_prefilter_failed", "total_ai_jobs": "total_ai_jobs",
    "total_successes": "total_successes", "total_maybes": "total_maybes", "success_rate": "success_rate",
    "recent_success_rate": "recent_success_rate", "last_searched_at": "last_searched_at",
}

def ensure_schema(conn) -> None:
    conn.execute("UPDATE search_keywords SET current_score = base_score WHERE current_score IS NULL")
    conn.commit()


class KeywordStore:
    def __init__(self, db_tracker):
        self.db = db_tracker
        with closing(self.db.get_connection()) as conn:
            ensure_schema(conn)

    # ------------------------------------------------------------------ #
    # Catalogue / configuration
    # ------------------------------------------------------------------ #
    def seed_missing(self, seed: list[tuple]) -> int:
        """Insert keywords that are not in the table yet. NEVER overwrites rows, so scores and
        per-keyword configuration you edited in the database survive restarts."""
        added = 0
        with closing(self.db.get_connection()) as conn:
            for kw, domain, score, query in seed:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO search_keywords (keyword, domain, query, base_score, current_score)
                       VALUES (?, ?, ?, ?, ?)""",
                    (kw, domain, query, float(score), float(score)),
                )
                added += cur.rowcount
            conn.commit()
        return added

    def seed_with_boosts(self, seed: list[tuple], boosts: dict | None = None) -> list[str]:
        """Insert missing keywords; the one-off boosts are applied ONLY to the keywords inserted now,
        so a boost you changed later is never reset. Returns the keywords inserted."""
        inserted = []
        with closing(self.db.get_connection()) as conn:
            for kw, domain, score, query in seed:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO search_keywords (keyword, domain, query, base_score, current_score)
                       VALUES (?, ?, ?, ?, ?)""", (kw, domain, query, float(score), float(score)))
                if cur.rowcount:
                    inserted.append(kw)
            for kw in inserted:
                if boosts and kw in boosts:
                    conn.execute("UPDATE search_keywords SET boost = ? WHERE keyword = ?", (float(boosts[kw]), kw))
            conn.commit()
        return inserted

    def find_keyword(self, text: str) -> dict | None:
        """Case-insensitive lookup (spaces and wrapping quotes ignored)."""
        n = normalize_keyword(text)
        with closing(self.db.get_connection()) as conn:
            conn.row_factory = _row_factory
            return conn.execute("SELECT * FROM search_keywords WHERE LOWER(keyword) = LOWER(?)", (n,)).fetchone()

    def add_user_keyword(self, text: str, base_score: float = USER_BASE_SCORE) -> tuple[dict, bool]:
        """A keyword typed in the UI. Saved with domain 'user_insert' unless it already exists.
        Returns (row, created)."""
        n = normalize_keyword(text)
        if not n:
            raise ValueError("empty keyword")
        existing = self.find_keyword(n)
        if existing:
            return existing, False
        with closing(self.db.get_connection()) as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO search_keywords (keyword, domain, query, base_score, current_score)
                   VALUES (?, ?, NULL, ?, ?)""", (n, USER_DOMAIN, base_score, base_score))
            conn.commit()
            created = cur.rowcount == 1
        return self.find_keyword(n), created

    def ensure_adhoc(self, keyword: str, domain: str = USER_DOMAIN, base_score: float = USER_BASE_SCORE) -> None:
        self.add_user_keyword(keyword, base_score)

    def set_boost(self, keyword: str, factor: float) -> None:
        self._update(keyword, "boost", float(factor))

    def set_enabled(self, keyword: str, enabled: bool) -> None:
        self._update(keyword, "enabled", 1 if enabled else 0)

    def set_overrides(self, keyword: str, max_pages=None, max_jobs=None, max_success=None,
                      max_prefilter_fail=None) -> None:
        """Per-keyword limits. None = fall back to config.txt."""
        with closing(self.db.get_connection()) as conn:
            conn.execute(
                """UPDATE search_keywords SET max_pages = ?, max_jobs = ?, max_success = ?,
                          max_prefilter_fail = ? WHERE keyword = ?""",
                (max_pages, max_jobs, max_success, max_prefilter_fail, keyword),
            )
            conn.commit()

    def _update(self, keyword: str, col: str, value) -> None:
        with closing(self.db.get_connection()) as conn:
            conn.execute(f"UPDATE search_keywords SET {col} = ? WHERE keyword = ?", (value, keyword))
            conn.commit()

    def get_keyword(self, keyword: str) -> dict | None:
        with closing(self.db.get_connection()) as conn:
            conn.row_factory = _row_factory
            return conn.execute("SELECT * FROM search_keywords WHERE keyword = ?", (keyword,)).fetchone()

    def get_enabled(self, domain: str | None = None) -> list[dict]:
        sql = "SELECT * FROM search_keywords WHERE enabled = 1"
        args: tuple = ()
        if domain:
            sql += " AND LOWER(domain) = ?"
            args = (domain.lower(),)
        with closing(self.db.get_connection()) as conn:
            conn.row_factory = _row_factory
            return conn.execute(sql, args).fetchall()

    def domains(self) -> list[str]:
        with closing(self.db.get_connection()) as conn:
            return [r[0] for r in conn.execute(
                "SELECT DISTINCT domain FROM search_keywords WHERE enabled = 1 AND domain IS NOT NULL")]

    def list_keywords(self, sort_key: str = "keyword", direction: str = "ASC") -> list[dict]:
        """All keywords, sorted by any column (NULLs always last)."""
        col = SORT_COLUMNS.get(sort_key, SORT_COLUMNS["keyword"])
        d = "DESC" if str(direction).upper() == "DESC" else "ASC"
        sql = (f"SELECT * FROM search_keywords ORDER BY ({col.split()[0]} IS NULL), {col} {d}, "
               f"keyword COLLATE NOCASE")
        with closing(self.db.get_connection()) as conn:
            conn.row_factory = _row_factory
            return conn.execute(sql).fetchall()

    def keyword_summary(self, keyword: str) -> dict | None:
        """Everything the keyword's searches produced, combined."""
        with closing(self.db.get_connection()) as conn:
            conn.row_factory = _row_factory
            kw = conn.execute("SELECT * FROM search_keywords WHERE keyword = ?", (keyword,)).fetchone()
            if not kw:
                return None
            a = conn.execute(
                """SELECT COUNT(*) n, COALESCE(SUM(pages),0) pages, COALESCE(SUM(reads),0) reads,
                          COALESCE(SUM(title_rejected),0) title_rejected,
                          COALESCE(SUM(prefilter_failed),0) prefilter_failed,
                          COALESCE(SUM(ai_jobs),0) ai_jobs, COALESCE(SUM(ai_calls),0) ai_calls,
                          COALESCE(SUM(successes),0) successes, COALESCE(SUM(maybes),0) maybes,
                          COALESCE(SUM(bad_pages),0) bad_pages, AVG(target_pct) avg_target_pct,
                          COALESCE(SUM(CASE WHEN successes = 0 THEN 1 ELSE 0 END),0) empty_searches,
                          MIN(score_after) min_score, MAX(score_after) max_score
                   FROM keyword_searches WHERE keyword = ?""", (keyword,)).fetchone()
            first = conn.execute(
                "SELECT score_before, run_at_display FROM keyword_searches WHERE keyword = ? "
                "ORDER BY run_at ASC, ks_id ASC LIMIT 1", (keyword,)).fetchone()
            last = conn.execute(
                "SELECT score_after, run_at_display FROM keyword_searches WHERE keyword = ? "
                "ORDER BY run_at DESC, ks_id DESC LIMIT 1", (keyword,)).fetchone()
            stops: dict = {}
            for r in conn.execute("SELECT stop_reason, COUNT(*) c FROM keyword_searches WHERE keyword = ? "
                                  "GROUP BY stop_reason", (keyword,)):
                key = (r["stop_reason"] or "-").split(":")[0]
                stops[key] = stops.get(key, 0) + r["c"]
            jobs = {r["st"]: r["c"] for r in conn.execute(
                """SELECT LOWER(COALESCE(job_status,'')) st, COUNT(*) c FROM jobs
                   WHERE search_id IN (SELECT search_id FROM keyword_searches
                                       WHERE keyword = ? AND search_id IS NOT NULL) GROUP BY st""", (keyword,))}
        ai, succ, maybe = a["ai_jobs"], a["successes"], a["maybes"]
        a.update({
            "keyword": kw, "do_not_apply": max(ai - succ - maybe, 0),
            "success_rate": (succ / ai) if ai else 0.0,
            "first_search": first["run_at_display"] if first else None,
            "last_search": last["run_at_display"] if last else None,
            "first_score": first["score_before"] if first else None,
            "current_score": kw["current_score"],
            "stop_reasons": dict(sorted(stops.items(), key=lambda kv: -kv[1])),
            "jobs_by_status": jobs,
            "reads_per_search": (a["reads"] / a["n"]) if a["n"] else 0.0,
            "successes_per_search": (succ / a["n"]) if a["n"] else 0.0,
        })
        return a

    # ------------------------------------------------------------------ #
    # Counters / history
    # ------------------------------------------------------------------ #
    def today_totals(self, now: datetime | None = None) -> dict:
        now = now or datetime.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime(TS)
        with closing(self.db.get_connection()) as conn:
            row = conn.execute(
                """SELECT COALESCE(SUM(successes),0), COALESCE(SUM(reads),0), COALESCE(SUM(pages),0),
                          COALESCE(SUM(ai_jobs),0)
                   FROM keyword_searches WHERE run_at >= ?""", (midnight,)).fetchone()
        return {"successes": row[0], "reads": row[1], "pages": row[2], "ai_jobs": row[3]}

    def history(self, since: datetime, conn=None) -> list[dict]:
        # pending = jobs of that search still waiting for the AI verdict. The scheduler removes them from
        # the reads so a search that has not been scored yet is not counted as "0 successes".
        sql = """SELECT ks.keyword, ks.domain, ks.run_at, ks.reads, ks.ai_jobs, ks.successes, ks.maybes,
                        ks.bad_pages,
                        (SELECT COUNT(*) FROM jobs j
                          WHERE j.search_id = ks.search_id AND LOWER(j.job_status) = 'scraped') AS pending
                 FROM keyword_searches ks WHERE ks.run_at >= ?"""
        if conn is not None:
            conn.row_factory = _row_factory
            return conn.execute(sql, (since.strftime(TS),)).fetchall()
        with closing(self.db.get_connection()) as c:
            c.row_factory = _row_factory
            return c.execute(sql, (since.strftime(TS),)).fetchall()

    # ------------------------------------------------------------------ #
    # Record one search + refresh the keyword row (one transaction)
    # ------------------------------------------------------------------ #
    def record_search(self, rec: dict, score_fn, history_days: int, now: datetime | None = None) -> dict:
        """rec: search_id, keyword, quota, target_pct, pages, reads, title_rejected, prefilter_failed,
        ai_jobs, ai_calls, successes, maybes, bad_pages, stop_reason.
        score_fn(keyword_row, history_rows, now) -> {"score": float, "recent_success_rate": float}"""
        now = now or datetime.now()
        ts, shown = now.strftime(TS), fmt_display(now)
        ai_jobs, succ = int(rec.get("ai_jobs", 0)), int(rec.get("successes", 0))
        rate = (succ / ai_jobs) if ai_jobs else 0.0

        with closing(self.db.get_connection()) as conn:
            conn.row_factory = _row_factory
            kw = conn.execute("SELECT * FROM search_keywords WHERE keyword = ?", (rec["keyword"],)).fetchone()
            if kw is None:
                raise KeyError(f"keyword not in search_keywords: {rec['keyword']}")
            before = kw["current_score"] if kw["current_score"] is not None else kw["base_score"]

            cur = conn.execute(
                """INSERT INTO keyword_searches
                   (search_id, keyword, domain, run_at, run_at_display, score_before, score_after, target_pct,
                    quota, pages, reads, title_rejected, prefilter_failed, ai_jobs, ai_calls, successes,
                    maybes, success_rate, bad_pages, stop_reason)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rec.get("search_id"), rec["keyword"], kw["domain"], ts, shown, before, before,
                 rec.get("target_pct"), rec.get("quota"), rec.get("pages", 0), rec.get("reads", 0),
                 rec.get("title_rejected", 0), rec.get("prefilter_failed", 0), ai_jobs,
                 rec.get("ai_calls", 0), succ, rec.get("maybes", 0), rate, rec.get("bad_pages", 0),
                 rec.get("stop_reason", "")),
            )
            rowid = cur.lastrowid

            hist = self.history(now - timedelta(days=history_days), conn=conn)
            conn.row_factory = _row_factory
            res = score_fn(kw, hist, now)
            new_score = float(res["score"])
            conn.execute("UPDATE keyword_searches SET score_after = ? WHERE ks_id = ?", (new_score, rowid))

            agg = conn.execute(
                """SELECT COUNT(*) n, COALESCE(SUM(pages),0) p, COALESCE(SUM(reads),0) r,
                          COALESCE(SUM(prefilter_failed),0) pf, COALESCE(SUM(ai_jobs),0) a,
                          COALESCE(SUM(successes),0) s, COALESCE(SUM(maybes),0) m
                   FROM keyword_searches WHERE keyword = ?""", (rec["keyword"],)).fetchone()
            conn.execute(
                """UPDATE search_keywords SET
                       current_score = ?, total_searches = ?, total_pages = ?, total_reads = ?,
                       total_prefilter_failed = ?, total_ai_jobs = ?, total_successes = ?, total_maybes = ?,
                       success_rate = ?, recent_success_rate = ?, last_searched_at = ?, last_searched_display = ?
                   WHERE keyword = ?""",
                (new_score, agg["n"], agg["p"], agg["r"], agg["pf"], agg["a"], agg["s"], agg["m"],
                 (agg["s"] / agg["a"]) if agg["a"] else 0.0, res.get("recent_success_rate"),
                 ts, shown, rec["keyword"]),
            )
            conn.commit()
        return {"score_before": before, "score_after": new_score, "success_rate": rate,
                "run_at_display": shown, "ks_id": rowid}

    # ------------------------------------------------------------------ #
    # AI results arrive AFTER the scraping (scoring is a separate phase)
    # ------------------------------------------------------------------ #
    def update_ai_results(self, search_id: int, score_fn, history_days: int,
                          add_ai_calls: int = 0, now: datetime | None = None) -> dict | None:
        """Recomputes everything the AI verdicts change for ONE search, in one transaction:
             jobs table -> keyword_searches row (ai_jobs, successes, maybes, success_rate, ai_calls, score_after)
                        -> searches row (to_apply / maybe / do_not_apply counts, no_ai_calls)
                        -> search_keywords row (totals, success rates, current_score)
        Counts are re-derived from the jobs table, so calling it twice (or after a partial / interrupted
        scoring round) is safe. add_ai_calls is the only incremental value (Gemini requests used now).
        Returns None for searches without a keyword record (direct-URL searches)."""
        now = now or datetime.now()
        with closing(self.db.get_connection()) as conn:
            conn.row_factory = _row_factory
            ks = conn.execute("SELECT * FROM keyword_searches WHERE search_id = ?", (search_id,)).fetchone()
            if ks is None:
                return None
            kw = conn.execute("SELECT * FROM search_keywords WHERE keyword = ?", (ks["keyword"],)).fetchone()
            if kw is None:
                return None

            # AI-evaluated = date_scoring set and a real score (-1000 = the AI answer could not be parsed)
            c = conn.execute(
                """SELECT
                     COALESCE(SUM(CASE WHEN st = 'toapply' THEN 1 ELSE 0 END), 0) AS successes,
                     COALESCE(SUM(CASE WHEN st = 'maybe' THEN 1 ELSE 0 END), 0) AS maybes,
                     COALESCE(SUM(CASE WHEN st IN ('donotapply', 'notapply') THEN 1 ELSE 0 END), 0) AS dna,
                     COUNT(*) AS ai_jobs
                   FROM (SELECT REPLACE(REPLACE(LOWER(COALESCE(job_status, '')), ' ', ''), '_', '') AS st
                           FROM jobs
                          WHERE search_id = ? AND date_scoring IS NOT NULL
                            AND COALESCE(match_score, 0) > -1000)""", (search_id,)).fetchone()
            ai_jobs, succ, maybes = int(c["ai_jobs"]), int(c["successes"]), int(c["maybes"])
            ai_calls = int(ks["ai_calls"] or 0) + int(add_ai_calls or 0)
            rate = (succ / ai_jobs) if ai_jobs else 0.0

            conn.execute(
                """UPDATE keyword_searches SET ai_jobs = ?, ai_calls = ?, successes = ?, maybes = ?,
                          success_rate = ?, stop_reason = CASE WHEN stop_reason = 'scraped' THEN 'scored'
                                                               ELSE stop_reason END
                   WHERE ks_id = ?""", (ai_jobs, ai_calls, succ, maybes, rate, ks["ks_id"]))
            conn.execute(
                """UPDATE searches SET to_apply_count = ?, maybe_count = ?, do_not_apply_count = ?,
                          no_ai_calls = ? WHERE search_id = ?""",
                (succ, maybes, int(c["dna"]), ai_calls, search_id))

            # score with the fresh numbers
            hist = self.history(now - timedelta(days=history_days), conn=conn)
            conn.row_factory = _row_factory
            res = score_fn(kw, hist, now)
            new_score = float(res["score"])
            conn.execute("UPDATE keyword_searches SET score_after = ? WHERE ks_id = ?", (new_score, ks["ks_id"]))

            agg = conn.execute(
                """SELECT COUNT(*) n, COALESCE(SUM(pages),0) p, COALESCE(SUM(reads),0) r,
                          COALESCE(SUM(prefilter_failed),0) pf, COALESCE(SUM(ai_jobs),0) a,
                          COALESCE(SUM(successes),0) s, COALESCE(SUM(maybes),0) m
                   FROM keyword_searches WHERE keyword = ?""", (ks["keyword"],)).fetchone()
            conn.execute(
                """UPDATE search_keywords SET
                       current_score = ?, total_searches = ?, total_pages = ?, total_reads = ?,
                       total_prefilter_failed = ?, total_ai_jobs = ?, total_successes = ?, total_maybes = ?,
                       success_rate = ?, recent_success_rate = ?
                   WHERE keyword = ?""",
                (new_score, agg["n"], agg["p"], agg["r"], agg["pf"], agg["a"], agg["s"], agg["m"],
                 (agg["s"] / agg["a"]) if agg["a"] else 0.0, res.get("recent_success_rate"), ks["keyword"]))
            conn.commit()
        return {"keyword": ks["keyword"], "ai_jobs": ai_jobs, "successes": succ, "maybes": maybes,
                "ai_calls": ai_calls, "score_before": ks["score_before"], "score_after": new_score}

    # ------------------------------------------------------------------ #
    # Interviews
    # ------------------------------------------------------------------ #
    def adjust_interviews(self, keyword: str, delta: int, search_id: int | None = None) -> int:
        """+1 / -1 interview for a keyword (and for the selected search row). Returns the keyword total."""
        with closing(self.db.get_connection()) as conn:
            conn.execute("UPDATE search_keywords SET interviews = MAX(interviews + ?, 0) WHERE keyword = ?",
                         (delta, keyword))
            if search_id is not None:
                conn.execute("UPDATE keyword_searches SET interviews = MAX(interviews + ?, 0) WHERE search_id = ?",
                             (delta, search_id))
            row = conn.execute("SELECT interviews FROM search_keywords WHERE keyword = ?", (keyword,)).fetchone()
            conn.commit()
        return int(row[0]) if row else 0

    def interviews_for(self, keyword: str, search_id: int | None = None) -> tuple[int, int]:
        with closing(self.db.get_connection()) as conn:
            k = conn.execute("SELECT interviews FROM search_keywords WHERE keyword = ?", (keyword,)).fetchone()
            s = None
            if search_id is not None:
                s = conn.execute("SELECT interviews FROM keyword_searches WHERE search_id = ?",
                                 (search_id,)).fetchone()
        return (int(k[0]) if k else 0, int(s[0]) if s else 0)

    def update_current_score(self, keyword: str, score: float, recent_rate: float | None) -> None:
        with closing(self.db.get_connection()) as conn:
            conn.execute("UPDATE search_keywords SET current_score = ?, recent_success_rate = ? WHERE keyword = ?",
                         (score, recent_rate, keyword))
            conn.commit()