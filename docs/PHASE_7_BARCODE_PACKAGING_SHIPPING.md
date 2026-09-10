# Phase 7: Barcode Compatibility and Packaging/Shipping V2

## Objective
V2 Barcode، Package و Shipment را کامل کن، بدون شکستن QRهای V1.

## Barcode Compatibility
- `BarcodeResolver.resolve(payload_or_url)` legacy QRهای OrderItem و PackagingUnit را تشخیص می‌دهد.
- QR legacy بدون MigrationMap هم معتبر باقی می‌ماند.
- در صورت وجود MigrationMap، V2 target برگردانده می‌شود.
- resolver read-only است و هیچ mutation انجام نمی‌دهد.
- endpoint `scan_qr` legacy حفظ شده است.

## Packaging/Shipping
- `PackagingUnit` (V1) → `Package` / `PackageItem` (V2) migration در فاز `barcode` اضافه شد.
- `ShipmentLog` (V1) → `Shipment` / `ShipmentItem` (V2) migration در فاز `barcode` اضافه شد.
- migration idempotent است.
- Package و Shipment statusهای قابل audit دارند.
- V1 داده اصلی تا زمان reconciliation حفظ می‌شود.

## Tests Added
- `BarcodeLegacyTests`: QR legacy OrderItem و PackagingUnit resolve می‌شود، QR نامعتبر unknown برمی‌گرداند، legacy بدون MigrationMap معتبر است، legacy با MigrationMap v2_metadata دارد.
- `MigrationMapIntegrityTests`: unique_together integrity و rollback MigrationMapها.
- `PackagingMultiItemTests`: Package چند PackageItem دارد.
- `ShipmentPartialTests`: Shipment جزئی ShipmentItem ایجاد می‌کند.
- `DuplicateShipmentTests`: شماره shipment تکراری خطا می‌دهد.

## Migration
- `craftflow_migrate_v2 --phase barcode --dry-run|--execute`
- `PackagingUnit` → `Package`
- `ShipmentLog` → `Shipment`
- `MigrationMap` برای هر entity ایجاد می‌شود.

## Status
تکمیل شده.
