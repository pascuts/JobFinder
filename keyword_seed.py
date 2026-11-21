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

# keyword_seed.py
# Seed list: (keyword, domain, base_score, optional boolean query override)
# base_score = how much you WANT roles found by this keyword (1-10).
# Spelling variants share ONE search via a boolean query (saves a search slot).

def _v(*variants: str) -> str:
    return " OR ".join(f'"{v}"' for v in variants)

KEYWORD_SEED = [
    ("Programme Manager", "management", 10, _v("Programme Manager", "Program Manager")),
    ("Senior Project Manager", "management", 10, None),
    ("Technical Project Manager", "management", 10, None),
    ("Delivery Manager", "management", 10, None),
    ("Transformation Programme Manager", "management", 10,
        _v("Transformation Programme Manager", "Transformation Program Manager")),

    ("Solution Architect", "architecture", 9, None),
    ("Information Security Manager", "security", 9, None),
    ("Security Governance Manager", "security", 9, None),
    ("IT Project Manager", "management", 9, None),
    ("Cloud Migration Project Manager", "management", 9, None),
    ("Infrastructure Project Manager", "management", 9, None),
    ("Agile Project Manager", "agile", 9, None),
    ("Technology Transformation Manager", "management", 9, None),

    ("Enterprise Architect", "architecture", 8, None),
    ("TOGAF Architect", "architecture", 8, None),
    ("Principal Architect", "architecture", 8, None),
    ("Security Architect", "architecture", 8, None),
    ("Technical Architect", "architecture", 8, None),
    ("Java Technical Architect", "architecture", 8, None),
    ("Digitalisation Strategy Lead", "leadership", 8,
        _v("Digitalisation Strategy Lead", "Digitalization Strategy Lead")),
    ("Digital Transformation Lead", "leadership", 8, None),
    ("Digital Transformation Manager", "management", 8, None),
    ("Security Risk and Compliance Manager", "security", 8, None),
    ("Head of Delivery", "leadership", 8, None),
    ("Head of PMO", "leadership", 8, None),
    ("Team Lead", "leadership", 8, None),
    ("Technical Program Manager", "technical", 8, _v("Technical Program Manager", "Technical Programme Manager")),
    ("Technical Transformation Lead", "technical", 8, None),
    ("Engineering Delivery Lead", "technical", 8, None),
    ("PMO Lead", "management", 8, None),
    ("Transformation Manager", "management", 8, None),
    ("Project Manager", "management", 8, None),

    ("Lead Enterprise Architect", "architecture", 7, None),
    ("Domain Architect", "architecture", 7, None),
    ("Digital Strategy Lead", "leadership", 7, None),
    ("Digital Strategy Manager", "leadership", 7, None),
    ("Technology Strategy Lead", "leadership", 7, None),
    ("Information Security Officer", "security", 7, None),
    ("IT Security Manager", "security", 7, None),
    ("Vulnerability Management", "security", 7, None),
    ("ISO 27001", "security", 7, None),
    ("Scrum Master", "agile", 7, None),
    ("Agile Delivery Manager", "agile", 7, None),
    ("Software Delivery Manager", "technical", 7, None),
    ("Delivery Director", "leadership", 7, None),
    ("Programme Director", "leadership", 7, _v("Programme Director", "Program Director")),

    ("Digital Architect", "architecture", 6, None),
    ("Cloud Architect", "architecture", 6, None),
    ("Platform Modernisation Lead", "architecture", 6, _v("Platform Modernisation Lead", "Platform Modernization Lead")),
    ("Cyber Security Manager", "security", 6, None),
    ("PCI-DSS", "security", 6, None),
    ("Security GRC", "security", 6, None),
    ("Continuous Improvement Manager", "management", 6, None),
    ("DevOps Delivery Lead", "technical", 6, None),
    ("Transformation Director", "leadership", 6, None),

    ("Director of IT", "leadership", 5, None),
    ("Engineering Manager", "technical", 5, None),
    ("Release Manager", "agile", 5, None),
    ("Java SME", "technical", 5, None),
    ("Project Delivery Lead", "leadership", 5, None),

    ("Agile Coach", "agile", 4, None),
    ("Kanban Practitioner", "agile", 4, None),
    ("Agile Program Manager", "agile", 4, None),
    ("Agile transformation", "agile", 4, None),
    ("IT Operations Manager", "leadership", 4, None),
    ("Interim IT Director", "leadership", 4, None),
    ("Head of Engineering", "leadership", 4, None),
    ("VP of Engineering", "leadership", 4, None),
    ("Director of Software Engineering", "leadership", 4, None),
    

    ("Vulnerability Management Lead", "security", 3, None),
    ("Security Risk Compliance Manager", "security", 3, None),
    ("Cybersecurity Governance Manager", "security", 3, None),
    
    ("CISO", "security", 3, None),
    ("CTO", "leadership", 3, None),
]

# Keywords that earned interviews: multiplier on top of the score (1.0 = neutral).
# Applied once with KeywordScheduler.set_boost(); persists in the DB afterwards.
INITIAL_BOOSTS = {
    "Enterprise Architect": 1.5,
    "Digitalisation Strategy Lead": 1.5,
    "Solution Architect": 1.3,
}


def seed_database(store) -> list:
    """Insert the keywords that are missing (idempotent). One-off boosts are applied only to the
    keywords inserted now. Returns the keywords inserted."""
    return store.seed_with_boosts(KEYWORD_SEED, INITIAL_BOOSTS)
