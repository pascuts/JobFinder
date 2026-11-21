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

# job_prefilter.py
"""
Free, local Y/N gate that runs BEFORE any Gemini call.

Stage A  title_gate(title)   -> run on the results CARD, before opening the job page.
Stage B  prefilter(job)      -> run on the extracted job dict, before Gemini.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from config_manager import ConfigManager

# =============================== CONFIG ===============================
_cfg = ConfigManager()
MIN_DAY_RATE_GBP = _cfg.get_int(ConfigManager.KEY_MIN_DAY_RATE, 350)
MIN_SALARY_GBP = _cfg.get_int(ConfigManager.KEY_MIN_SALARY, 65_000)
PASS_SCORE = _cfg.get_int(ConfigManager.KEY_PASS_SCORE, 5)                  # Score threshold for Gemini gate
MAX_DESC_CHARS_FOR_AI = _cfg.get_int(ConfigManager.KEY_MAX_DESC_CHARS, 6000)

CLEARANCE_HELD: set[str] = set()
REJECT_EMPLOYMENT = {"part-time", "internship", "volunteer", "apprenticeship"}

LACKING_CERTS = ["cissp", "cism", "cisa", "crisc"]
HELD_CERTS = ["prince2", "psm", "togaf", "agilepm", "six sigma", "scrum master", "csm"]

_ALWAYS_SUBSTR = {"jira", "scrum", "agile", "audit", "confluence", "kanban", "devops"}
_LEFT_GUARD = {"migration": r"(?<!\w)"}


def _term_rx(term: str) -> str:
    core = term.lower()
    t = re.escape(core).replace(r"\ ", r"[\s\-]*").replace(r"\-", r"[\s\-]*")
    compact = re.sub(r"[\s\-]", "", core)
    if core in _ALWAYS_SUBSTR or len(compact) >= 6:
        return _LEFT_GUARD.get(core, "") + t
    return rf"(?<!\w){t}(?!\w)"


def _any(terms: list[str]) -> re.Pattern:
    return re.compile("|".join(_term_rx(t) for t in terms), re.I)


def _compile(patterns) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.I)


def _norm(t: str) -> str:
    return re.sub(r"[\u2010-\u2015\u2212]", "-", (t or "")).replace("\u00a0", " ")


# =============================== STAGE A: TITLE GATE ===============================

# --- Tier 1: Hard Deny Rules (Junior levels, Construction, Health/Medical, HR/Recruiting) ---
TITLE_DENY = _compile([
    # Junior / Entry Level / Non-leadership support (removed coordinator)
    r"\b(junior|graduate|apprentice|apprenticeship|intern|internship|trainee|administrator)\b",
    r"\b(?<!assistant\s)assistant(?!\s+manager)\b",
    
    # Construction / Civil / Engineering / Trades / Real Estate
    r"\b(construction|civil|structural|mechanical|electrical|quantity\s+surveyor|surveyor|building|"
    r"interior|landscape|fit[\s\-]?out|m&e|mep|highways|site\s+manager|facilities|estates|fire|wind|solar|"
    r"nuclear|oil|gas|architectural|foreman|estimator|bim|property|asset\s+management)\b",
    
    # Health / Medical / Clinical / Care / Bio
    r"\b(health|healthcare|medical|clinical|nurse|nursing|doctor|physician|patient|care|carer|pharmacy|"
    r"pharmacist|biomedical|therapist|mental\t|dental|dentist|veterinary|radiographer|nhs\s+care)\b",
    
    # HR / People Operations / Talent Acquisition / Recruiting / Finance / Sales (removed business development)
    r"\b(hr|human\s+resources|people\s+partner|talent|recruiter|recruitment|resourcer|payroll|"
    r"accounting|accountant|auditor|marketing|account\s+manager|sales\s+executive)\b",
])
# --- Tier 2 & 3: High-Confidence Target Roles (Pass-through Bucketing) ---
TITLE_ALLOW = _compile([
    # Project, Programme, Delivery, Transformation, Change & Coordinators
    r"\b(programme|program|project|delivery|release|transformation|portfolio|change|people\s+projects?)\s+(manager|lead|director|specialist|consultant|co-?ordinator)\b",
    r"\b(business\s+change|change\s+acceleration|project\s+controls|programme\s+planning\s*&\s*enablement)\b",
    r"\bpmo\b",
    
    # General, Operations, Information, IT Support, IT Asset, Network, Risk, Implementation, Engagement, Product Management
    r"\b(general|operations|information|it\s+support|it\s+asset|network|risk|implementation|engagement|product|data\s+product|it\s+systems|infrastructure\s+and\s+operations|enterprise\s+implementation|senior\s+risk\s*&\s*opportunity)\s+manager\b",
    r"\bmanager\b",
    
    # Engineering, DevOps, Cloud Security, Analytics, Systems & Technical Roles
    r"\b(devops|cloud\s+platform\s+security|cloud|software|infrastructure|security|cyber|data|analytics\s+and\s+statistics|technical|solutions?)\s+(engineer|developer|specialist|analyst)\b",
    r"\bcloud\s+platform\s+security\s+engineer\b",
    r"\bdevops\s+engineer\b",
    
    # Analysts, Specialists, SMEs, Partners, Business Analysts
    r"\b(security\s+intelligence|cyber\s+security|business|data|systems?|cyber\s+security)\s+(analyst|specialist|partner|sme)\b",
    r"\bbusiness\s+analyst\b",
    r"\bzscaler\s+sme\b",
    r"\bsme\b",
    r"\bcyber\s+security\s+business\s+partner\b",
    
    # Architecture & Platforms
    r"\b(technical|solution|solutions|security|integration|cloud|enterprise|application|portfolio|data\s+intelligent|product)\s+architect(\s+manager)?\b",
    
    # Team Leadership & Executive / CTO / Co-Founder
    r"\bteam\s+(lead|manager)\b",
    r"\btech\s+lead\b",
    r"\bengineering\s+manager\b",
    r"\b(cto|co-?founder)\b",
    r"\bassistant\s+director\b",
    
    # Information Security, GRC & Audit
    r"\binformation\s+security\b",
    r"\b(security|cyber\s?security|digital|tech|cyber|it)\s+(audit|auditor)\b",
    r"\b(security|cyber\s?security|digital|tech|cyber)\s+(manager|governance|compliance|risk|programme|program|delivery|lead|officer|consultant|assistant\s+manager|audit\s+manager)\b",
    r"\bgrc\b", r"\bisms\b",
    
    # IT Operations & Service Delivery
    r"\bit\s+(operations|service\s+delivery|infrastructure)\s+(manager|director|head)\b",
    r"\bclient\s+technology\b",
    r"\bbusiness\s+development\s+manager\b",
    
    # Tech stack single-word or short titles
    r"\bjava\b",
    
    r"\bexpert\s+opportunity\b",
    r"\bexpression\s+of\s+interest\b",
    r"\bassociate\s+(transformation|reporting|intelligence|project|delivery)\b",
    r"\bvice\s+president\b",
])
# Ambiguous / Non-standard titles allowed through to Stage B evaluation
AMBIGUOUS_PASS = _compile([
    r"\b(principal|lead|head|director|chief|vp|vice\s+president)\b",
    r"\b(consultant|strategist|advisor|chapter\tlead)\b",
    r"\bmanagement\s+consultant\b",
])


def normalize_title(title: str) -> str:
    """Tier 2: Clean and normalize non-standard/spatial formatting."""
    t = _norm(title)
    # Remove bracketed metadata e.g. "(Contract)", "[Ref:1234]"
    t = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", t)
    # Remove punctuation & symbols except hyphen/spaces
    t = re.sub(r"[^\w\s\-]", " ", t)
    # Collapse whitespace
    return re.sub(r"\s+", " ", t).strip().lower()


def title_gate(title: str) -> tuple[bool, str]:
    raw_norm = _norm(title).strip()
    if not raw_norm:
        return True, "no title on card (let extraction decide)"

    clean_t = normalize_title(raw_norm)

    # 1. Tier 1: Check Blacklist (Hard Deny)
    deny_match = TITLE_DENY.search(clean_t)
    if deny_match:
        return False, f"Title [{title}] reject: '{deny_match.group(0)}'"

    # 2. Tier 3: Check Whitelist (Target Roles)
    if TITLE_ALLOW.search(clean_t):
        return True, "Title ok (explicit match)"

    # 3. Tier 3: Check Ambiguous Titles (Defer to Stage B / Description Prefilter)
    if AMBIGUOUS_PASS.search(clean_t):
        return True, "Title ok (ambiguous/broad role passed to stage B)"

    return False, "Title [{title}] not in allow-list"


# =============================== STAGE B: DESCRIPTION PREFILTER ===============================
IT_CONTEXT = _any([
    "software", "cloud", "infrastructure", "cyber", "cybersecurity", "information security", "digital",
    "technology", "applications", "platform", "devops", "agile", "saas", "erp", "data centre",
    "data center", "it project", "it programme", "it delivery", "it operations", "it security",
    "it transformation", "information technology", "migration", "plm", "payments", "sovereign",
    "private cloud", "transition", "enterprise", "solutions", "ai", "language model", "pmo", "change",
    "digitalisation", "strategy", "sap", "public sector", "consulting", "governance", "project controls"
])
IT_CONTEXT_MIN = 1

SIGNALS: dict[str, tuple[int, int, list[str]]] = {
    "delivery": (3, 15, [
        "programme delivery", "program delivery", "project delivery", "delivery management", "transformation",
        "migration", "cutover", "change request", "stakeholder management", "multi vendor", "raid",
        "risk management", "governance", "pmo", "prince2", "agilepm", "agile project management",
        "benefits realisation", "budget", "supplier management", "vendor management",
        "delivery lead", "software delivery", "delivery assurance", "stakeholder engagement", "work plan",
        "onshore", "offshore", "dependencies", "project manager", "transitions", "transition",
        "change management", "business change", "version 1", "project controls", "public sector"
    ]),
    "agile": (2, 8, ["scrum", "kanban", "sprint", "agile", "devops", "ci/cd", "jira", "confluence",
                     "pi planning", "backlog", "product owner", "sdlc", "agile ceremonies"]),
    "security": (3, 12, [
        "information security", "iso 27001", "pci dss", "grc", "compliance", "vulnerability management",
        "qualys", "iam", "identity and access", "assurance", "audit", "attestation", "cyber security",
        "nist", "soc 2", "risk and compliance", "security governance", "isms", "sovereign", "cyber"
    ]),
    "architecture": (3, 15, [
        "togaf", "enterprise architecture", "solution architecture", "technical architecture",
        "architecture governance", "cloud architecture", "aws", "azure", "integration", "api", "pki",
        "hsm", "payments", "banking", "financial services", "public sector", "automotive", "plm",
        "private cloud", "sovereign", "portfolio architecture", "tech modernisation"
    ]),
    "seniority": (1, 3, ["senior", "lead", "head of", "director", "principal", "manager", "vp", "vice president", "associate"]),
    "legacy_ok": (1, 2, ["java", "spring", "j2ee", "c++", "sap"]),
    "stack_mismatch": (-1, -5, [
        "kubernetes", "terraform", "reactjs", "react.js", "angular", "golang", "rust", "scala",
        "databricks", "snowflake", "bigquery"
    ]),
    "hands_on_dev": (-3, -9, [
        "write code", "writing code", "write and review code", "code review", "pull request",
        "hands-on technical", "actively coded", "hands on development", "you will code"
    ]),
    "platform_mismatch": (0, 0, []),
    "junior": (-4, -8, ["entry level", "graduate scheme", "junior", "0-2 years", "1-2 years", "1-3 years"]),
}
_SIGNAL_RX = {k: [(t, re.compile(_term_rx(t), re.I)) for t in v[2]] for k, v in SIGNALS.items()}

NON_IT_WORDS = _any([
    "civil engineering", "quantity surveying", "highways", "cdm regulations", "residential development",
    "building regulations", "plant and equipment", "preventive maintenance", "predictive maintenance",
    "spare parts", "sterilization", "sterilisation", "ethylene oxide", "production line",
    "manufacturing site", "drivers licence", "driving licence", "clinical trial", "patient care",
    "nursing home", "human resources partner", "talent acquisition partner"
])

# ---- Security Clearance Check ----
_CLR_ANCHOR = re.compile(r"clearance|cleared|vetting|vetted", re.I)
_DV_TOKEN = re.compile(r"(?<!\w)(dv|developed\s+vetting)(?!\w)", re.I)
_SC_TOKEN = re.compile(r"(?<!\w)(sc|security\s+cleared|security\s+clearance)(?!\w)", re.I)
_ELIGIBLE = re.compile(r"eligible|ability to obtain|able to obtain|must be able|willing to undergo", re.I)
_ACTIVE_REQ = re.compile(r"active|must hold|currently hold|holds|valid|in place", re.I)
_DESIRABLE = re.compile(r"desirable|advantageous|preferred|nice to have", re.I)


def clearance_check(text: str) -> tuple[str, str]:
    soft = ""
    for m in _CLR_ANCHOR.finditer(text):
        win = text[max(0, m.start() - 50): m.end() + 50]
        near = text[max(0, m.start() - 25): m.end() + 25]
        is_dv = bool(_DV_TOKEN.search(near))
        sc = _SC_TOKEN.search(near)
        lvl = "dv" if is_dv else (sc.group(0).lower().split()[0] if sc else "")
        if not lvl:
            continue
        if any(h in lvl or lvl in h for h in CLEARANCE_HELD) or _DESIRABLE.search(win):
            continue
        shown = re.sub(r"\s+", " ", win.strip())[:70]
        if is_dv:
            return "reject", f"DV clearance: '...{shown}...'"
        if _ELIGIBLE.search(win) and not _ACTIVE_REQ.search(win):
            soft = f"clearance obtainable: '...{shown}...'"
            continue
        if _ACTIVE_REQ.search(win) or "cleared" in lvl or "sc cleared" in text:
            return "reject", f"active {lvl.upper()} clearance: '...{shown}...'"
    return ("soft", soft) if soft else ("none", "")


LANG_RX = re.compile(
    r"(?:fluent|native|business[\s\-]level|proficient|mother\s+tongue)\s+(?:in\s+)?(?:[\w,]+\s+){0,4}?"
    r"(german|dutch|spanish|italian|portuguese|arabic|polish|swedish|danish|norwegian|finnish|mandarin|japanese)\b"
    r"|(german|dutch|spanish|italian|portuguese|arabic|polish|swedish|danish|norwegian|finnish|mandarin|japanese)"
    r"\s*(?:language)?\s*(?:\(|is\s+)?(?:essential|required|mandatory|fluent|native)\b", re.I)

YEARS_HELD: dict[str, float] = {}
_POSTER_BLOCK = re.compile(r"requirements added by the job poster(.*)$", re.S | re.I)
_POSTER_LINE = re.compile(r"(\d+)\+?\s*years?\s+of\s+(?:work\s+)?experience\s+(?:with|in)\s+([^\n•]+)", re.I)


def poster_requirements(text: str) -> list[tuple[str, int]]:
    m = _POSTER_BLOCK.search(text or "")
    if not m:
        return []
    return [(mm.group(2).strip().lower(), int(mm.group(1))) for mm in _POSTER_LINE.finditer(m.group(1))]


_ESSENTIAL = re.compile(r"essential|mandatory|must|required|requirement", re.I)
_SOFTENER = re.compile(r"desirable|preferred|advantageous|nice to have|bonus|ideally|plus\b|or equivalent experience", re.I)
_AMT = re.compile(r"[\$£]\s?(\d[\d,]*(?:\.\d+)?)\s?(k)?|(\d[\d,]*(?:\.\d+)?)\s?(k)?\s?(?:gbp|usd)", re.I)


def parse_pay(text: str):
    vals = []
    is_usd = "$" in text or "usd" in text.lower()
    fx_rate = 0.77 if is_usd else 1.0

    for m in _AMT.finditer(text or ""):
        num, k = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        v = float(num.replace(",", ""))
        vals.append((v * 1000 if k else v) * fx_rate)

    if not vals:
        return None

    t = text.lower()
    hi = max(vals)
    lo = min(vals)
    if re.search(r"\b(per day|a day|daily|day rate|p/?d)\b|/\s?day", t):
        unit = "day"
    elif re.search(r"\b(per hour|hourly|ph)\b|/\s?h(ou)?r", t):
        unit = "hour"
    elif re.search(r"per annum|\bp\.?a\.?\b|/\s?yr|/\s?year|annual|yearly|per year", t) or hi >= 10_000:
        unit = "year"
    elif 150 <= hi <= 2000:
        unit = "day"
    else:
        unit = None

    # Apply the shorthand fix ONLY if pay is per annum (unit == "year") and values are written without 'k' (e.g. 60 - 70)
    if unit == "year" and hi < 1000:
        vals = [v * 1000 for v in vals]
        hi = max(vals)
        lo = min(vals)
    elif len(vals) > 1 and unit == "year":
        max_v = max(vals)
        if max_v >= 10_000:
            vals = [v * 1000 if v < 1000 else v for v in vals]
            hi = max(vals)
            lo = min(vals)
    return lo, hi, unit


@dataclass
class PreFilterResult:
    passed: bool
    score: int = 0
    hard_reason: str = ""
    reasons: list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        return self.hard_reason or "; ".join(self.reasons[:4])

    def as_result(self) -> dict:
        return {
            "score": 0,
            "cvtmpl_no": -1,
            "job_status": "donotapply",
            "job_score_result": f"{self.reason}",
        }


def _hard_rules(job: dict, text: str) -> str:
    emp = (job.get("work_type") or "").lower()

    if any(e in emp for e in REJECT_EMPLOYMENT):
        return f"employment type '{emp}'"

    pay = parse_pay(job.get("salary") or "") or parse_pay(text)
    if pay:
        lo, hi, unit = pay
        if unit == "day" and hi < MIN_DAY_RATE_GBP:
            return f"day rate £{hi:.0f} < floor"
        if unit == "year" and hi < MIN_SALARY_GBP:
            return f"salary £{hi:.0f} < floor"
        if unit == "hour" and hi * 7.5 < (MIN_DAY_RATE_GBP / 8 * 7.5):
            return f"hourly £{hi:.0f} < floor"

    kind, detail = clearance_check(text)
    if kind == "reject":
        return detail

    m = LANG_RX.search(text)
    if m:
        return f"language requirement: '{m.group(0)[:40]}'"

    for cert in LACKING_CERTS:
        for cm in re.finditer(_term_rx(cert), text):
            window = text[max(0, cm.start() - 80): cm.end() + 80]
            near = text[max(0, cm.start() - 60): cm.end() + 60]
            if any(h in near for h in HELD_CERTS):
                continue
            if _ESSENTIAL.search(window) and not _SOFTENER.search(window):
                return f"essential cert not held: {cert}"

    for skill, yrs in poster_requirements(text):
        for key, held in YEARS_HELD.items():
            if key in skill and held < yrs:
                return f"poster requires {yrs}+ yrs {skill}; you list {held:g}"

    if len(NON_IT_WORDS.findall(text)) >= 6:
        return "non-IT industry (construction/health/HR/plant wording)"

    return ""


def prefilter(job: dict) -> PreFilterResult:
    """Stage B. Returns PreFilterResult; passed=True means 'worth paying Gemini for'."""
    ok, why = title_gate(job.get("title", ""))
    if not ok:
        return PreFilterResult(False, hard_reason=why)

    text = _norm(job.get("description") or "").lower()
    if len(text) < 150:
        return PreFilterResult(False, hard_reason="description missing/too short (<150 chars)")

    hard = _hard_rules(job, text)
    if hard:
        return PreFilterResult(False, hard_reason=hard)

    if len({m.lower() for m in IT_CONTEXT.findall(text)}) < IT_CONTEXT_MIN:
        return PreFilterResult(False, hard_reason="not enough IT/tech context in ad")

    scored = trim_for_ai(text, max_chars=20_000)
    total, reasons = 0, []
    for cat, (w, cap, _) in SIGNALS.items():
        hits = [t for t, rx in _SIGNAL_RX[cat] if rx.search(scored)]
        pts = w * len(hits)
        pts = max(pts, cap) if cap < 0 else min(pts, cap)
        total += pts
        if hits:
            reasons.append(f"{cat}{pts:+d}({','.join(hits[:3])})")

    if clearance_check(text)[0] == "soft":
        total -= 3
        reasons.append("clearance-soft-3")

    passed = total >= PASS_SCORE
    return PreFilterResult(passed, score=total, reasons=reasons,
                           hard_reason="" if passed else f"score {total} < {PASS_SCORE}")

_BOILERPLATE = re.compile(
    r"equal opportunit|reasonable adjustments|disability confident|privacy (notice|policy)|data protection|"
    r"\bgdpr\b|by applying|benefits (include|package)|what we offer|why join us|our benefits|\bperks\b|"
    r"about us\b|about the company|how to apply|recruitment process|diversity|company description|"
    r"years in business|award[\s\-]*winning|great place to work|gptw|premier .{0,20}partner", re.I)


def trim_for_ai(text: str, max_chars: int = MAX_DESC_CHARS_FOR_AI) -> str:
    lines = [l.strip() for l in re.split(r"[\r\n]+", text or "") if l.strip()]
    if len(lines) >= 8:
        lines = lines[:1] + [l for l in lines[1:] if not _BOILERPLATE.search(l)]
    out = "\n".join(lines)
    if len(out) > max_chars:
        head, tail = int(max_chars * 0.75), int(max_chars * 0.25)
        out = out[:head] + "\n...\n" + out[-tail:]
    return out


def body_fingerprint(job: dict) -> str:
    d = job.get("description") or ""
    body = d.split("|", 7)[-1] if d.count("|") >= 7 else d
    body = re.sub(r"\W+", " ", body.lower()).strip()[:4000]
    return hashlib.sha1(body.encode("utf-8")).hexdigest()


def repost_key(job: dict) -> str:
    def n(x: str) -> str:
        x = _norm(x).lower()
        x = re.sub(r"[\(\[][^)\]]*[\)\]]", " ", x)
        x = re.sub(r"\b(contract|contractor|permanent|perm|interim|ftc|fixed[\s\-]*term|\d+\s*months?)\b", " ", x)
        return re.sub(r"[^a-z0-9]+", " ", x).strip()
    return f"{n(job.get('company', ''))}|{n(job.get('title', ''))}"