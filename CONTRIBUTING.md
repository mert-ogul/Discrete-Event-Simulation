# Contributing

Thank you for helping improve this project. This document matches how the team and graders expect changes to land.

## Branching and pull requests

- Use **feature branches** off `main` with short, descriptive names (examples: `fix/mypy-sim-package`, `feature/analysis-tables`).
- Open a **pull request (PR)** early for sizable work, keep commits focused.
- Prefer **rebase** or **merge without fast-forward**, avoid force-pushing shared branches.

## Commit messages

- Use the **imperative mood** in the subject line (`Add tests for Sim.run`, `Fix gate busy reset`).
- Keep the first line around **72 characters** or less and put details in the body when needed.
- Reference issue or assignment IDs when your course requires traceability.

## Maintainer contact (active course window)

During the **2mbs40 assignment period**, use the **course communication channels** (canvas or email) and **request reviewers on GitHub pull requests** where possible. Teammates should expect a **best-effort reply within a few working days** while the project is active. There is no commitment outside the course timeline.

## Pre-commit hooks (optional)

After installing dependencies, run once per clone:

```bash
pre-commit install
```

Hooks mirror the main lint stack (`ruff`, `black`, full-project `mypy`). Run on all files anytime with `pre-commit run --all-files`.

## Local checks (same spirit as CI)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest -q
pytest --cov=sim --cov-report=term-missing -q

ruff check src tests
black --check src tests
mypy --config-file=pyproject.toml
```

## Docker

From the repository root:

```bash
docker compose build
docker compose run --rm app pytest -q
docker compose run --rm app ruff check src tests
docker compose run --rm app black --check src tests
docker compose run --rm app mypy --config-file=pyproject.toml
docker compose run --rm app pre-commit run --all-files
```

## Python path and running scripts

Simulation entry points import `sim` and `customtypes` from **`src/`**. From the repo root:

```bash
PYTHONPATH=src python src/run_simulation_predictive.py
```

Or:

```bash
cd src
export PYTHONPATH=.
python run_simulation_predictive.py
```

See [README.md](README.md) for data layout and architecture.

## Lockfiles

All dependencies (runtime and dev/CI) are pinned in **`requirements.txt`**. For optional hash-locked workflows (`pip-tools`, `uv`), see the README section on dependency lockfiles.

## Dependency scanning in CI

The **dependency-audit** job runs [`pip-audit`](https://pypi.org/project/pip-audit/) against the installed environment. If a finding is a false positive or cannot be fixed immediately, maintainers may document the exception and adjust the workflow after coordinating with course staff if this affects grading.

## Code of Conduct

All contributors agree to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
