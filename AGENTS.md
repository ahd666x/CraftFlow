# AGENTS.md

## Test Commands

```bash
# Run all tests
python -m django test --settings=selvi.settings

# Run specific test module
python -m django test --settings=selvi.settings v2_api

# Run with verbose output
python -m django test --settings=selvi.settings -v 2

# Run reconciliation command
python -m django craftflow_reconcile_v2 --settings=selvi.settings

# Run migration command
python -m django craftflow_migrate_v2 --settings=selvi.settings
```

## Lint / Type Check

No formal linter or type checker is currently configured. All validation is via the Django test suite (143 tests).

## Code Style

- Django conventions: snake_case for Python, PascalCase for models
- Persian (Farsi) verbose names in model field definitions
- Persian date support via `jdatetime` and `PersianDateField`
- All V2 mutations wrapped in `transaction.atomic`
- V2 API follows View → Service (mutations) / View → Selector (queries) pattern
