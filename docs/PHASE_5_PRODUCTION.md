# Phase 5: Routing and Production Migration

## هدف
تکمیم مدل‌های تولید V2، ایجاد مهاجرت امن از V1 به V2، و پوشش تستی کامل جریان‌های تولید.

## مدل‌های V2 (production/models.py)

### ProductionOrder
- `order`: FK به `sales.CustomerOrder`
- `routing`: FK به `planning.Routing`
- `bom_revision`: Revision BOM در سطح سفارش تولید
- `status`: finite state machine
  - `draft` → `planned` → `released` → `in_progress` → `paused` → `completed`
  - هر حالت فقط به مجازهای تعریف شده در `PO_TRANSITIONS` می‌تواند برود.

### ProductionOrderItem
- `production_order`: FK به `ProductionOrder`
- `customer_order_item`: FK به `sales.CustomerOrderItem`
- `product`: FK به `products.Product`
- `bom`: FK به `bom.BOM`
- **`bom_revision`**: Revision BOM در زمان ایجاد
- **`bom_snapshot`**: JSON snapshot از آیتم‌های BOM و قوانین مواد
- `routing`: FK به `planning.Routing`
- **`routing_revision`**: Revision Routing در زمان ایجاد
- **`routing_snapshot`**: JSON snapshot از عملیات مسیر تولید
- `quantity`, `completed_quantity`, `scrapped_quantity`

### ProductionOperation
- `production_order`, `production_order_item`
- `operation_name`, `operation_code`, `work_center`, `sequence`
- `status`: finite state machine
  - `waiting` → `ready` → `in_progress` → `paused` → `completed`
  - همچنین `skipped`, `failed`
  - تعریف شده در `OPERATION_TRANSITIONS`
- `setup_time_minutes`, `run_time_minutes`
- `completed_quantity`, `scrapped_quantity`
- فیلدهای سازگاری V1: `part`, `scanned_by`, `completed_at`, `painting_stage`, `assigned_worker`, `order_item`, `color_part`

### OperationAssignment
- تخصیص کارگر به عملیات
- `operation`, `worker`, `status`
- `status`: `assigned` → `started` → `completed` → `released`

### OperationExecution
- ثبت اجرای واقعی یک عملیات
- `operation`, `worker`, `started_at`, `ended_at`
- `quantity_produced`, `quantity_scrapped`
- `setup_time_minutes`, `run_time_minutes`
- `is_completed`

### WIPUnit
- واحد در حال تولید (Work In Progress)
- `production_order`, `production_order_item`
- `serial_number`: منحصر به فرد
- `status`: `in_progress`, `waiting`, `completed`, `scrapped`
- `current_operation`: FK به `ProductionOperation`

### WIPTransfer
- ثبت انتقال WIP بین عملیات
- `wip_unit`, `from_operation`, `to_operation`
- `from_location`, `to_location`: FK به `inventory.StockLocation`
- `transferred_by`, `transferred_at`, `notes`

## قوانین کلیدی

### 1. ProductionTask V1 تغییر destructive نمی‌دهد
- مدل `product.ProductionTask` بدون تغییر باقی می‌ماند.
- تابع `LegacyProductionService.complete_task` به‌صورت کاملاً backward compatible حفظ شده.
- هیچ فیلد یا行为 V1 حذف یا تغییر نمی‌دهد.

### 2. فعال‌سازی عملیات بعدی فقط از طریق RoutingDependency
- sequence + 1 برای فعال‌سازی **ممنوع** است.
- فقط وابستگی‌های ثبت شده در `planning.RoutingDependency` باعث become `ready` شدن successor می‌شوند.
- در نبود dependency، operation بعدی به‌صورت خودکار ready نمی‌شود.

### 3. Snapshot/Version برای BOM و Routing
- هر `ProductionOrderItem` دارای `bom_revision`, `routing_revision`, `bom_snapshot`, `routing_snapshot` است.
- این snapshot در زمان ایجاد `ProductionOrderItem` ثبت می‌شود.
- `ProductionService.add_production_order_item` به‌صورت خودکار این فیلدها را پر می‌کند.

### 4. Partial Completion Policy صریح
- `ProductionService.complete_operation`:
  - `force_complete=False`: فقط زمانی operation را `completed` می‌کند که `completed_quantity >= run_time_minutes`.
  - `force_complete=True`: حتی با مقدار صفر نیز operation را `completed` می‌کند.
- `ProductionService.partial_complete_operation`:
  - `quantity` باید > 0 باشد مگر `force=True`.
  - operation به `completed` نمی‌رود مگر `force=True` یا `completed_quantity >= quantity`.

### 5. Transitionهای تمام مدل‌ها validate می‌شوند
- `ProductionStateMachine.transition_operation`
- `ProductionStateMachine.transition_production_order`
- `ProductionStateMachine.transition_batch`
- `ProductionService.start_operation`
- `ProductionService.pause_operation`
- `ProductionService.resume_operation`

### 6. complete/start/pause/assign/transfer در service هستند
- `ProductionService.complete_operation`
- `ProductionService.start_operation`
- `ProductionService.pause_operation`
- `ProductionService.resume_operation`
- `ProductionService.assign_worker`
- `ProductionService.start_assignment`
- `ProductionService.complete_assignment`
- `ProductionService.transfer_wip`
- `ProductionService.create_wip_unit`

### 7. هیچ View هنوز به V2 Production وصل نشده
- `production/urls.py`: خالی (`urlpatterns = []`)
- هیچ view، serializer یا endpoint عمومی برای V2 Production تعریف نشده است.

## مهاجرت V1 → V2

### دستور مهاجرت
```bash
python manage.py craftflow_migrate_v2 --phase production --dry-run
python manage.py craftflow_migrate_v2 --phase production --execute
```

### نگاشت‌ها
| V1 | V2 | روش |
|---|---|---|
| `product.Order` | `sales.CustomerOrder` | Order → CustomerOrder |
| `product.OrderItem` | `sales.CustomerOrderItem` | OrderItem → CustomerOrderItem |
| `product.Order` | `production.ProductionOrder` | Order → ProductionOrder |
| `product.ProductionTask` | `production.ProductionOperation` | ProductionTask → ProductionOperation |

### Status Mapping
| V1 Order | V2 CustomerOrder / ProductionOrder |
|---|---|
| `draft` | `draft` |
| `planned` | `planned` |
| `producing` | `in_progress` |
| `completed` | `completed` |
| `cancelled` | `cancelled` |

| V1 ProductionTask | V2 ProductionOperation |
|---|---|
| `waiting` | `waiting` |
| `pending` | `ready` |
| `done` | `completed` |

### Partial Migration (عملیات)
- اگر Phase 5 قبلاً اجرا شده باشد، ران مجدد idempotent است (بر اساس `MigrationMap`).
- برای rollback:
```bash
python manage.py craftflow_migrate_v2 --rollback <RUN_ID>
```

## تست‌ها

### dependency
- `ProductionDependencyTests.test_no_dependency_no_auto_activation`: بدون RoutingDependency، operation بعدی ready نمی‌شود.
- `ProductionDependencyTests.test_dependency_based_activation`: با RoutingDependency، operation بعدی به `ready` می‌رود.

### partial completion
- `ProductionDependencyTests.test_partial_completion_does_not_complete_without_force`: partial بدون force، operation را completed نمی‌کند.
- `ProductionDependencyTests.test_force_complete_partial`: force_complete=True، تکمیل جزئی را accepted می‌کند.

### invalid transition
- `ProductionTransitionTests.test_invalid_transition_waiting_to_completed_raises`: waiting → completed خطا می‌دهد.
- `ProductionTransitionTests.test_invalid_transition_completed_to_any_raises`: completed → هر حالتی خطا می‌دهد.
- `ProductionTransitionTests.test_valid_transition_waiting_to_ready`: waiting → ready موفق.
- `ProductionTransitionTests.test_valid_transition_ready_to_in_progress`: ready → in_progress موفق.

### worker assignment
- `ProductionWorkerAssignmentTests.test_assign_worker_creates_assignment`: تخصیص کارگر OperationAssignment ایجاد می‌کند.
- `ProductionWorkerAssignmentTests.test_assign_worker_twice_returns_existing`: reassign assignsion موجود را برمی‌گرداند.
- `ProductionWorkerAssignmentTests.test_start_assignment_requires_assigned_status`: start فقط در حالت assigned مجاز است.
- `ProductionWorkerAssignmentTests.test_complete_assignment_requires_started_status`: complete فقط در حالت started مجاز است.

### WIP transfer
- `ProductionWIPTransferTests.test_wip_transfer_creates_transfer_record`: انتقال WIP رکورد WIPTransfer ایجاد می‌کند.
- `ProductionWIPTransferTests.test_duplicate_wip_transfer_raises`: انتقال تکراری به همان operation خطا می‌دهد.
- `ProductionWIPTransferTests.test_wip_transfer_to_wrong_order_item_raises`: انتقال به آیتم سفارش دیگر خطا می‌دهد.

### rollback
- `MigrationRollbackTests.test_rollback_deletes_migration_maps`: rollback MigrationMapهای run را حذف می‌کند.

## فایل‌های تغییر یافته
- `production/models.py`: اضافه شدن فیلدهای snapshot به `ProductionOrderItem`
- `production/services.py`: رفع indent bug، اضافه شدن `start_operation`, `pause_operation`, `resume_operation`، و بهبود `_get_direct_successors`
- `reporting/management/commands/craftflow_migrate_v2.py`: اضافه شدن فاز مهاجرت production
- `product/tests_v2_domain_contracts.py`: اضافه شدن تست‌های Phase 5
- `production/migrations/0004_add_production_order_item_snapshots.py`: مهاجرت جدید

## نکات پایانی
- V1 ProductionTask کاملاً بدون تغییر باقی مانده.
- هیچ View یا URL عمومی برای V2 Production تعریف نشده است.
- تمام transitionها از طریق `ProductionStateMachine` یا `ProductionService` اعتبارسنجی می‌شوند.
- WIP transfer از duplicate prevention و dependency gate پشتیبانی می‌کند.
