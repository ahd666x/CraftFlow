# Phase 33: CI Quality Gate

Status: **Not Implemented**

## Proposed Pipeline

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - run: pip install -r requirements.txt
      - run: python manage.py check
      - run: python manage.py makemigrations --check --dry-run
      - run: python manage.py migrate --plan
      - run: python manage.py test --verbosity 2
```

## Gates

1. `python manage.py check` — system checks pass
2. `makemigrations --check --dry-run` — no missing migrations
3. `migrate --plan` — all migrations applicable
4. `python manage.py test` — all tests pass
5. QR compatibility tests
6. Inventory reconciliation tests
7. ProductionTask legacy tests
8. V2 service tests

## Rules

- Temporary test database only
- No production database access
- No secrets in repository
- Failure shows test name and reason clearly

## No Changes Made