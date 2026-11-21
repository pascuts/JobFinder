# Contributing Guidelines

Thank you for your interest in contributing to this project! Before submitting code, bug reports, or pull requests, please review these guidelines carefully.

This repository is governed by the **Custom Source-Available & Personal Job-Search Licence (v1.2)**. By cloning, forking, modifying, or opening a Pull Request (PR) against this repository, you explicitly agree to all terms and conditions set forth herein and in the root `LICENSE` file.

---

## 1. Legal Obligations & Licence Compliance

### A. Permitted Scope
* **Private Individuals Only**: Use and contributions are strictly restricted to **private individuals** using or enhancing the software for **personal, non-commercial job-search activities**.
* **Commercial Restrictions**: Commercial entities, recruitment agencies, SaaS platforms, and enterprise users are **strictly prohibited** from copying, using, modifying, hosting, or deploying this software without a separate, executed **Commercial Licence Agreement** from **Adrian Pascut (ESLAMERA LIMITED)**.

### B. Reciprocal Licence (Share-Alike)
* All accepted contributions, modifications, and forks automatically fall under the **Custom Source-Available & Personal Job-Search Licence (v1.2)**.
* You may not re-licence, dual-licence, or distribute any part of this repository under MIT, Apache, GPL, or any other open-source or commercial licence.

### C. Mandatory Header Preservation & Anti-Tampering
* **Header Requirement**: Every new or modified source file **must** retain or include the full copyright and licence header block at the top of the file.
* **Strict Prohibition on Removal**: Removing, stripping, obscuring, or altering copyright notices, headers, or the root `LICENSE` file is strictly prohibited.
* **Doubled Contractual Penalties**: Under Section 5 of the Licence, intentional removal or tampering with copyright notices or licence files **doubles all liquidated damage penalties**:
  * **Commercial Entity Tampering Breach**: **£200,000** per breach/deployment + legal fees.
  * **Private Individual Tampering Breach**: **£20,000** per breach + legal fees.

---

## 2. How to Submit Contributions

### A. Reporting Issues
1. Search existing issues before opening a new one to avoid duplicates.
2. Ensure your report relates strictly to software functionality or individual personal job-search workflows.
3. Provide details on your environment, steps to reproduce, and relevant logs (ensure no private API keys or candidate data are exposed).

### B. Pull Request (PR) Process
1. **Fork the Repository**: Ensure your fork retains the root `LICENSE` file and all existing header blocks intact.
2. **Create a Feature Branch**: `git checkout -b feature/your-feature-name`
3. **Add Licence Headers**: Ensure any newly created source files include the official licence header block.
4. **Code Quality Standards**:
   * Keep code modular, well-documented, and readable.
   * Ensure third-party API rate limits and terms of service (e.g., job portals, AI APIs) are respected.
   * Do not commit hardcoded credentials, secret keys, or personal data.
5. **Submit Your PR**:
   * Include a clear description of the feature or fix.
   * Include the following confirmation statement in your PR description:
     > *"I confirm that my contribution complies with and is submitted under the Custom Source-Available & Personal Job-Search Licence (v1.2)."*

---

## 3. Third-Party Platform & Data Ethics

Contributors must ensure that any code interacting with external job boards, platforms, or APIs:
* Complies with the target platform's Terms of Service and rate limits.
* Implements robust error handling and backoff mechanics to avoid overloading third-party infrastructure.
* Respects user privacy and data protection laws.

---

## 4. Commercial Licensing & Inquiries

For enterprise licensing requests, commercial permissions, or scope clarifications, please contact:

**Adrian Pascut (ESLAMERA LIMITED)**