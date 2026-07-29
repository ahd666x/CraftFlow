# product/tests/debug_scheduler.py
import sys
import traceback
import jdatetime
from django.db import connection

print("=" * 60)
print("DEBUG SCHEDULER - START")
print("=" * 60)

# Test 1: Worker cache
print("\n[1] Worker cache")
try:
    from product.utils import _get_worker_cache, invalidate_caches
    invalidate_caches()
    workers = _get_worker_cache()
    print(f"  workers type: {type(workers)}")
    print(f"  workers len: {len(workers) if workers else 0}")
    if workers and len(workers) > 0:
        print(f"  first worker type: {type(workers[0])}")
        print(f"  first worker: {workers[0]}")
except Exception as e:
    print(f"  ERROR: {e}")
    traceback.print_exc()

# Test 2: Process cache
print("\n[2] Process cache")
try:
    from product.utils import _get_process_cache
    processes = _get_process_cache()
    print(f"  processes type: {type(processes)}")
    print(f"  processes len: {len(processes) if processes else 0}")
except Exception as e:
    print(f"  ERROR: {e}")
    traceback.print_exc()

# Test 3: Find sample task
print("\n[3] Find sample task")
try:
    from product.models import ProductionTask
    sample_task = ProductionTask.objects.filter(
        station_name='paint',
        status__in=['pending', 'waiting'],
        scheduled_start__isnull=True,
        order_item__isnull=False,
        painting_stage__isnull=False,
    ).first()
    if sample_task:
        print(f"  found task id: {sample_task.id}")
        print(f"  order_item_id: {sample_task.order_item_id}")
        print(f"  painting_stage_id: {sample_task.painting_stage_id}")
    else:
        print("  No valid task found")
        sys.exit(0)
except Exception as e:
    print(f"  ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)

# Test 4: Create scheduler and test manually
print("\n[4] Test scheduler")
try:
    from product.utils import PaintingScheduler
    task_ids = [sample_task.id]
    target_date = jdatetime.date.today()
    print(f"  task_ids: {task_ids}")
    print(f"  target_date: {target_date}")

    scheduler = PaintingScheduler(task_ids, target_date)
    print(f"  scheduler created")
    print(f"  scheduler.task_ids type: {type(scheduler.task_ids)}")
    print(f"  scheduler.task_ids: {scheduler.task_ids}")

    # Load
    print("\n  Calling _load()...")
    scheduler._load()
    print(f"  _load() done")
    print(f"  tasks count: {len(scheduler.tasks)}")
    print(f"  workers type: {type(scheduler.workers)}")
    print(f"  workers count: {len(scheduler.workers)}")
    if scheduler.workers:
        print(f"  first worker: {scheduler.workers[0]}")
        print(f"  first worker type: {type(scheduler.workers[0])}")
    print(f"  schedule type: {type(scheduler.schedule)}")
    print(f"  schedule keys: {list(scheduler.schedule.keys())}")

    # Build
    print("\n  Calling build()...")
    result = scheduler.build()
    print(f"  build() result: {result}")

    # Apply
    print("\n  Calling apply()...")
    result2 = scheduler.apply()
    print(f"  apply() result: {result2}")

    # Full schedule
    print("\n  Calling schedule()...")
    scheduler2 = PaintingScheduler(task_ids, target_date)
    result3 = scheduler2.schedule()
    print(f"  schedule() result: {result3}")

except Exception as e:
    print(f"  ERROR in scheduler test: {e}")
    traceback.print_exc()
    # Print more details
    print("\n  === DETAILED WORKERS INFO ===")
    if 'scheduler' in locals():
        print(f"  workers: {scheduler.workers}")
        if isinstance(scheduler.workers, list):
            for i, w in enumerate(scheduler.workers):
                print(f"    [{i}]: {w}, type: {type(w)}")
        else:
            print(f"  workers is NOT a list, it's: {type(scheduler.workers)}")
            if hasattr(scheduler.workers, '__dict__'):
                print(f"  dir: {dir(scheduler.workers)}")

print("\n" + "=" * 60)
print("DEBUG END")
print("=" * 60)