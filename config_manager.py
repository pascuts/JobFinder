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

# config_manager.py
import os

class ConfigManager:
    AI_COPILOT = "copilot"
    AI_GEMINI = "gemini"
    AI_GROQ = "groq"

    # Default File Paths and Settings
    # Configuration Keys
    DEFAULT_CONFIG_PATH = "..\..\myprivatedata\config.txt"
    KEY_NO_PAGES = "on_keyword_pages"
    KEY_NO_JOBS = "on_keyword_jobs"
    KEY_SUCCESS_MATCHES = "on_keyword_matches"
    KEY_CHANNEL = "channel"
    KEY_USER_DATA_DIR = "user_data_dir"
    KEY_MY_PROF_PROFILE = "my_prof_profile"
    KEY_GEM_CACHE_DURATION = "gemini_cache_duration"
    DAY_SUCCCESS_TARGET = "daily_success_target"
    # ---- keyword search limits (add these lines to config.txt to change the defaults) ----
    # on_keyword_pages / on_keyword_jobs / on_keyword_matches (above) are the per-keyword limits:
    #   max result pages, max jobs extracted & searched, max 'toapply' successes.
    KEY_MAX_READS_DAY = "max_jobs_read_per_day"            # job pages opened per day
    KEY_MAX_AI_CALLS_DAY = "max_ai_calls_per_day"          # Gemini requests per day (never above 250)
    KEY_PREFILTER_FAIL_MAX = "on_page_prefilter_fail_max"  # of ~25 new jobs on a page, max allowed to fail preselection
    KEY_PREFILTER_PENALTY = "prefilter_fail_score_penalty" # keyword score points lost per page over that limit
    KEY_INTERVIEW_BOOST = "interview_score_boost"          # +x weight per interview (0.15 = +15%)
    KEY_KEYWORD_MAX_SHARE = "keyword_max_share_pct"        # max % of the daily target one keyword may deliver

    # Prefilter configuration keys
    KEY_MIN_DAY_RATE = "min_day_rate_gbp"
    KEY_MIN_SALARY = "min_salary_gbp"
    KEY_PASS_SCORE = "pass_score"
    KEY_MAX_DESC_CHARS = "max_desc_chars_for_ai"

    DEFAULTS = {
        KEY_NO_PAGES: 2,
        KEY_NO_JOBS: 40,
        KEY_SUCCESS_MATCHES: 10,
        KEY_MAX_READS_DAY: 250,
        KEY_MAX_AI_CALLS_DAY: 250,
        KEY_PREFILTER_FAIL_MAX: 15,
        KEY_PREFILTER_PENALTY: 0.5,
        KEY_INTERVIEW_BOOST: 0.15,
        KEY_KEYWORD_MAX_SHARE: 20,
        KEY_MIN_DAY_RATE: 350,
        KEY_MIN_SALARY: 65000,
        KEY_PASS_SCORE: 5,
        KEY_MAX_DESC_CHARS: 6000,
    }

    def __init__(self, config_path=DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.config = self.load_config()

    def load_config(self):
        config = {}
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        config[key.strip()] = value.strip().strip('"').strip("'")
        return config

    def get_constant(self, constant):
        """Returns the saved profile folder and a dictionary of secondary configuration settings.""" 
        return self.config.get(constant)

    def get_int(self, key, default=None) -> int:
        """Integer setting; falls back to DEFAULTS (or `default`) when missing or not a number."""
        fallback = default if default is not None else self.DEFAULTS.get(key)
        try:
            return int(float(self.config.get(key)))
        except (TypeError, ValueError):
            return fallback

    def get_float(self, key, default=None) -> float:
        fallback = default if default is not None else self.DEFAULTS.get(key)
        try:
            return float(self.config.get(key))
        except (TypeError, ValueError):
            return fallback

    def save_constant(self, key, value): 
        """Updates a single key in self.config and rewrites the full configuration file."""        
        # Update or set the specific value
        self.config[key] = str(value)        
        # Rewrite all configurations back to file
        with open(self.config_path, "w", encoding="utf-8") as f:
            for k, v in self.config.items():
                f.write(f"{k}\t=\t{v}\n")
                
                
    # DEPRECATED Predefined domain queries
    DOMAIN_SEARCHES = [
        ('domain_architecture', '"Enterprise Architect","Solution Architect","Cloud Architect","Technical Architect"'),
        ('domain_management', '"Program Manager","Delivery Manager","Project Manager","PMO Lead","Transformation Manager","Software Manager"'),
        ('domain_agile', '"Scrum Master","Agile Coach","Agile" OR "Kanban","Release","Agile Project Manager"'),
        ('domain_security', '"Information Security","Cybersecurity,Governance Manager,"Security Risk Compliance","PCI-DSS","Vulnerability","IT Security","Information Security Manager","CISO"'),
        ('domain_technical', '"Java Technical Lead" OR "Engineering Manager" OR "DevOps Delivery Lead" OR "Java Software Architect" OR "Principal Engineer" OR "C++ Systems Architect" OR "Lead Software Engineer" OR "Technical SME" NOT "Junior"'),
        ('domain_leadership', '"Head of Engineering","Director of IT","CTO","Head of Delivery","IT Operations Manager","Interim IT Director","VP of Engineering" OR "Director of Software Engineering"'),
    ]