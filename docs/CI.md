# CI Baseline

GitHub Actions workflow for CraftFlow.

## Triggers

- Push to `main`
- Pull request targeting `main`

## Jobs

### test (Python 3.11, ubuntu-latest)

1. Checkout
2. Install dependencies from `requirements.txt`
3. `python manage.py check` — Django system checks
4. `python manage.py makemigrations --check --dry-run` — verify no missing migrations
5. `python manage.py test --verbosity 1` — full test suite

## Security

- `SECRET_KEY` set via environment variable, never hardcoded
- Test database is temporary (created and destroyed per run)
- No production database access
- No credentials in repository

## Local Execution

```bash
# Simulate CI checks locally
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --verbosity 1
```

## Failure Output

The workflow fails with a non-zero exit code and a clear step name.
GitHub Actions shows which step failed and its log output.

## Files

- `.github/workflows/ci.yml` — workflow definition