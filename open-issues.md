# Open Issues - UNetbootin Python Rewrite

> **Last Updated**: 2026-07-23
> **Status**: Code Audit Complete | Issues H-001, H-002, M-007 Fixed
> **Auditor**: Mistral Vibe CLI Agent

This document tracks all identified issues, warnings, security concerns, and code quality problems in the UNetbootin Python rewrite codebase. Issues are categorized by priority and type.

---

## 📊 Summary

| Category | Count | Status |
|----------|-------|--------|
| Critical Issues | 0 | ✅ None |
| High Priority | 0 | ✅ All Fixed |
| Medium Priority | 14+ | ⚠️ Needs Review |
| Low Priority | 20+ | 📋 Backlog |

**Fixed in this update**: H-001, H-002, M-007

---

## 🔴 CRITICAL ISSUES

*None identified - the codebase handles security, privileges, and file operations appropriately.*

---

## 🟡 HIGH PRIORITY ISSUES

### H-001: Multiple Setup Files Conflict
**Type**: Build/Dependency  
**Files**: `setup.py`, `setup_pysg.py`  
**Status**: ✅ Fixed  
**Fixed On**: 2026-07-23  
**Description**: Two setup files exist with different package names (`unetbootin` vs `unetbootin-pysg`), creating potential conflicts during installation.  
**Impact**: Confuses users, may cause installation conflicts  
**Recommendation**: Consolidate into a single `setup.py` with feature flags, or clearly document the purpose of each and ensure they don't conflict.
**Resolution**: Removed `setup_pysg.py` to eliminate conflict. Only `setup.py` remains.

---

### H-002: Duplicate Requirements Files
**Type**: Build/Dependency  
**Files**: `requirements.txt`, `requirements_pysg.txt`  
**Status**: ✅ Fixed  
**Fixed On**: 2026-07-23  
**Description**: Both files contain identical content.  
**Impact**: Maintenance burden, potential for divergence  
**Recommendation**: Remove `requirements_pysg.txt`. Use a single `requirements.txt` with `extras_require` in `setup.py` for optional dependencies.
**Resolution**: Removed `requirements_pysg.txt`. All requirements consolidated in `requirements.txt`.

---

## 🟠 MEDIUM PRIORITY ISSUES

### M-001: Wildcard Imports in Platform Module
**Type**: Code Style / PEP 8  
**File**: `src/unetbootin/platform/__init__.py`  
**Status**: Open  
**Lines**: 9, 11, 13, 16, 19  
**Description**: Uses `from .macos import *`, `from .windows import *`, etc.  
**Impact**: Pollutes namespace, violates PEP 8, unclear what's imported  
**Recommendation**: Explicitly import only needed functions/classes.

---

### M-002: Excessive Broad Exception Handling
**Type**: Code Quality  
**Files**: Throughout `src/unetbootin/` (141 instances)  
**Status**: Open  
**Description**: Overuse of `except Exception as e` catches too broadly, hiding bugs and making debugging difficult.  
**Impact**: Masked exceptions, harder debugging  
**Recommendation**: Catch specific exceptions where possible (e.g., `requests.exceptions.RequestException`, `OSError`, `IOError`, `ValueError`).

---

### M-003: Line Length Violations
**Type**: Code Style / PEP 8  
**Files**: `src/unetbootin/app.py` (most violations), `downloader.py`, `extractor.py`, `installer.py`  
**Status**: Open  
**Description**: 100+ lines exceed the 88-character limit specified in README.  
**Impact**: Reduced readability, violates project style guidelines  
**Recommendation**: Refactor long lines using line continuation or breaking into multiple statements.

---

### M-004: Inconsistent Logging
**Type**: Code Quality  
**Files**: `src/unetbootin/main.py:64-66`, `app.py`, and others  
**Status**: Open  
**Description**: Mix of `logger.error()`, `logger.warning()`, `logger.info()` with direct `print()` statements.  
**Impact**: Inconsistent output, harder to control logging behavior  
**Recommendation**: Use the logging module consistently; remove all `print()` calls from production code.

---

### M-005: Duplicate Drive Listing Logic
**Type**: Code Duplication  
**Files**: `src/unetbootin/core/utils.py:356-497`, `src/unetbootin/platform/*.py`  
**Status**: Open  
**Description**: Drive listing logic exists in both `utils.py` and platform-specific modules.  
**Impact**: Maintenance burden, potential for inconsistencies  
**Recommendation**: Consolidate drive listing into platform-specific modules only; remove from `utils.py`.

---

### M-006: Temporary File Cleanup
**Type**: Potential Resource Leak  
**Files**: `src/unetbootin/app.py:232-240`  
**Status**: Open  
**Description**: Cleanup only runs if `self.tmp_dir` is set; errors might occur before it's initialized.  
**Impact**: Temporary files may not be cleaned up on error  
**Recommendation**: Use `tempfile.TemporaryDirectory` context manager or ensure cleanup in `finally` blocks.

---

### M-007: Missing Build Dependency
**Type**: Build/Dependency  
**File**: `requirements.txt`  
**Status**: ✅ Fixed  
**Fixed On**: 2026-07-23  
**Description**: `setuptools` is not listed in dependencies but is required for building.  
**Impact**: Build may fail if setuptools is not pre-installed  
**Recommendation**: Add `setuptools>=61.0.0` to development dependencies.
**Resolution**: Added `setuptools>=61.0.0` to both `requirements.txt` and `setup.py` development extras.

---

### M-008: Incomplete Platform Implementations
**Type**: Code Quality  
**Files**: `src/unetbootin/platform/base.py`, `src/unetbootin/platform/windows.py`  
**Status**: Open  
**Description**: Many functions are stubs that just return `False` or `None`.  
**Impact**: Incomplete functionality on some platforms  
**Recommendation**: Either implement these functions properly or raise `NotImplementedError` with a clear message explaining the limitation.

---

### M-009: Subprocess Parameter Validation
**Type**: Security  
**File**: `src/unetbootin/core/utils.py:287-327`  
**Status**: Open  
**Description**: `call_external_app()` uses `shlex.split()` which is good, but if `exec_param` comes from user input, it could still be risky.  
**Impact**: Potential command injection if user input is not validated  
**Recommendation**: Validate and sanitize `exec_param` before splitting; use a whitelist of allowed commands where possible.

---

### M-010: Plain FTP Usage
**Type**: Security  
**File**: `src/unetbootin/core/downloader.py:613-646`  
**Status**: Open  
**Description**: `list_ftp_directory()` uses plain FTP without encryption.  
**Impact**: Credentials and data transmitted in cleartext  
**Recommendation**: Prefer SFTP or FTPS; add a warning to users about insecure connection when FTP is used.

---

### M-011: macOS Privilege Escalation Limitation
**Type**: Platform Support  
**File**: `src/unetbootin/app.py:189-200`  
**Status**: Open  
**Description**: Uses `osascript` to relaunch with sudo, which only works if Terminal is available.  
**Impact**: Fails on headless systems or systems without Terminal  
**Recommendation**: Add fallback to command-line sudo, or provide better error handling with clear instructions.

---

### M-012: Unused Imports
**Type**: Code Quality  
**Files**: Various throughout `src/unetbootin/`  
**Status**: Open  
**Description**: Several files import modules that aren't used.  
**Impact**: Minor - increased import time, code clutter  
**Recommendation**: Remove unused imports to keep code clean.

---

## 🟢 LOW PRIORITY ISSUES

### L-001: README Inconsistencies
**Type**: Documentation  
**File**: `README.md:292-296`  
**Status**: Open  
**Description**: README mentions PySide6 but the actual implementation uses PySimpleGUI.  
**Impact**: Confusing for users  
**Recommendation**: Update README to reflect actual implementation (PySimpleGUI + Tkinter).

---

### L-002: Python Version Inconsistency
**Type**: Documentation  
**Files**: `README.md:89` (says Python 3.10+), `setup.py:55` (says >=3.9)  
**Status**: Open  
**Description**: Inconsistent Python version requirements.  
**Impact**: Confusing for users  
**Recommendation**: Standardize on Python 3.10+ (as stated in README) or update both to match.

---

### L-003: Magic Numbers
**Type**: Code Quality  
**Files**: Throughout `src/unetbootin/core/downloader.py`, `extractor.py`  
**Status**: Open  
**Description**: Hardcoded values like `timeout=300`, `chunk_size=8192`.  
**Impact**: Hard to maintain and update  
**Recommendation**: Define these as module-level constants with descriptive names.

---

### L-004: Inconsistent String Formatting
**Type**: Code Style  
**Files**: Throughout codebase  
**Status**: Open  
**Description**: Mix of f-strings, `.format()`, and `%` formatting.  
**Impact**: Minor inconsistency  
**Recommendation**: Use f-strings consistently (Python 3.10+).

---

### L-005: Missing Docstrings
**Type**: Documentation  
**Files**: Various throughout `src/unetbootin/`  
**Status**: Open  
**Description**: Some functions lack docstrings despite README stating "Include docstrings for all public methods".  
**Impact**: Reduced code documentation  
**Recommendation**: Add docstrings to all public methods.

---

### L-006: Missing `if __name__ == "__main__"` Guards
**Type**: Code Quality  
**Files**: Various modules  
**Status**: Open  
**Description**: Some modules could benefit from main guards for testing.  
**Impact**: Minor - modules can't be easily tested standalone  
**Recommendation**: Add `if __name__ == "__main__":` to all executable modules.

---

### L-007: HTTP vs HTTPS in Test Files
**Type**: Code Quality  
**File**: `tests/test_new_features.py`  
**Status**: Open  
**Description**: Test uses `http://` for mirror URL instead of `https://`.  
**Impact**: Minor - test data only  
**Recommendation**: Use `https://` consistently for security best practices.

---

## 📋 ISSUE TRACKING

### Status Legend
- ✅ **Fixed** - Issue has been resolved
- 🔄 **In Progress** - Issue is being worked on
- ⏳ **Pending** - Issue acknowledged, not yet started
- ❌ **Won't Fix** - Issue intentionally not addressed
- ⏸️ **On Hold** - Issue deferred

### Current Status
| Issue ID | Status | Assignee | Notes |
|----------|--------|----------|-------|
| H-001 | ✅ Fixed | - | Consolidate setup files - Removed setup_pysg.py |
| H-002 | ✅ Fixed | - | Remove duplicate requirements - Removed requirements_pysg.txt |
| M-001 | ⏳ Pending | - | Fix wildcard imports |
| M-002 | ⏳ Pending | - | Narrow exception handling |
| M-003 | ⏳ Pending | - | Fix line length violations |
| M-004 | ⏳ Pending | - | Consistent logging |
| M-005 | ⏳ Pending | - | Consolidate drive listing |
| M-006 | ⏳ Pending | - | Improve temp file cleanup |
| M-007 | ✅ Fixed | - | Add setuptools dependency - Added to requirements.txt and setup.py |
| M-008 | ⏳ Pending | - | Complete platform implementations |
| M-009 | ⏳ Pending | - | Validate subprocess parameters |
| M-010 | ⏳ Pending | - | Use secure FTP alternatives |
| M-011 | ⏳ Pending | - | Improve macOS privilege escalation |
| M-012 | ⏳ Pending | - | Remove unused imports |

---

## 🎯 RECOMMENDED FIX ORDER

### Phase 1: High Priority (1-2 days)
- [x] H-001: Consolidate setup files - **COMPLETED** (Removed setup_pysg.py)
- [x] H-002: Remove duplicate requirements files - **COMPLETED** (Removed requirements_pysg.txt)
- [x] M-007: Add setuptools to development dependencies - **COMPLETED** (Added to requirements.txt and setup.py)
- [ ] M-001: Fix wildcard imports in platform/__init__.py

### Phase 2: Medium Priority - Code Quality (3-5 days)
1. M-002: Narrow exception handling in core modules
2. M-003: Fix line length violations
3. M-004: Use consistent logging (remove print statements)
4. M-005: Consolidate drive listing logic
5. M-012: Remove unused imports

### Phase 3: Medium Priority - Security & Reliability (2-3 days)
1. M-006: Improve temporary file cleanup
2. M-008: Complete or document stub platform functions
3. M-009: Validate subprocess parameters
4. M-010: Warn about plain FTP usage
5. M-011: Improve macOS privilege escalation

### Phase 4: Low Priority (Ongoing)
1. L-001: Update README inconsistencies
2. L-002: Standardize Python version requirement
3. L-003: Define magic numbers as constants
4. L-004: Use consistent string formatting
5. L-005: Add missing docstrings
6. L-006: Add main guards to modules

---

## 📊 METRICS

- **Files Analyzed**: 20+ Python files
- **Total Lines of Code**: ~8,000
- **Test Files**: 6
- **Critical Issues**: 0
- **High Priority**: 0 (2 fixed)
- **Medium Priority**: 12 (1 fixed)
- **Low Priority**: 7+
- **Total Fixed**: 3

---

## 🔍 VERIFICATION CHECKLIST

- [x] All Python files are syntactically valid
- [x] No syntax errors found
- [x] No hardcoded credentials or secrets
- [x] No `eval()` or `exec()` with user input
- [x] No `shell=True` in subprocess calls
- [x] No `pickle` usage with untrusted data
- [x] Proper use of `tempfile.mkdtemp()` (not insecure `mktemp`)
- [x] HTTPS used for all distribution URLs
- [x] No `import *` except in platform/__init__.py (flagged for fix)


