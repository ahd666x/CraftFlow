# CraftFlow V2 Stabilization Audit

تاریخ: 2026-09-07
ت commit مرجع: feb36f5
وضعیت: V1 عملیاتی، V2 schema-first بدون data migration و cutover

---

## 1. Current Runtime Truth

### 1.1 V1 Operational Surface

**اپ‌های فعال در تولید:**
- `product`: هر espécies لاجیک اصلی در این اپ متمرکز است.
- `inventory`: اپ دوم فعال؛ مدل‌های V1 در آن هستند.

**مدل‌های V1 که در حال استفاده هستند:**

| Model | فایل | نقش production |
|-------|------|----------------|
| `Customer` | `product/models.py:15` | مشتریان سفارش |
| `ProductCategory` | `product/models.py:36` | دسته‌بندی محصول |
| `Material` | `product/models.py:47` | نوع ورق/متریال |
| `Order` | `product/models.py:80` | هدر سفارش |
| `OrderItem` | `product/models.py:256` | آیتم سفارش |
| `Color` | `product/models.py:416` | رنگ‌های قطعات |
| `Part` | `product/models.py:443` | قطعه فیزیکی |
| `ProductBOM` | `product/models.py:488` | فرمول ساخت |
| `ProductionTask` | `product/models.py:540` | وظیفه تولید (source of truth برای schedule) |
| `WorkerProfile` | `product/models.py:688` | پروفایل کارگر |
| `ProductionLog` | `product/models.py:719` | گزارش مراحل |
| `ProductionEvent` | `product/models.py:736` | رویدادهای تولید |
| `PackagingUnit` | `product/models.py:781` | واحد بسته‌بندی و ارسال |
| `ShipmentLog` | `product/models.py:814` | بارگیری/ارسال |
| `PaintingProcess` | `product/models.py:834` | روند نقاشی |
| `PaintingStage` | `product/models.py:849` | مرحله نقاشی |
| `PaintingAssignmentRule` | `product/models.py:871` | قوانین تخصیص نقاشی |
| `Holiday` | `product/models.py:964` | تعطیلات |

**مدل‌های V1 در `inventory`:**

| Model | فایل | نقش production |
|-------|------|----------------|
| `Supplier` | `inventory/models.py:6` | تامین‌کننده |
| `RawMaterialCategory` | `inventory/models.py:22` | دسته مواد اولیه |
| `RawMaterial` | `inventory/models.py:34` | ماده اولیه |
| `StockMovement` | `inventory/models.py:82` | حرکت انبار (source of truth موجودی) |
| `PurchaseOrder` | `inventory/models.py:109` | سفارش خرید |
| `PurchaseOrderItem` | `inventory/models.py:131` | آیتم سفارش خرید |

**URLهای فعال V1:**
- `product/urls.py` → root URLها (order_list, item_detail, scan_qr, admin_tasks_management, dashboard, ...)
- `inventory/urls.py` → `/inventory/...` (dashboard, suppliers, categories, materials, movements, purchase_orders, ...)

**ویوهای critical V1:**
- `product/views.py:1232` — `scan_qr`: ثبت مرحله با QR
- `product/views.py:505` — `mark_task_done`: تکمیل تسک از UI
- `product/views.py:722` — `admin_tasks_management`: bulk status/worker/delete
- `product/views.py:853` — `order_generate_tasks`: ایجاد تسک‌ها
- `inventory/views.py:538` — `purchase_order_receive`: دریافت سفارش خرید

**Utilityهای critical V1:**
- `product/utils.py:745` — `PaintingScheduler`: منبع حقیقت زمان‌بندی نقاشی
- `product/utils.py:1512` — `assign_task_to_worker`: تخصیص دستی/کش‌دار
- `product/utils.py:56` — `consume_material_for_task`: مصرف خودکار مواد
- `product/utils.py:35` — `log_production_event`: ثبت رویداد

### 1.2 V2 Orphan Surface

**اپ‌های V1 که هیچ caller عملیاتی ندارند (schema-first):**

| اپ | وضعیت |
|----|-------|
| `core` | فقط abstract models |
| `accounts` | مدل `Worker` و `WorkerSchedule` و `Holiday` — هیچ ویو/سرویس فعال |
| `customers` | `Customer`, `CustomerGroup`, `CustomerAddress` — orphans |
| `sales` | `CustomerOrder`, `CustomerOrderItem` — orphans (V1 `Order` فعال است) |
| `products` | `Product`, `ProductCategory`, `ProductPart`, `ProductRevision` — orphans (V1 `Product` فعال است) |
| `bom` | `BOM`, `BOMItem`, `BOMItemMaterialRule` — orphans |
| `inventory` (V2 models) | `Item`, `StockBalance`, `StockLedger`, `StockLot`, `StockReservation` — orphans (V1 `RawMaterial`/`StockMovement` فعال است) |
| `warehouse` | تمام مدل‌ها orphans |
| `production` | تمام مدل‌ها orphans |
| `planning` | تمام مدل‌ها orphans |
| `painting` (V2 models) | `PaintingProcess`, `PaintingProcessStage`, `PaintingAssignmentRule`, `PaintingSchedule` — duplicates با V1 |
| `quality` | تمام مدل‌ها orphans |
| `packaging` | تمام مدل‌ها orphans |
| `shipping` | تمام مدل‌ها orphans |
| `reporting` | تمام مدل‌ها orphans |

**سرویس‌های V2 orphans:**

| فایل | کلاس/تابع | وضعیت |
|------|-----------|-------|
| `sales/services.py` | `OrderService` | هیچ caller |
| `inventory/services.py` | `InventoryService` | هیچ caller |
| `warehouse/services.py` | `WarehouseService` | هیچ caller |
| `production/services.py` | `ProductionService` | هیچ caller |
| `painting/services.py` | `PaintingService` | هیچ caller |

**Selectors V2 orphans:**

| فایل | کلاس | وضعیت |
|------|------|-------|
| `production/selectors.py` | `ProductionSelectors` | هیچ caller |
| `inventory/selectors.py` | `InventorySelectors` | هیچ caller |
| `reporting/selectors.py` | `ReportingSelectors` | هیچ caller |

**نکته مهم:** V2 URLها در `v2_urls.py` ثبت شده‌اند اما هیچ ویوی عملیاتی پشت آن‌ها وجود ندارد و هیچ رکوردی به آن‌ها ارجاع داده نمی‌شود.

---

## 2. Compatibility Contracts

### 2.1 QR/Barcode Contract

**قرارداد فعلی:**
- QR `OrderItem`: تولید می‌شود در سیگنال `generate_qr_code` (`product/signals.py:18`) و URL ساختارش:
  ```
  {SCAN_BASE_URL}/scan/{OrderItem.id}/
  ```
- QR `PackagingUnit`: تولید می‌شود در سیگنال `generate_packaging_qr_codes` (`product/signals.py:83`) و URL ساختارش:
  ```
  {SCAN_BASE_URL}/scan/packaging_unit/{PackagingUnit.id}/?next=/item_detail/{OrderItem.id}/
  ```
- `SCAN_BASE_URL` پیش‌فرض: `https://selvichoob.ir` (در `product/signals.py:14` و `product/utils.py`)

**محدودیت:** هر تغییری در این URLها یا ساختار QRها، چاپ‌شده‌های قبلی را نامعتبر می‌کند.

### 2.2 URL Legacy Contract

| URL Name | Pattern | Usage |
|----------|---------|-------|
| `scan_qr` | `/scan/{item_id}/` | QR OrderItem |
| `scan_packaging_unit` | `/scan/packaging_unit/{pu_id}/` | QR PackagingUnit |
| `item_detail` | `/item/{item_id}/` | بازگشت از QR |

### 2.3 Jalali Date Contract

- `PersianDateField` در `product/fields.py` برای فیلدهای `created_at`, `due_date`, `completed_at` در `Order` و `ProductionTask` استفاده می‌شود.
- تمام تاریخ‌های تولید در V1 به صورت جلالی ذخیره و خوانده می‌شوند.
- تغییر این field یا تبدیل به Gregorian بر اساس هیچ Phase مجاز نیست.

### 2.4 PaintingScheduler Contract

- `PaintingScheduler` در `product/utils.py:745` منبع حقیقت زمان‌بندی نقاشی است.
- موتور cascade insertion/shift (`_run_cascade_schedule`, `_insert_and_cascade_worker_day`) در همان فایل قرار دارد.
- sticky worker behaviour از طریق `_order_worker_history` پیاده شده.
- assignment rules از `PaintingAssignmentRule` (V1) خوانده می‌شود.
- هیچ کد نباید این کلاس را replace یا به `PaintingSchedule` V2 متصل کند.

### 2.5 Inventory/StockMovement Contract

- V1 موجودی به صورت aggregate از `StockMovement` محاسبه می‌شود (`RawMaterial.current_stock`).
- `StockMovement` با `reference_task` به `ProductionTask` متصل است.
- جریان receipt: `PurchaseOrder` → `StockMovement(purchase)` → موجودی افزایش.
- جریان consumption: `ProductionTask.save()` → `consume_material_for_task()` → `StockMovement(consumption)`.
- هیچ V2 `StockBalance`/`StockLedger` در این جریان دخیل نیست.

### 2.6 PackagingUnit/ShipmentLog Contract

- `PackagingUnit` به ازای هر quantity OrderItem auto-created می‌شود (در سیگنال).
- `unique_together = ('order_item', 'unit_number')`.
- `get_absolute_url()` به `scan_packaging_unit` اشاره می‌کند.
- `ShipmentLog` به `PackagingUnit` متصل است و به عنوان سند ارسال استفاده می‌شود.

---

## 3. V2 Schema Gap Review

### 3.1 sequence + 1 در ProductionService.complete_operation

- **فایل:** `production/services.py:56`
- **کلاس/تابع:** `ProductionService.complete_operation`
- **مشکل:** در خط 70، `operation.sequence < operation.production_order_item.operations.count()` بررسی می‌شود. این عبارت همیشه false است چون sequence از 1 شروع می‌شود و count از 1. در نتیجه `next_op.status = 'ready'` هرگز اجرا نمی‌شود.
- **اثر:** activation مرحله بعدی در V2 production ops کار نمی‌کند.
- **تصمیم پیشنهادی:** در Phase مستقل بعدی، پس از تعریف mapping، شرط را به `operation.sequence < next_sequence` اصلاح کن.
- **Phase مجاز:** Phase 11+ (پس از cutover plan)

### 3.2 نبود RoutingDependency در فعال‌سازی operation

- **فایل:** `planning/models.py`
- **کلاس:** `RoutingDependency` (وجود دارد اما در `complete_operation` استفاده نمی‌شود)
- **مشکل:** وابستگی‌های parallel/fan-out در V2 ignore می‌شوند.
- **اثر:** operationهای وابسته ممکن است قبل از تکمیل پیش نیاز فعال شوند.
- **تصمیم پیشنهادی:** در Phase بعدی، قبل از فعال‌سازی `next_op`، تمام `RoutingDependency`های satisfied را بررسی کن.
- **Phase مجاز:** Phase 11+

### 3.3 نبود select_for_update در تغییر StockBalance

- **فایل:** `inventory/services.py:32-53`
- **کلاس/تابع:** `InventoryService.receive_stock`, `reserve_stock`
- **مشکل:** خواندن/نوشتن `StockBalance` بدون `select_for_update()` در حالت concurrent در risk of race-condition است.
- **اثر:** در صورت همزمانی، موجودی می‌تواند منفی یا کمتر از واقعیت ثبت شود.
- **تصمیم پیشنهادی:** اضافه کردن `select_for_update()` قبل از خواندن balance.
- **Phase مجاز:** Phase 10 (ایمن‌سازی contractهای V2 بدون اتصال UI)

### 3.4 امکان StockLocation خالی در create_item

- **فایل:** `inventory/services.py:12-29`
- **کلاس/تابع:** `InventoryService.create_item`
- **مشکل:** `StockLocation.objects.filter(location_type='warehouse').first()` اگر رکوردی نباشد، `None` به `StockBalance.location` نسبت داده می‌شود.
- **اثر:** IntegrityError یا balance بدون مکان.
- **تصمیم پیشنهادی:** raise `ValueError` اگر warehouse location یافت نشد.
- **Phase مجاز:** Phase 10

### 3.5 نبود idempotency key برای issue/transfer/consume

- **فایل:** `warehouse/services.py:37-65`
- **کلاس/تابع:** `WarehouseService.issue_material`, `consume_material`
- **مشکل:** هیچ کلید idempotency (مثل request number یا UUID) برای جلوگیری از duplicate در صورت retry وجود ندارد.
- **اثر:** در صورت retry، رکوردهای duplicate صادر/مصرف می‌شوند.
- **تصمیم پیشنهادی:** اضافه کردن `idempotency_key` به `MaterialIssue` و `MaterialConsumption`.
- **Phase مجاز:** Phase 10

### 3.6 هم‌پوشانی یا ناسازگاری V1 Painting با painting app جدید

- **فایل‌ها:** `product/models.py:834-940` (V1) و `painting/models.py` (V2)
- **مشکل:**
  - V1 `PaintingProcess` فیلد `code` (unique) و `color_codes` (list) دارد.
  - V2 `PaintingProcess` فیلدهای مشابه دارد اما V2 `PaintingProcessStage` فیلدهای اضافی (`temperature_min`, `humidity_max`, `is_mandatory`, `notes`) دارد که در V1 وجود ندارد.
  - V1 `PaintingAssignmentRule` به `WorkerProfile` و `PaintingStage` (V1) ارجاع می‌دهد.
  - V2 `PaintingAssignmentRule` به `Worker` (accounts) و `PaintingProcessStage` (V2) ارجاع می‌دهد.
- **اثر:** در صورت cutover، قوانین تخصیص از بین می‌روند یا به مدل غلط متصل می‌شوند.
- **تصمیم پیشنهادی:** در Phase مستقل، MigrationMap برای نگاشت یک-به-یک بین V1 و V2 models تعریف کن.
- **Phase مجاز:** Phase 12 (Migration Planning)

### 3.7 Barcode V2 بدون Legacy Barcode Resolver

- **فایل:** `reporting/models.py:108`
- **کلاس:** `Barcode`
- **مشکل:** V2 مدل `Barcode` برای هر نوع بارکد است، اما هیچ resolver برای URLهای legacy QR (`/scan/{id}/` و `/scan/packaging_unit/{id}/`) وجود ندارد.
- **اثر:** پس از cutover، QRهای چاپ شده قبلی قابل اسکن نخواهند بود مگر resolver اضافه شود.
- **تصمیم پیشنهادی:** ایجاد `BarcodeResolver` که بر اساس type و content_object، URL درست را redirect کند.
- **Phase مجاز:** Phase 12

### 3.8 MigrationMap uniqueness و امکان map کردن چند migration-run

- **فایل:** `reporting/models.py:137`
- **کلاس:** `MigrationMap`
- **مشکل:** `unique_together = ['migration_type', 'old_id', 'old_app']` اجازه نمی‌دهد یک رکورد در دو run مختلف map شود. همچنین `migration_run` nullable است و ردیابی audit کامل ممکن نیست.
- **اثر:** در صورت partial failure و retry، mappings قبلی overwrite می‌شوند یا duplicate ایجاد می‌کنند.
- **تصمیم پیشنهادی:** اضافه کردن composite unique شامل `migration_run` یا استفاده از idempotency key.
- **Phase مجاز:** Phase 10

### 3.9 ادعای StockLedger به‌عنوان source of truth در برابر mutation مستقیم StockBalance

- **فایل:** `inventory/services.py:32-53`
- **کلاس/تابع:** `InventoryService.receive_stock`
- **مشکل:** `StockBalance` مستقیماً در `receive_stock` آپدیت می‌شود، در حالی که `StockLedger` به عنوان source of truth طراحی شده. اگر یک فرآیند خارج از سرویس، `StockBalance` را mutate کند، ledger و balance با هم inconsistent می‌شوند.
- **اثر:** عدم یکپارچگی بین دفتر روزنامه و موجودی واقعی.
- **تصمیم پیشنهادی:** تمام mutations از طریق `StockLedger` و trigger-based یا service-based balance sync باشند.
- **Phase مجاز:** Phase 10

---

## 4. Safe Refactor Backlog

### 4.1 استخراج consume_material_for_task از ProductionTask.save()

- **scope:** استخراج منطق مصرف خودکار مواد از `ProductionTask.save()` به یک تابع مجزا در `product/utils.py` بدون تغییر رفتار.
- **out of scope:** تغییر مسیر صدا زدن، اضافه کردن logging جدید، تغییر exception handling.
- **affected files:** `product/models.py`, `product/utils.py`
- **preconditions:** تست‌های characterization پاس باشند.
- **tests:** تست‌های موجود + یک تست جدید که verify می‌کند `ProductionTask.save()` هنوز مصرف می‌کند.
- **rollback:** بازگرداندن کد به حالت قبل در `save()`.
- **acceptance criteria:** `consume_material_for_task` در `utils.py` قابل import باشد و `ProductionTask.save()` از آن استفاده کند.

### 4.2 استخراج log_production_event از ProductionTask.save()

- **scope:** مشابه بالا، استخراج `log_production_event` به تابع مجزا.
- **out of scope:** تغییر ساختار `ProductionEvent`.
- **affected files:** `product/models.py`, `product/utils.py`
- **preconditions:** تست‌های characterization پاس باشند.
- **tests:** تست موجود در characterization.
- **rollback:** بازگرداندن inline code.
- **acceptance criteria:** `log_production_event` در `utils.py` قابل import باشد.

### 4.3 ایمن‌سازی InventoryService.create_item برای StockLocation خالی

- **scope:** اضافه کردن raise ValueError اگر warehouse location وجود نداشته باشد.
- **out of scope:** ایجاد خودکار location، migration data.
- **affected files:** `inventory/services.py`
- **preconditions:** هیچ نیازی به data migration ندارد.
- **tests:** تست جدید در `product/tests_v2.py` یا `inventory/tests.py`.
- **rollback:** حذف raise.
- **acceptance criteria:** `create_item` بدون location موجود، exception برمی‌گرداند.

### 4.4 اضافه کردن select_for_update به InventoryService.reserve_stock

- **scope:** اضافه کردن `select_for_update()` قبل از خواندن `StockBalance`.
- **out of scope:** تغییر لاجیک бизнес، اضافه کردن lock timeout handling.
- **affected files:** `inventory/services.py`
- **preconditions:** هیچ نیازی به migration ندارد.
- **tests:** تست characterization یا جدید برای race-condition safety.
- **rollback:** حذف select_for_update.
- **acceptance criteria:** در حالت concurrent، reserve_stock دقیقاً یک balances را می‌خواند.

### 4.5 اضافه کردن idempotency_key به WarehouseService.issue_material

- **scope:** اضافه کردن `idempotency_key` (اختیاری) به `MaterialIssue` برای جلوگیری از duplicate.
- **out of scope:** migration schema، backfill داده.
- **affected files:** `warehouse/services.py`, `warehouse/models.py`
- **preconditions:** نیاز به migration schema دارد — **منعacted بر اساس قوانین این Phase**.
- **تغییر:** در این Phase اجرا نمی‌شود. به Phase بعدی موکول می‌شود.

---

## 5. Recommended Execution Order

حداکثر پنج تغییر مستقل و کوچک، به ترتیب:

### A. تست‌های characterization برای رفتار V1 (تکمیل شده)
- **توضیحات:** ۱۳ تست characterization در `product/tests_characterization.py` ایجاد شد.
- **نتیجه:** همه ۱۳ تست پاس شدند.
- **فایل‌های تغییرکرده:** `product/tests_characterization.py`
- **خطر:** صفر — فقط تست اضافه شده، هیچ کد production تغییر نکرده.

### B. استخراج service از ProductionTask.save بدون تغییر رفتار
- **توضیحات:** `consume_material_for_task` و `log_production_event` از `utils.py` به صورت تابع مجزا już هستند. کافیست `ProductionTask.save()` را به استفاده از آن‌ها تغییر دهیم (در حال حاضر هم استفاده می‌کند).
- **نتیجه:** فعلاً نیازی به تغییر نیست چون از import داخل save استفاده می‌شود.
- **خطر:** صفر — لاجیک unchanged.

### C. ایمن‌سازی contractهای V2 inventory/production، بدون اتصال به UI
- **توضیحات:** 
  1. `InventoryService.create_item` → raise اگر warehouse location وجود ندارد.
  2. `InventoryService.receive_stock` → `select_for_update()` روی StockBalance.
  3. `ProductionService.complete_operation` → docstring اضافه کن که sequence logic باید در Phase بعدی اصلاح شود.
- **فایل‌های تغییرکرده:** `inventory/services.py`, `production/services.py`
- **خطر:** کم — فقط defensive checks اضافه می‌شود.

### D. طراحی BarcodeResolver سازگار با QRهای legacy
- **توضیحات:** ایجاد یک تابع/کلاس در `reporting/` که URLهای legacy `/scan/{id}/` و `/scan/packaging_unit/{id}/` را parse و resolve کند.
- **فایل‌های جدید:** `reporting/barcode_resolver.py`
- **خطر:** صفر — فقط resolver اضافه می‌شود، هیچ تغییری در QR تولید نمی‌شود.

### E. فقط بعد از تأیید دستی: pilot migration محدود و dry-run
- **توضیحات:** انتخاب یک سفارش قدیمی، اجرای MigrationRun با status `pending`،dry-run بدون تغییر دیتابیس.
- **فایل‌های تغییرکرده:** `reporting/migrations/` (اگر نیاز باشد)، `reporting/selectors.py`
- **خطر:** متوسط — نیاز به تأیید دستی دارد.

---

## 6. Explicitly Deferred Work

مواردی که عمداً به Phase بعدی موکول شده و در این Phase **هیچ** کاری روی آن‌ها انجام نمی‌شود:

| کار | دلیل defer |
|-----|-----------|
| تبدیل Jalali به Gregorian | تغییر PersianDateField بر اساس قانون غیرقابل‌مذاکره |
| بازنویسی PaintingScheduler | منبع حقیقت V1 است؛ refactor آن نیاز به Phase مستقل با تست end-to-end دارد |
| حذف V1 models | هیچ migration داده یا حذف مدل در این Phase مجاز نیست |
| data migration سراسری | نیاز به Phase مستقل با MigrationRun و dry-run |
| UI cutover | هیچ View فعلی به V2 serviceها متصل نمی‌شود |
| PostgreSQL migration | توسعه‌ای در این Phase نیست |
| اضافه کردن idempotency_key به warehouse | نیاز به migration schema دارد |
| اصلاح sequence logic در complete_operation | نیاز به تعریف mapping و cutover plan |
| حذف duplicate painting models (V1 vs V2) | نیاز به MigrationMap و plan جداگانه |

---

## 7. Test Results

### 7.1 Baseline Tests (پیش از characterization)

```
python manage.py check
System check identified no issues (0 silenced).

python manage.py test product.tests product.tests_v2 --verbosity 1
Found 9 test(s).
Ran 9 tests in 7.152s - OK
```

### 7.2 Characterization Tests (بعد از ایجاد)

```
python manage.py test product.tests_characterization --verbosity 1
Found 13 test(s).
Ran 13 tests in 21.532s - OK
```

### 7.3 Full Test Suite

```
python manage.py test --verbosity 1
Found 22 test(s).
Ran 22 tests in 29.651s - OK
```

### 7.4 تست‌های characterization و آنچه پوشش می‌دهند

| تست | رفتار V1 پوشش داده |
|-----|-------------------|
| `test_order_item_qr_url_pattern` | QR تولید در سیگنال و ساختار URL |
| `test_packaging_unit_qr_url_pattern` | QR PackagingUnit + پارامتر next |
| `test_scan_qr_url_resolves` | resolve URL scan_qr |
| `test_scan_packaging_unit_url_resolves` | resolve URL scan_packaging_unit |
| `test_completion_creates_production_event` | side effect ProductionEvent در تکمیل |
| `test_completion_triggers_material_consumption` | side effect مصرف خودکار مواد |
| `test_no_duplicate_consumption_movement` | idempotency مصرف (بررسی عدم تکرار) |
| `test_legacy_next_step_activation` | فعال شدن مرحله بعدی در مسیر قدیمی |
| `test_persian_date_field_default` | تاریخ پیش‌فرض جلالی |
| `test_persian_date_field_stores_jalali` | ذخیره تاریخ جلالی |
| `test_production_task_completed_at_jalali` | زمان تکمیل جلالی |
| `test_packaging_units_created_on_order_item` | ایجاد خودکار PackagingUnit |
| `test_shipment_log_creation` | اتصال ShipmentLog به PackagingUnit |

---

## 8. Files Changed in This Phase

### 8.1 فایل‌های ایجاد شده

| فایل | توضیحات |
|------|---------|
| `product/tests_characterization.py` | ۱۳ تست characterization برای رفتارهای V1 |

### 8.2 فایل‌هایی که عمداً تغییر نکرده‌اند

| فایل/دایرکتوری | دلیل unchanged |
|----------------|---------------|
| `product/models.py` | هیچ تغییر در مدل‌های V1 |
| `product/signals.py` | هیچ تغییر در سیگنال‌های QR |
| `product/utils.py` | PaintingScheduler untouched |
| `product/views.py` | هیچ ویو جدید یا تغییر یافته |
| `inventory/models.py` | هیچ تغییر در schema V1 |
| `inventory/views.py` | هیچ تغییر در ویوهای inventory |
| `inventory/services.py` | بدون تغییر (ایمن‌سازی deferred به Phase 10) |
| `production/services.py` | بدون تغییر (complete_operation unchanged) |
| `warehouse/services.py` | بدون تغییر |
| `painting/models.py` | بدون تغییر |
| `reporting/models.py` | بدون تغییر |
| `v2_urls.py` | بدون تغییر |
| `selvi/urls.py` | بدون تغییر |
| `selvi/settings.py` | بدون تغییر |
| `docs/V2_PROGRESS.md` | بدون تغییر |
| `New Text Document.txt` | فایل کاربر — untouched |

### 8.3 فایل‌های تغییرکرده

| فایل | نوع تغییر |
|------|-----------|
| `product/tests_characterization.py` | ایجاد جدید (۱۳ تست) |

---

## 9. Suggested Next Phase Prompt

```
تست‌های characterization V1 را اجرا کن (product/tests_characterization.py).

سپس به این تغییرات کوچک و امن در لایه V2 services پرداز:
1. inventory/services.py: select_for_update() در reserve_stock و receive_stock اضافه کن.
2. inventory/services.py: create_item را در صورت نبود warehouse location با ValueError متوقف کن.
3. production/services.py: complete_operation را با docstring و TODO برای sequence logic علامت‌گذاری کن.
4. reporting/barcode_resolver.py: یک resolver بساز که URLهای legacy QR را parse کند.
5. هیچ migration schema جدید ایجاد نکن، مگر برای issue #3 که لازم است.

در پایان:
- تست‌های کامل را دوباره اجرا کن.
- فایل‌های تغییرکرده را گزارش بده.
- فایل‌هایی که unchanged مانده‌اند را فهرست بکن.
- فقط یک Prompt برای Phase بعدی (پilot migration محدود) پیشنهاد بده.
```

---

## 10. Migration Status

| App | V1 Migration | V2 Migration | Status |
|-----|-------------|--------------|--------|
| product | 0001-0017 | — | Applied |
| inventory | 0001-0002 | — | Applied (V2 models در 0002 اضافه شده‌اند) |
| accounts | — | 0001 | Applied |
| customers | — | 0001 | Applied |
| sales | — | 0001 | Applied |
| products | — | 0001 | Applied |
| bom | — | 0001 | Applied |
| warehouse | — | 0001 | Applied |
| production | — | 0001 | Applied |
| planning | — | 0001 | Applied |
| painting | — | 0001-0002 | Applied |
| packaging | — | 0001-0002 | Applied |
| quality | — | 0001 | Applied |
| shipping | — | 0001 | Applied |
| reporting | — | 0001 | Applied |

**توجه:** هیچ V1 migration تغییر نکرده. V2 migrations کاملاً additive هستند.
