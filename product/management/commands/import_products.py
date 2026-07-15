import json
import os
from django.core.management.base import BaseCommand
from django.db import transaction
from product.models import Product, Part, ProductBOM, Material, ProductCategory

class Command(BaseCommand):
    help = 'ایمپورت داده‌ها با نگاشت فنی: F3=Barcode, F2=Name, F4/F5/F26/F18=Edges'

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='add JSON')

    def handle(self, *args, **options):
        file_path = options['json_file']
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"خطا در خواندن فایل: {e}"))
            return

        stats = {'products_created': 0, 'products_updated': 0, 'parts_created': 0}

        with transaction.atomic():
            for dir_entry in data:
                if not isinstance(dir_entry, list) or not dir_entry:
                    continue
                
                files_list = dir_entry[0]
                if not files_list: continue

                # ۱. استخراج اطلاعات محصول از اولین قطعه
                first_part_raw = next((p for f in files_list for p in list(f.values())[0] if p), {})
                if not first_part_raw: continue

                # دسته بندی از Grain
                category_name = str(first_part_raw.get('Grain', 'سایر')).strip()
                if category_name.lower() in ['true', 'false', '0', '1', '']:
                    category_name = "سایر"
                category, _ = ProductCategory.objects.get_or_create(name=category_name)

                # مسیر پوشه و نام محصول
                first_full_path = list(files_list[0].keys())[0]
                dir_path = os.path.dirname(first_full_path)
                product_name = first_part_raw.get('Order', os.path.basename(dir_path))

                # ۲. ایجاد یا آپدیت محصول
                product, created = Product.objects.update_or_create(
                    parts_list_key=dir_path,
                    defaults={'name': product_name, 'category': category}
                    # defaults={'name': product_name}
                )
                product.bom.all().delete()
                
                if created: stats['products_created'] += 1
                else: stats['products_updated'] += 1

                # ۳. پردازش فایل‌ها و قطعات
                for file_dict in files_list:
                    for full_path, parts in file_dict.items():
                        # استخراج متریال از نام فایل (مثلا gerdo.CUT)
                        filename = os.path.basename(full_path)
                        mat_name = filename.split('.')[0]

                        mat, _ = Material.objects.get_or_create(
                            name=mat_name,
                            defaults={'thickness': 16}
                        )

                        for p_data in parts:
                            # ایجاد قطعه با نگاشت جدید شما
                            new_part = Part.objects.create(
                                material=mat,
                                f3=p_data.get('F3', ''),          # بارکد
                                f2=p_data.get('F2', ''),          # نام قطعه
                                name=p_data.get('F2', ''),    # همسان‌سازی با فیلد name
                                length=p_data.get('X', 0),
                                width=p_data.get('Y', 0),
                                f4=p_data.get('F4', ''),          # نوار ۱
                                f5=p_data.get('F5', ''),          # نوار ۲
                                f26=p_data.get('F26', ''),        # نوار ۳
                                f18=p_data.get('F18', ''),        # نوار ۴
                                routing_code=p_data.get('F19', ''), # ایستگاه‌ها
                                grain=p_data.get('Grain', ''),
                                pname=p_data.get('Order', ''),
                                # turn=p_data.get('Turn', ''),
                            )

                            # ثبت در BOM
                            qty = int(p_data.get('Count', 1) or 1)
                            ProductBOM.objects.create(
                                product=product,
                                part=new_part,
                                quantity=qty
                            )
                            stats['parts_created'] += 1

        self.stdout.write(self.style.SUCCESS(f"ایمپورت با موفقیت انجام شد. مجموع قطعات: {stats['parts_created']}"))