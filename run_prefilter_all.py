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

from db_tracker import DatabaseTracker
from job_prefilter import prefilter

def run_job_prefilter():
    tracker = DatabaseTracker()
    jobs = tracker.get_all_jobs_for_prefilter()
    
    print(f"Starting prefilter analysis on {len(jobs)} jobs...\n")
    
    passed_count = 0
    failed_count = 0
    
    for job in jobs:
        job_id = str(job.get("job_id", "")).strip()
        if not job_id:
            continue
            
        # Execute stage A (title_gate) & stage B (prefilter)
        res = prefilter(job)
        
        passed_flag = "Y" if res.passed else "N"
        score = res.score
        reason = res.reason
        
        # Save or update prefilter evaluation in SQLite
        tracker.save_prefilter_result(
            job_id=job_id,
            passed=passed_flag,
            score=score,
            reason=reason
        )
        
        if res.passed:
            passed_count += 1
        else:
            failed_count += 1
            
        print(f"[{passed_flag}] Job ID: {job_id:<12} | Score: {score:>3} | Reason: {reason}")

    print(f"\nFinished prefilter execution!")
    print(f"Total: {len(jobs)} | Passed (Y): {passed_count} | Failed (N): {failed_count}")

if __name__ == "__main__":
    run_job_prefilter()