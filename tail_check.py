import json
from django.db import connection
from django.apps import apps
from django.db.migrations.loader import MigrationLoader

results = {
    "v1_tables": {},
    "v2_tables_in_db": {},
    "core_tables": {},
    "migrations_applied": [],
    "migrations_pending": [],
    "v1_models": {},
    "v2_models": {},
    "migration_map_status": "N/A - table does not exist",
}

with connection.cursor() as cursor:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    all_tables = [row[0] for row in cursor.fetchall()]

# V1 tables (product app)
v1_tables = [t for t in all_tables if t.startswith("product_")]
for t in v1_tables:
    cursor.execute(f'SELECT COUNT(*) FROM "{t}"')
    count = cursor.fetchone()[0]
    results["v1_tables"][t] = count

# V2 tables (any non-V1, non-core table)
v2_app_tables = [t for t in all_tables if not t.startswith("product_") and not t.startswith("django_") and not t.startswith("auth_") and not t.startswith("admin_") and not t.startswith("sessions_") and not t.startswith("accounts_")]
for t in v2_app_tables:
    cursor.execute(f'SELECT COUNT(*) FROM "{t}"')
    count = cursor.fetchone()[0]
    results["v2_tables_in_db"][t] = count

# Core tables
core_tables = [t for t in all_tables if t.startswith("django_") or t.startswith("auth_") or t.startswith("admin_") or t.startswith("sessions_") or t.startswith("accounts_")]
for t in core_tables:
    cursor.execute(f'SELECT COUNT(*) FROM "{t}"')
    count = cursor.fetchone()[0]
    results["core_tables"][t] = count

# Migration status
loader = MigrationLoader(None, ignore_no_migrations=True)
for app_label, migration_name in sorted(loader.applied_migrations):
    results["migrations_applied"].append(f"{app_label}.{migration_name}")
for app_label in sorted(loader.disk_migrations.keys()):
    disk_migs = loader.disk_migrations[app_label]
    applied = loader.applied_migrations.get(app_label, set())
    for mig_name in sorted(disk_migs.keys()):
        if mig_name not in applied:
            results["migrations_pending"].append(f"{app_label}.{mig_name}")

# V1 models
v1_apps = ["product"]
for app_label in v1_apps:
    app_config = apps.get_app_config(app_label)
    for model in app_config.get_models():
        model_name = model.__name__
        try:
            count = model._default_manager.count()
        except Exception as e:
            count = f"Error: {e}"
        results["v1_models"][f"{app_label}.{model_name}"] = count

# V2 models - attempt to query, report errors
v2_apps = ["customers", "products", "inventory", "bom", "production", "sales", 
           "quality", "shipping", "packaging", "painting", "warehouse", "reporting",
           "planning", "core"]
for app_label in v2_apps:
    try:
        app_config = apps.get_app_config(app_label)
        for model in app_config.get_models():
            model_name = model.__name__
            try:
                count = model._default_manager.count()
            except Exception as e:
                count = f"Error: {str(e)}"
            results["v2_models"][f"{app_label}.{model_name}"] = count
    except Exception as e:
        results["v2_models"][f"{app_label} (error)"] = str(e)

# MigrationMap check
try:
    from reporting.models import MigrationMap
    mm_count = MigrationMap.objects.count()
    results["migration_map_status"] = {"count": mm_count}
    from collections import Counter
    types = Counter(MigrationMap.objects.values_list("migration_type", flat=True))
    results["migration_map_status"]["types"] = dict(types)
except Exception as e:
    results["migration_map_status"] = f"Table does not exist or not migrated: {str(e)}"

print(json.dumps(results, indent=2, default=str))
