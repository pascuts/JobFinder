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

# keyword_scheduler.py
"""
Keyword rotation: which keywords to search today, with what limits, and how their score evolves.

  weight    = current_score ** sharpness
  priority  = weight * days since the keyword was last searched   (stride scheduling:
              nothing starves, heavier keywords just come round more often; any keyword idle for
              `max_days_without_search` is forced in)
  quota     = share of the day's success target, proportional to weight, clamped to
              [min_share, max_share] of the target and to the success cap (config.txt, or per keyword)

  current_score = clamp( base_score * yield_multiplier * boost * interview_factor - prefilter_penalty , 1, 15 )

     yield_multiplier  measured successes per job read, shrunk towards domain/global average, time-decayed
     interview_factor  1 + interview_boost * interviews        (capped)
     prefilter_penalty each page that exceeded the allowed prefilter failures costs `prefilter_penalty`
                       points, recovering with a half-life of `penalty_half_life_days`
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from keyword_store import KeywordStore, TS


@dataclass
class SearchLimits:
    # ---- daily budget ----------------------------------------------------
    daily_success_target: int = 35
    max_reads_per_day: int = 250          # job pages opened per day
    max_ai_calls_per_day: int = 250       # Gemini requests per day (hard ceiling enforced in db_tracker)

    # ---- per keyword (config.txt; per-keyword overrides live in search_keywords) -----
    max_pages_per_keyword: int = 2
    max_reads_per_keyword: int = 40       # jobs extracted & searched per keyword
    min_reads_per_keyword: int = 8
    read_safety: float = 1.5
    abs_max_success_per_keyword: int = 10
    max_share_per_keyword: float = 0.20   # one keyword may deliver at most 20% of the daily target
    min_share_per_keyword: float = 0.05
    max_prefilter_fail_per_page: int = 15 # of the ~25 new jobs on a page
    prefilter_penalty: float = 0.5        # score points lost per page over that limit
    penalty_half_life_days: float = 14.0

    # ---- interviews ----------------------------------------------------------
    interview_boost: float = 0.15         # +15% weight per interview
    interview_boost_cap: float = 2.0

    # ---- rotation ----------------------------------------------------------
    overbook: float = 1.4
    max_keywords_per_day: int | None = None
    sharpness: float = 1.5
    max_days_without_search: int = 10
    max_forced_per_day: int = 3

    # ---- learning ----------------------------------------------------------
    prior_yield: float = 0.15
    maybe_weight: float = 0.25
    half_life_days: float = 10.0
    history_days: int = 60
    pseudo_reads_global: float = 50
    pseudo_reads_domain: float = 30
    pseudo_reads_keyword: float = 15
    yield_exponent: float = 0.75
    yield_mult_min: float = 0.5
    yield_mult_max: float = 2.0
    min_score: float = 1.0
    max_score: float = 15.0               # >10 means 'outperforms the top tier' (proven keywords rank higher)

    # ---- query building ----------------------------------------------------
    quote_phrases: bool = True
    default_recency_days: int = 7

    @classmethod
    def from_config(cls, cfg) -> "SearchLimits":
        """Reads config.txt through ConfigManager (get_int/get_float carry the defaults)."""
        from config_manager import ConfigManager as C
        L = cls()
        L.daily_success_target = cfg.get_int(C.DAY_SUCCCESS_TARGET)
        L.max_pages_per_keyword = cfg.get_int(C.KEY_NO_PAGES)
        L.max_reads_per_keyword = cfg.get_int(C.KEY_NO_JOBS)
        L.abs_max_success_per_keyword = cfg.get_int(C.KEY_SUCCESS_MATCHES)
        L.max_reads_per_day = cfg.get_int(C.KEY_MAX_READS_DAY)
        L.max_ai_calls_per_day = min(cfg.get_int(C.KEY_MAX_AI_CALLS_DAY), 250)   # 250 is the ceiling
        L.max_prefilter_fail_per_page = cfg.get_int(C.KEY_PREFILTER_FAIL_MAX)
        L.prefilter_penalty = cfg.get_float(C.KEY_PREFILTER_PENALTY)
        L.interview_boost = cfg.get_float(C.KEY_INTERVIEW_BOOST)
        L.max_share_per_keyword = cfg.get_float(C.KEY_KEYWORD_MAX_SHARE) / 100.0
        L.min_reads_per_keyword = min(L.min_reads_per_keyword, L.max_reads_per_keyword)
        return L


@dataclass
class KeywordPlan:
    keyword: str
    domain: str
    base_score: float
    score: float                 # current score used for this plan
    query: str
    quota: int                   # max 'toapply' successes this search may deliver
    target_pct: float            # quota as % of the daily target
    max_pages: int
    max_reads: int
    max_prefilter_fail: int
    recency_seconds: int
    weight: float
    days_since: float
    est_yield: float


def allocate_quotas(weights: list[float], total: float, lo: int, hi: int) -> list[int]:
    """Water-filling: split `total` proportionally to `weights`, keep every item in
    [lo, hi], redistribute what clamping frees up, then round (largest remainder)."""
    n = len(weights)
    if n == 0:
        return []
    lo, hi = min(lo, hi), max(lo, hi)
    alloc = [0.0] * n
    free = set(range(n))
    remaining = float(total)

    for _ in range(n + 1):
        if not free:
            break
        wsum = sum(weights[i] for i in free) or 1.0
        prop = {i: remaining * weights[i] / wsum for i in free}
        low = [i for i in free if prop[i] < lo]
        high = [i for i in free if prop[i] > hi]
        if not low and not high:
            for i in free:
                alloc[i] = prop[i]
            free.clear()
            break
        if len(low) >= len(high) and low:
            for i in low:
                alloc[i] = lo; remaining -= lo; free.discard(i)
        else:
            for i in high:
                alloc[i] = hi; remaining -= hi; free.discard(i)
        remaining = max(remaining, 0.0)
    for i in free:
        alloc[i] = max(lo, min(hi, remaining / max(len(free), 1)))

    base = [int(math.floor(a)) for a in alloc]
    leftover = int(round(sum(alloc))) - sum(base)
    for i in sorted(range(n), key=lambda i: alloc[i] - base[i], reverse=True):
        if leftover <= 0:
            break
        if base[i] < hi:
            base[i] += 1
            leftover -= 1
    return [max(lo, min(hi, b)) for b in base]


class _Evidence:
    """Time-decayed yield and prefilter penalties computed from the keyword_searches history."""

    def __init__(self, rows: list[dict], now: datetime, L: SearchLimits):
        self.L = L
        self.kw: dict = {}      # keyword -> [decayed succ(+maybe), decayed reads, decayed succ, decayed ai_jobs]
        self.dom: dict = {}
        self.pen: dict = {}     # keyword -> decayed penalty points
        g_s = g_r = 0.0
        for r in rows:
            age = max((now - datetime.strptime(r["run_at"], TS)).total_seconds() / 86400.0, 0.0)
            w = 0.5 ** (age / L.half_life_days)
            s = w * ((r["successes"] or 0) + L.maybe_weight * (r["maybes"] or 0))
            # reads still waiting for the AI verdict carry no information yet
            rd = w * max((r["reads"] or 0) - (r.get("pending") or 0), 0)
            g_s += s
            g_r += rd
            a = self.kw.setdefault(r["keyword"], [0.0, 0.0, 0.0, 0.0])
            a[0] += s
            a[1] += rd
            a[2] += w * (r["successes"] or 0)
            a[3] += w * (r["ai_jobs"] or 0)
            d = self.dom.setdefault(r["domain"], [0.0, 0.0])
            d[0] += s
            d[1] += rd
            if r["bad_pages"]:
                pw = 0.5 ** (age / L.penalty_half_life_days)
                self.pen[r["keyword"]] = self.pen.get(r["keyword"], 0.0) + r["bad_pages"] * L.prefilter_penalty * pw
        self.y_global = (g_s + L.prior_yield * L.pseudo_reads_global) / (g_r + L.pseudo_reads_global)

    def y_domain(self, dom) -> float:
        s, r = self.dom.get(dom, (0.0, 0.0))
        return (s + self.y_global * self.L.pseudo_reads_domain) / (r + self.L.pseudo_reads_domain)

    def y_keyword(self, kw, dom) -> float:
        s, r = self.kw.get(kw, (0.0, 0.0, 0.0, 0.0))[:2]
        return (s + self.y_domain(dom) * self.L.pseudo_reads_keyword) / (r + self.L.pseudo_reads_keyword)

    def recent_rate(self, kw) -> float | None:
        v = self.kw.get(kw)
        return (v[2] / v[3]) if v and v[3] > 0 else None


class KeywordScheduler:
    def __init__(self, db_tracker, limits: SearchLimits | None = None):
        self.db = db_tracker
        self.limits = limits or SearchLimits()
        self.store = KeywordStore(db_tracker)

    # ---- thin wrappers ----------------------------------------------------
    def sync_keywords(self, seed) -> int:
        return self.store.seed_missing(seed)

    def set_boost(self, keyword, factor):
        self.store.set_boost(keyword, factor)

    def register_user_keyword(self, text: str):
        """Keyword typed in the UI -> (row, created). Saved with domain 'user_insert' if it is new."""
        return self.store.add_user_keyword(text)

    def describe_keyword(self, row: dict) -> str:
        """One line with the keyword's parameters; '(n)' is the config.txt default used when the
        keyword has no override of its own."""
        L = self.limits

        def lim(v, default):
            return str(v) if v else f"({default})"

        def num(v, fmt="{:.2f}"):
            return fmt.format(v) if isinstance(v, (int, float)) else "-"

        ai = row.get("total_ai_jobs") or 0
        rate = f"{(row.get('success_rate') or 0):.0%} ({row.get('total_successes') or 0}/{ai})" if ai else "n/a"
        parts = [f"'{row['keyword']}'", f"domain {row.get('domain') or '-'}"]
        if row.get("query"):
            parts.append(f"query {row['query']}")
        parts += [
            f"score base {num(row.get('base_score'))} -> current {num(row.get('current_score'))}",
            f"boost x{(row.get('boost') or 1.0):g}",
            f"enabled {'yes' if row.get('enabled', 1) else 'no'}",
            f"max pages {lim(row.get('max_pages'), L.max_pages_per_keyword)}",
            f"max jobs {lim(row.get('max_jobs'), L.max_reads_per_keyword)}",
            f"max successes {lim(row.get('max_success'), L.abs_max_success_per_keyword)}",
            f"max prefilter fails/page {lim(row.get('max_prefilter_fail'), L.max_prefilter_fail_per_page)}",
            f"interviews {row.get('interviews') or 0}",
            f"searches {row.get('total_searches') or 0}",
            f"success rate {rate}",
            f"last searched {row.get('last_searched_display') or 'never'}",
        ]
        return " | ".join(parts)

    def today_totals(self, now=None) -> dict:
        t = self.store.today_totals(now)
        t["ai_calls"] = self.db.ai_calls_today()
        return t

    # ------------------------------------------------------------------ #
    # Score
    # ------------------------------------------------------------------ #
    def compute_score(self, kwrow: dict, ev: _Evidence) -> float:
        L = self.limits
        mult = (ev.y_keyword(kwrow["keyword"], kwrow["domain"]) / ev.y_global) ** L.yield_exponent
        mult = min(max(mult, L.yield_mult_min), L.yield_mult_max)
        inter = min(1 + L.interview_boost * (kwrow.get("interviews") or 0), L.interview_boost_cap)
        raw = kwrow["base_score"] * mult * (kwrow.get("boost") or 1.0) * inter - ev.pen.get(kwrow["keyword"], 0.0)
        return min(max(raw, L.min_score), L.max_score)

    def _score_fn(self, kwrow, hist, now) -> dict:
        ev = _Evidence(hist, now, self.limits)
        return {"score": self.compute_score(kwrow, ev), "recent_success_rate": ev.recent_rate(kwrow["keyword"])}

    def _evidence(self, now) -> _Evidence:
        return _Evidence(self.store.history(now - timedelta(days=self.limits.history_days)), now, self.limits)

    # ------------------------------------------------------------------ #
    # Plan
    # ------------------------------------------------------------------ #
    def plan_day(self, now: datetime | None = None, domain: str | None = None) -> list[KeywordPlan]:
        L = self.limits
        now = now or datetime.now()
        remaining = L.daily_success_target - self.store.today_totals(now)["successes"]
        if remaining <= 0:
            return []
        rows = self.store.get_enabled(domain)
        if not rows:
            return []
        ev = self._evidence(now)

        cands = []
        for r in rows:
            last = r["last_searched_at"]
            days = max((now - datetime.strptime(last, TS)).total_seconds() / 86400.0, 0.0) if last \
                else float(L.max_days_without_search)
            score = self.compute_score(r, ev)
            weight = score ** L.sharpness
            cands.append({"row": r, "days": days, "score": score, "weight": weight,
                          "est": ev.y_keyword(r["keyword"], r["domain"]),
                          "priority": weight * max(days, 0.05)})

        T = L.daily_success_target
        q_lo = max(1, round(T * L.min_share_per_keyword))
        q_hi = max(q_lo, min(L.abs_max_success_per_keyword, round(T * L.max_share_per_keyword)))
        q_hi = min(q_hi, max(remaining, 1))
        q_lo = min(q_lo, q_hi)

        n_slots = L.max_keywords_per_day or max(3, math.ceil(remaining * L.overbook / q_hi))
        n_slots = min(n_slots, len(cands))

        due = L.max_days_without_search - 0.5      # half a day of grace for time-of-day drift
        forced = sorted((c for c in cands if c["days"] >= due),
                        key=lambda c: (-c["days"], -c["weight"]))[: L.max_forced_per_day]
        chosen = list(forced)
        taken = {c["row"]["keyword"] for c in chosen}
        for c in sorted(cands, key=lambda c: -c["priority"]):
            if len(chosen) >= n_slots:
                break
            if c["row"]["keyword"] not in taken:
                chosen.append(c)
                taken.add(c["row"]["keyword"])

        quotas = allocate_quotas([c["weight"] for c in chosen], remaining * L.overbook, q_lo, q_hi)

        plans = [self._make_plan(c["row"], c["score"], c["weight"], c["days"], c["est"], q, due)
                 for c, q in zip(chosen, quotas)]
        plans.sort(key=lambda p: -p.days_since)   # most neglected first
        return plans

    def plan_for_keyword(self, keyword: str, now: datetime | None = None) -> KeywordPlan:
        """Ad-hoc search typed by the user: registered in search_keywords so it is tracked like any other."""
        L = self.limits
        now = now or datetime.now()
        row, _ = self.store.add_user_keyword(keyword)        # existing keyword (any case) or new 'user_insert'
        keyword = row["keyword"]
        ev = self._evidence(now)
        score = self.compute_score(row, ev)
        remaining = max(L.daily_success_target - self.store.today_totals(now)["successes"], 1)
        quota = max(1, min(L.abs_max_success_per_keyword, remaining))
        last = row["last_searched_at"]
        days = max((now - datetime.strptime(last, TS)).total_seconds() / 86400.0, 0.0) if last \
            else float(L.max_days_without_search)
        return self._make_plan(row, score, score ** L.sharpness, days,
                               ev.y_keyword(keyword, row["domain"]), quota,
                               L.max_days_without_search - 0.5)

    def _make_plan(self, row, score, weight, days, est, quota, due) -> KeywordPlan:
        L = self.limits
        if row.get("max_success"):
            quota = max(1, min(quota, int(row["max_success"])))
        max_pages = int(row.get("max_pages") or L.max_pages_per_keyword)
        reads_cap = int(row.get("max_jobs") or L.max_reads_per_keyword)
        adaptive = math.ceil(quota / max(est, 0.02) * L.read_safety)
        reads = max(min(L.min_reads_per_keyword, reads_cap), min(reads_cap, adaptive))
        recency_days = L.default_recency_days if days >= due else min(max(math.ceil(days) + 1, 1), 30)
        return KeywordPlan(
            keyword=row["keyword"], domain=row["domain"] or "custom", base_score=row["base_score"],
            score=round(score, 2), query=self._build_query(row["keyword"], row.get("query")),
            quota=quota, target_pct=round(100.0 * quota / max(L.daily_success_target, 1), 1),
            max_pages=max_pages, max_reads=reads,
            max_prefilter_fail=int(row.get("max_prefilter_fail") or L.max_prefilter_fail_per_page),
            recency_seconds=recency_days * 86400, weight=round(weight, 2),
            days_since=round(days, 1), est_yield=round(est, 3),
        )

    def _build_query(self, keyword: str, override: str | None) -> str:
        if override:
            return override.replace('"', '').replace("'", '').strip()
        
        k = keyword.strip().replace('"', '').replace("'", '')
        return k
    # ------------------------------------------------------------------ #
    # Record / interviews
    # ------------------------------------------------------------------ #
    def record_search(self, plan: KeywordPlan, search_id: int | None, pages: int, reads: int,
                      title_rejected: int, prefilter_failed: int, ai_jobs: int, ai_calls: int,
                      successes: int, maybes: int, bad_pages: int, stop_reason: str,
                      now: datetime | None = None) -> dict:
        """Insert the search row AND refresh the keyword row (totals + current score) in one transaction."""
        return self.store.record_search(
            {"search_id": search_id, "keyword": plan.keyword, "quota": plan.quota,
             "target_pct": plan.target_pct, "pages": pages, "reads": reads,
             "title_rejected": title_rejected, "prefilter_failed": prefilter_failed, "ai_jobs": ai_jobs,
             "ai_calls": ai_calls, "successes": successes, "maybes": maybes, "bad_pages": bad_pages,
             "stop_reason": stop_reason},
            self._score_fn, self.limits.history_days, now)

    def update_search_ai_results(self, search_id: int, ai_calls: int = 0,
                                 now: datetime | None = None) -> dict | None:
        """Called after the AI scoring of a search's jobs. Re-derives the search's AI numbers from the
        jobs table, then refreshes the search_keywords totals and the keyword's current score so the next
        plan_day() rotates on real results. ai_calls = Gemini requests used in this round for this search."""
        return self.store.update_ai_results(search_id, self._score_fn, self.limits.history_days, ai_calls, now)

    def adjust_interviews(self, keyword: str, delta: int, search_id: int | None = None) -> int:
        """+1/-1 interview, then recompute the keyword's current score straight away."""
        total = self.store.adjust_interviews(keyword, delta, search_id)
        row = self.store.get_keyword(keyword)
        if row:
            ev = self._evidence(datetime.now())
            self.store.update_current_score(keyword, self.compute_score(row, ev), ev.recent_rate(keyword))
        return total