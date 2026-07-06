# Contributing to Mudir / ORCHESTRA

Thanks for your interest in improving Mudir! This document explains how to
contribute effectively.

---

## Code of conduct

Be respectful, constructive and inclusive. Assume good intent, keep discussions
technical, and help newcomers. Harassment or abusive behaviour is not tolerated.
By participating you agree to uphold these standards.

---

## Ways to contribute

- **Report bugs** and **request features** using the
  [issue templates](ISSUE_TEMPLATE) — including the **security** template for
  vulnerabilities (do not open a public issue for a security report; use the
  security template's private guidance).
- **Improve documentation** (including the Arabic translations under `docs/ar/`).
- **Fix bugs / add features** via pull requests.

---

## Development setup

- **Python engine:** `pip install -r requirements-test.txt` then `pytest`.
  Service/DB extras are in `orchestra/*/requirements.txt`.
- **Backend:** `cd backend && npm install && npm test`.
- **Frontend:** `cd frontend && npm install && npm test`.

See [DEVELOPER_GUIDE.md](../DEVELOPER_GUIDE.md) for architecture and the testing
guide.

---

## Pull-request process

1. **Fork** the repo and create a topic branch from `main`
   (e.g. `feature/parallel-stages` or `fix/stage-advance`).
2. Make **focused** changes — one logical change per PR. Avoid unrelated
   refactors.
3. **Add or update tests** for your change. Keep the suite green:
   - `pytest` (and `--cov=orchestra` if you touched the engine)
   - `npm test` in `backend/` and/or `frontend/` if you touched them
4. **Update documentation** affected by your change (README, guides, `docs/`, and
   Arabic translations where user-facing).
5. **Do not commit secrets.** Keep webhook signature verification and other
   security controls intact.
6. Open a PR against `main`, fill in the template, and link any related issues.
7. Ensure **CI is green** (tests run on Python 3.10/3.11/3.12) and address review
   feedback.

Maintainers squash-merge once approved and CI passes.

---

## Coding standards

- **Python:** PEP 8, full type hints, docstrings, lazy imports for heavy deps,
  dependency injection over globals. Async tests use
  `unittest.IsolatedAsyncioTestCase`.
- **JavaScript/React:** follow the existing ESLint/Prettier config; colocate
  tests as `*.test.js(x)`; keep the dashboard Arabic-first (RTL) and dark-mode
  aware.
- **Commits:** imperative and scoped, e.g. `engine: fix stage advance on skip`.
- **Localization:** user-facing strings are bilingual (Arabic first, English
  fallback).

---

## Reporting security issues

Please **do not** file public issues for vulnerabilities. Use the private
reporting path described in the
[security issue template](ISSUE_TEMPLATE/security_report.yml) and see
[docs/security.md](../docs/security.md). We aim to acknowledge reports promptly
and coordinate a fix and disclosure.
