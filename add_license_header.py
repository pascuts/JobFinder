from pathlib import Path

# Change this path to your target repository or project directory
TARGET_DIR = Path(r"C:\Users\Fujitsu\source\repos\PythonModules\JobSeachPy")

LICENSE_HEADER = """# ------------------------------------------------------------------------------
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

"""

# Directories to skip when walking the project tree
EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "build",
    "dist",
    "backups",
}


def add_header_to_file(file_path: Path, dry_run: bool = False) -> str:
    content = file_path.read_text(encoding="utf-8", errors="replace")

    # Skip if this license notice is already in the file
    if "LICENCE NOTICE:" in content and "Adrian Pascut (ESLAMERA LIMITED)" in content:
        return "skipped (already licensed)"

    lines = content.splitlines(keepends=True)
    top_directives = []
    idx = 0

    # Preserve shebang (#!...) on line 1 if present
    if lines and lines[0].startswith("#!"):
        top_directives.append(lines[0])
        idx += 1

    # Preserve encoding comment (# -*- coding: utf-8 -*-) right after shebang or on line 1
    if idx < len(lines) and ("coding:" in lines[idx] or "coding=" in lines[idx]):
        top_directives.append(lines[idx])
        idx += 1

    remaining_code = "".join(lines[idx:])
    updated_content = "".join(top_directives) + LICENSE_HEADER + remaining_code

    if not dry_run:
        file_path.write_text(updated_content, encoding="utf-8")

    return "previewed" if dry_run else "updated"


def process_directory(target_dir: Path, dry_run: bool = False) -> None:
    if not target_dir.exists() or not target_dir.is_dir():
        print(f"Error: Directory does not exist: {target_dir}")
        return

    updated_count = 0
    skipped_count = 0
    total_count = 0

    for py_file in sorted(target_dir.rglob("*.py")):
        # Skip this script itself so it doesn't add the header to itself
        if py_file.resolve() == Path(__file__).resolve():
            continue

        # Skip virtual environments, git folders, build artifacts, etc.
        if any(part in EXCLUDED_DIRS for part in py_file.parts):
            continue

        if not py_file.is_file():
            continue

        total_count += 1
        status = add_header_to_file(py_file, dry_run=dry_run)
        print(f"[{status}] {py_file}")

        if status.startswith("skipped"):
            skipped_count += 1
        else:
            updated_count += 1

    print(
        f"\nDone. Found {total_count} .py files | "
        f"{'Would update' if dry_run else 'Updated'}: {updated_count} | "
        f"Skipped: {skipped_count}"
    )


if __name__ == "__main__":
    # Set dry_run=True first to preview changes safely, then set dry_run=False to write files
    process_directory(TARGET_DIR, dry_run=False)