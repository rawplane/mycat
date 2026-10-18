# Refactor MyCat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up mycat by fixing test/lint tooling, centralizing config operations in `app_config.py`, and extracting platform display/RandR logic and tray setup out of `main.py`.

**Architecture:** Split responsibilities: `display.py` handles X11 and screen geometry, `tray.py` handles icon creation and system tray menu, `app_config.py` centralizes config I/O. `main.py` retains public re-exports for backwards compatibility.

**Tech Stack:** Python 3.10+, PySide6, pytest, ruff.

**Spec:** Refactor agreement in conversation.

## Global Constraints
- Preserve all existing public module APIs in `mycat.main` (`CFG_FILE`, `make_app_icon`, `setup_tray`, etc.) to keep existing tests and integrations working.
- Keep tests passing at each task: `pytest`.
- Keep code clean: `ruff check .`.

## Review Focus
- `pytest` runs without `PYTHONPATH=.` set in environment.
- Config reading/writing preserves file permissions (`secret_store.secure_file`) and UTF-8 handling.
- Screen geometry calculations behave correctly across headless/X11 environments.
- Tray icon and menus work identically.
- Re-exports in `mycat.main` prevent any `ImportError`.

---

### Task 1: Fix Tooling and Linter

**Files:**
- Modify: `pyproject.toml`
- Modify: `tests/test_reminder.py:52-57`

- [ ] **Step 1: Update `pyproject.toml`**
Add `pythonpath = ["."]` under `[tool.pytest.ini_options]` so `pytest` works directly.

- [ ] **Step 2: Fix lint in `tests/test_reminder.py`**
Format and split imports in `test_single_config_source`.

- [ ] **Step 3: Verify**
Run: `pytest`
Run: `ruff check .`

- [ ] **Step 4: Commit**
`git commit -am "chore: fix pytest pythonpath and ruff import lint"`

---

### Task 2: Centralize Configuration Logic in `mycat/app_config.py`

**Files:**
- Modify: `mycat/app_config.py`
- Modify: `mycat/main.py`
- Create: `tests/test_app_config.py`

- [ ] **Step 1: Write unit tests in `tests/test_app_config.py`**
Test `read_config()`, `load_config()`, `save_config()`, `load_image_from_ini()`, `save_image_to_ini()`, `load_wait_time_from_ini()`.

- [ ] **Step 2: Implement config helpers in `mycat/app_config.py`**
Implement the config operations cleanly using `read_config()` and `secure_write_config()`.

- [ ] **Step 3: Update `mycat/main.py`**
Import the helpers from `app_config` and re-export them in `main.py`.

- [ ] **Step 4: Verify**
Run `pytest` and `ruff check .`.

- [ ] **Step 5: Commit**
`git commit -am "refactor: centralize config management into app_config.py"`

---

### Task 3: Extract Display & X11 Logic to `mycat/display.py`

**Files:**
- Create: `mycat/display.py`
- Modify: `mycat/main.py`
- Create: `tests/test_display.py`

- [ ] **Step 1: Create `mycat/display.py`**
Move `x11_compositor_active`, `x11_screen_size`, `usable_screen_rect`, `randr_monitor_count`, `ensure_virtual_monitor` from `mycat/main.py` to `mycat/display.py`.

- [ ] **Step 2: Update `mycat/main.py`**
Import and re-export the display functions.

- [ ] **Step 3: Add `tests/test_display.py`**
Test `usable_screen_rect()`, verify it returns a `QRect` even in headless/offscreen environments.

- [ ] **Step 4: Verify**
Run `pytest` and `ruff check .`.

- [ ] **Step 5: Commit**
`git commit -am "refactor: extract display and X11 platform logic to display.py"`

---

### Task 4: Extract Tray Management to `mycat/tray.py`

**Files:**
- Create: `mycat/tray.py`
- Modify: `mycat/main.py`

- [ ] **Step 1: Create `mycat/tray.py`**
Move `make_app_icon()` and `setup_tray()` into `mycat/tray.py`.

- [ ] **Step 2: Update `mycat/main.py`**
Import `make_app_icon` and `setup_tray` from `mycat/tray.py` and re-export them.

- [ ] **Step 3: Verify**
Run `pytest` and `ruff check .`.

- [ ] **Step 4: Commit**
`git commit -am "refactor: extract tray setup and icon creation to tray.py"`
