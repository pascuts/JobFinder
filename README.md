# 🔍 Personal Job Finder Tool

[![Licence: Custom Source-Available]([suspicious link removed])](#-licence--usage-restrictions)
[![Scope: Personal Use Only]([suspicious link removed])](#-permitted-use)
[![Python: 3.10+]([suspicious link removed])](https://www.python.org/)

An automated job search and application management assistant designed exclusively to help **private individuals** streamline, track, and optimize their personal career search across major job portals and AI APIs.
---
## ⚠️ Important Licence & Legal Notice

> **RESTRICTED LICENCE & MANDATORY PENALTY NOTICE**
> 
> This repository is governed by the **Custom Source-Available & Personal Job-Search Licence (v1.2)**. 
> 
> * **Permitted Use**: Granted **strictly and exclusively to Private Individuals** for non-commercial personal job-search activities.
> * **Commercial Entities & Other Uses Strictly Prohibited**: Any copying, modification, hosting, deployment, SaaS integration, recruitment agency usage, or commercial deployment requires direct prior written authorization and an executed **Commercial Licence Agreement** from **Adrian Pascut (ESLAMERA LIMITED)**.
> * **Strict Anti-Tampering & Removal Prohibition**: Removing, altering, obscuring, or stripping copyright headers, notices, or the `LICENSE` file is strictly prohibited.
> 
> ### Contractual Penalties (Liquidated Damages)
> Any breach of this licence triggers mandatory financial penalties plus legal and enforcement costs:
> 
> | Breach Type | Standard Breach Penalty | Tampering / Header Removal Penalty |
> | :--- | :--- | :--- |
> | **Commercial Entity** | **£100,000** per breach/deployment | **£200,000** per breach/deployment |
> | **Private Individual** | **£10,000** per breach | **£20,000** per breach |

---

## 🌟 Key Features

* **Multi-Portal Job Search**: Automated aggregation and search filtering across major job platforms.
* **AI Match & Resume Tailoring**: Seamless integration with LLM APIs to evaluate candidate fit and tailor application materials.
* **Application Tracker**: Centralised tracking of application statuses, outreach, and follow-ups.
* **Automated Rate Limiting**: Built-in safeguards to maintain strict compliance with third-party platform API guidelines and rate limits.

---

## 🚀 Quick Start & Installation

### Prerequisites
* Python 3.10 or higher
* Valid API keys for supported third-party AI services and job portals

### Setup Instructions

1. **Clone the Repository**:
   ```bash
   git clone [suspicious link removed]
   cd job-finder-tool
(Note: Cloning or forking this repository constitutes full acceptance of the Custom Source-Available Licence v1.2 terms.)
Create a Virtual Environment:
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
Install Dependencies:
See requirements.txt
Configure Environment Variables: Copy .env.example to .env and insert your API credentials:
cp .env.example .env

Run the Application:
python JobSeachPy.py

🛠 Repository Structure & Governance
To maintain repository integrity and compliance, please refer to the following governance files:
File   				Purpose  
LICENSE.md			Full text of the Custom Source-Available & Personal Job-Search Licence (v1.2).
CONTRIBUTING.md		Guidelines for opening PRs, maintaining copyright headers, and contribution rules.
SECURITY.md			Policy for reporting security vulnerabilities and commercial misuse / licence violations.
.github/			Mandatory PR and Issue templates enforcing licence compliance checkboxes.

🛡️ Third-Party Compliance Disclaimer
This software interacts with external third-party platforms, APIs, and job portals. Users are solely responsible for ensuring their usage complies with all third-party Terms of Service, data protection laws (including GDPR), and rate-limiting regulations.
Software is provided "AS IS", without warranty of any kind.

✉️ Commercial Licensing & Contact
For commercial licensing agreements, enterprise queries, or written permissions, please contact:
Copyright Holder: Adrian Pascut
Operating Entity: ESLAMERA LIMITED
Email: [pascutn_pnairda@yahoo.fr]