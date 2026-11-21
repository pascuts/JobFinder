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

import os, random, collections, sys, tempfile
from datetime import datetime, timedelta
from db_tracker import DatabaseTracker
from keyword_scheduler import KeywordScheduler, SearchLimits
from keyword_seed import KEYWORD_SEED, INITIAL_BOOSTS

def simulate(days=40, seed=7, limits=None, quiet=False):
    random.seed(seed)
    path = os.path.join(tempfile.gettempdir(), "sim_rotation.db")
    if os.path.exists(path): os.remove(path)
    db = DatabaseTracker(db_filename=path)
    L = limits or SearchLimits()
    sch = KeywordScheduler(db, L)
    sch.sync_keywords(KEYWORD_SEED)
    for k, b in INITIAL_BOOSTS.items(): sch.set_boost(k, b)
    truth = {}
    for kw, dom, score, _ in KEYWORD_SEED:
        base = {"architecture":.16,"management":.20,"security":.12,"leadership":.08,"technical":.12,"agile":.10}[dom]
        truth[kw] = base * random.uniform(.5, 1.6)
    truth["Enterprise Architect"] = .34
    truth["Digitalisation Strategy Lead"] = .30
    truth["Scrum Master"] = .30
    start = datetime(2026, 10, 1, 7, 0, 0)
    searches = collections.Counter(); succ = collections.Counter()
    gaps = collections.defaultdict(list); last = {}
    day_totals = []; reads_days = []; max_share = 0
    for d in range(days):
        now = start + timedelta(days=d)
        tot = 0; reads_day = 0
        for rnd in range(3):
            if tot >= L.daily_success_target or reads_day >= L.max_reads_per_day: break
            plans = sch.plan_day(now + timedelta(minutes=10 * rnd))
            if not plans: break
            for p in plans:
                if tot >= L.daily_success_target or reads_day >= L.max_reads_per_day: break
                reads = succ_k = pages = 0; stop = "pages"
                while pages < p.max_pages and reads < p.max_reads and succ_k < p.quota:
                    pages += 1
                    for _ in range(25):
                        if reads >= p.max_reads: stop = "reads"; break
                        if reads_day >= L.max_reads_per_day: stop = "day_reads"; break
                        reads += 1; reads_day += 1
                        if random.random() < truth[p.keyword]:
                            succ_k += 1; tot += 1
                        if succ_k >= p.quota: stop = "quota"; break
                        if tot >= L.daily_success_target: stop = "daily"; break
                    if stop in ("quota", "daily", "day_reads"): break
                sch.record_search(p, None, pages, reads, 0, reads // 4, reads - reads // 4, reads, succ_k, 0, 0, stop,
                                  now=now + timedelta(minutes=10 * rnd + 5))
                searches[p.keyword] += 1; succ[p.keyword] += succ_k
                if p.keyword in last: gaps[p.keyword].append(d - last[p.keyword])
                last[p.keyword] = d
                max_share = max(max_share, succ_k / L.daily_success_target)
        day_totals.append(tot); reads_days.append(reads_day)
    return dict(day_totals=day_totals, reads_days=reads_days, max_share=max_share, searches=searches,
                succ=succ, gaps=gaps, truth=truth)

if __name__ == "__main__":
    r = simulate()
    L = SearchLimits()
    dt = r["day_totals"]
    print("successes/day:", dt)
    print("avg %.1f | max %d | max reads/day %d | max keyword share %.0f%%" %
          (sum(dt)/len(dt), max(dt), max(r["reads_days"]), r["max_share"]*100))
    print("never searched:", [k for k,_,_,_ in KEYWORD_SEED if r["searches"][k]==0])
    print("max gap (days):", max(max(g) for g in r["gaps"].values() if g))
    print(f"\n{'keyword':38}{'score':>6}{'true':>7}{'runs':>6}{'succ':>6}{'avg gap':>9}")
    for kw, dom, score, _ in sorted(KEYWORD_SEED, key=lambda x:-x[2]):
        if kw in ("Enterprise Architect","Digitalisation Strategy Lead","Scrum Master","Programme Manager",
                  "Delivery Manager","Head of Delivery","Agile Coach","CTO","CISO","Director of IT","Solution Architect"):
            g = r["gaps"][kw]
            print(f"{kw:38}{score:>6}{r['truth'][kw]:>7.2f}{r['searches'][kw]:>6}{r['succ'][kw]:>6}{(sum(g)/len(g) if g else 0):>9.1f}")
