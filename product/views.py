import io
import ast
import json
import logging
import math
import os
import re
import xml.etree.ElementTree as ET
from datetime import timedelta
from xml.dom import minidom

import pandas as pd
from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import models, transaction
from django.db.models import Count, Prefetch, Q
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import (get_list_or_404, get_object_or_404, redirect,
                               render)

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from .models import Order, Customer, OrderItem, Color, Product, ProductCategory
from .forms import CustomerInfoForm, OrderItemForm, ColorSelectionForm
from django.urls import reverse
from django.utils import timezone
from django.forms import inlineformset_factory, modelformset_factory
from .decorators import admin_or_manager_required , staff_or_representative_required
from .models import *
from .forms import *
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q, Count, F, OuterRef, Subquery, IntegerField, Exists
from django.shortcuts import render
from .decorators import staff_or_representative_required
from .models import OrderItem, ProductCategory, Product, STATION_CHOICES, PackagingUnit
import jdatetime
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone

from .decorators import admin_or_manager_required
from .models import Order, OrderItem, ProductionTask, PackagingUnit, STATION_CHOICES
from django.views.decorators.http import require_POST


import datetime as dt
import pandas as pd
import jdatetime
import math
from django.db import models

logger = logging.getLogger(__name__)










@login_required
@staff_or_representative_required
@require_POST
def order_generate_tasks(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    if order.generate_tasks():
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'تسک‌ها قبلاً ایجاد شده‌اند.'})




@login_required
@admin_or_manager_required
def dashboard(request):
    # آمار کلی سفارشات
    total_orders = Order.objects.count()
    active_orders = Order.objects.filter(status__in=['draft', 'planned', 'producing']).count()
    completed_orders = Order.objects.filter(status='completed').count()
    producing_orders = Order.objects.filter(status='producing').count()

    # ارسال‌های امروز
    today_shamsi = jdatetime.date.today()
    today_gregorian = today_shamsi.togregorian()
    shipped_today = PackagingUnit.objects.filter(
        is_shipped=True,
        shipped_at__date=today_gregorian
    ).count()

    # بار کاری ایستگاه‌ها
    station_load = []
    for code, name in STATION_CHOICES:
        pending = ProductionTask.objects.filter(station_name=code, status='pending').count()
        waiting = ProductionTask.objects.filter(station_name=code, status='waiting').count()
        station_load.append({
            'name': name,
            'pending': pending,
            'waiting': waiting,
            'total': pending + waiting,
        })

    # آخرین سفارشات
    latest_orders = Order.objects.select_related('customer', 'user').order_by('-id')[:5]

    context = {
        'total_orders': total_orders,
        'active_orders': active_orders,
        'completed_orders': completed_orders,
        'producing_orders': producing_orders,
        'shipped_today': shipped_today,
        'station_load': station_load,
        'latest_orders': latest_orders,
        'today_shamsi': today_shamsi,
    }
    return render(request, 'dashboard.html', context)














# -------------------------------------------------------------------
#     سفارش ها و پرینت فرم ها
# -------------------------------------------------------------------

# @login_required
# @staff_or_representative_required
# def order_list(request):
#     orders = Order.objects.select_related('customer').all()

#     # فیلتر وضعیت (دکمه‌ها)
#     status = request.GET.get('status')
#     if status:
#         orders = orders.filter(status=status)

#     # جستجوی عمومی (شماره یا نام مشتری)
#     q = request.GET.get('q')
#     if q:
#         orders = orders.filter(
#             models.Q(id__icontains=q) |
#             models.Q(customer__name__icontains=q) 
#             # models.Q(customerr__icontains=q)
#         )

#     # فیلترهای اختصاصی ستون‌ها
#     id_filter = request.GET.get('id_filter')
#     if id_filter:
#         orders = orders.filter(id__icontains=id_filter)

#     customer_filter = request.GET.get('customer_filter')
#     if customer_filter:
#         orders = orders.filter(customer__name__icontains=customer_filter)

#     date_from = request.GET.get('date_from')
#     if date_from:
#         orders = orders.filter(created_at__gte=date_from)

#     date_to = request.GET.get('date_to')
#     if date_to:
#         orders = orders.filter(created_at__lte=date_to)

#     # مرتب‌سازی
#     sort = request.GET.get('sort', '-id')
#     orders = orders.order_by(sort)

#     # صفحه‌بندی
#     paginator = Paginator(orders, 200)
#     page_number = request.GET.get('page')
#     page_obj = paginator.get_page(page_number)

#     context = {
#         'orders': page_obj,
#         'status_filter': status,
#         'search_query': q,
#         'id_filter': id_filter,
#         'customer_filter': customer_filter,
#         'date_from': date_from,
#         'date_to': date_to,
#         'sort': sort,
#     }
#     return render(request, 'order_list.html', context)



@login_required
@staff_or_representative_required
def order_list(request):
    orders = Order.objects.select_related('customer').all().order_by('-id')  # مرتب‌سازی نزولی

    # فیلتر وضعیت
    status = request.GET.get('status')
    if status:
        orders = orders.filter(status=status)

    # جستجوی عمومی
    q = request.GET.get('q')
    if q:
        orders = orders.filter(
            Q(id__icontains=q) |
            Q(customer__name__icontains=q) |
            Q(user__username__icontains=q) |
            Q(number__icontains=q)
        )

    # فیلترهای اختصاصی ستون‌ها
    id_filter = request.GET.get('id_filter')
    if id_filter:
        orders = orders.filter(id__icontains=id_filter)

    customer_filter = request.GET.get('customer_filter')
    if customer_filter:
        orders = orders.filter(customer__name__icontains=customer_filter)

    # صفحه‌بندی
    paginator = Paginator(orders, 200)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'orders': page_obj,
        'status_filter': status,
        'search_query': q,
        'id_filter': id_filter,
        'customer_filter': customer_filter,
    }
    return render(request, 'order_list.html', context)









@login_required
@staff_or_representative_required
def order_item_list(request):
    items = OrderItem.objects.select_related(
        'order__user', 'product__category'
    ).prefetch_related(
        'logs', 'ordercolor'
    ).order_by('-order__created_at')

    # جستجوی عمومی
    q = request.GET.get('q')
    if q:
        items = items.filter(
            Q(order__id__icontains=q) |
            Q(id__icontains=q) |
            Q(order__customer__user__username__icontains=q) |
            Q(product__name__icontains=q) |
            Q(product__category__name__icontains=q)
        )

    # فیلترهای کشویی
    customer_id = request.GET.get('customer')
    if customer_id:
        items = items.filter(order__customer__user_id=customer_id)

    category_id = request.GET.get('category')
    if category_id:
        items = items.filter(product__category_id=category_id)

    product_id = request.GET.get('product')
    if product_id:
        items = items.filter(product_id=product_id)

    # مرتب‌سازی
    sort = request.GET.get('sort', '-id')
    items = items.order_by(sort)

    # صفحه‌بندی
    paginator = Paginator(items, 200)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # وضعیت مراحل برای هر آیتم (تبدیل به تاریخ شمسی)
    for item in page_obj:
        stage_dates = {}
        for log in item.logs.all():
            if log.created_at:
                # log.created_at یک jdatetime.date است
                jdate = log.created_at
                stage_dates[log.stage] = f"{jdate.month:02d}/{jdate.day:02d}"
        item.stage_dates = stage_dates
        item.color = item.color_summary

    # لیست‌های پایه برای فیلترهای کشویی
    customers = User.objects.all()
    categories = ProductCategory.objects.all()

    # محصولات: اگر دسته‌ای انتخاب شده باشد، فقط محصولات آن دسته را بفرستیم
    if category_id:
        products = Product.objects.filter(category_id=category_id).order_by('name')
    else:
        products = Product.objects.none()

    context = {
        'items': page_obj,
        'station_choices': STATION_CHOICES,
        'search_query': q,
        'customers': customers,
        'categories': categories,
        'products': products,
        'selected_customer': customer_id,
        'selected_category': category_id,
        'selected_product': product_id,
        'sort': sort,
    }
    return render(request, 'order_item.html', context)


@login_required
@staff_or_representative_required
def item_detail(request, pk):
    item = get_object_or_404(
        OrderItem.objects.select_related('product', 'order__customer').prefetch_related('logs'),
        pk=pk
    )
    
    # ۱. وضعیت کلی ایستگاه‌ها (از روی ProductionLog)
    stage_status_list = []
    for code, name in STATION_CHOICES:
        log = item.logs.filter(stage=code).first()
        if log and log.created_at:
            jdate = log.created_at
            stage_status_list.append(f"{jdate.month:02d}/{jdate.day:02d}")
        else:
            stage_status_list.append(None)
    
    # ۲. دریافت همه تسک‌های این سفارش
    all_tasks = ProductionTask.objects.filter(order=item.order).select_related('part')
    
    # ۳. ساخت نگاشت از part_id به station -> status
    # همچنین نگاشت از base_part_id برای قطعات داینامیک
    task_map = {}
    for task in all_tasks:
        task_map[(task.part_id, task.station_name)] = task.status
        if task.part.base_part_id:
            # اگر قطعه داینامیک است، وضعیت را به قطعه اصلی هم نسبت بده
            task_map[(task.part.base_part_id, task.station_name)] = task.status
    
    # ۴. ساخت لیست قطعات BOM
    bom_parts = []
    for bom_entry in item.product.bom.select_related('part').all():
        part = bom_entry.part
        station_status = {}
        for code, name in STATION_CHOICES:
            status = task_map.get((part.id, code))
            station_status[code] = status
        bom_parts.append({
            'part': part,
            'quantity': bom_entry.quantity,
            'station_status': station_status,
        })
    
    context = {
        'item': item,
        'stage_status_list': stage_status_list,
        'station_choices': STATION_CHOICES,
        'bom_parts': bom_parts,
    }
    return render(request, 'item.html', context)


@login_required
@staff_or_representative_required
def scan_qr(request, pk):
    item = get_object_or_404(OrderItem.objects.select_related('order'), pk=pk)

    if not hasattr(request.user, 'workerprofile'):
        messages.error(request, "پروفایل کاری ندارید")
        return redirect('item_detail', pk=pk)

    stage = request.user.workerprofile.stage

    # جلوگیری از ثبت تکراری
    if ProductionLog.objects.filter(order_item=item, stage=stage).exists():
        messages.warning(request, "قبلاً ثبت شده")
        return redirect('item_detail', pk=pk)

    # ثبت لاگ
    ProductionLog.objects.create(
        order_item=item,
        stage=stage,
        user=request.user
    )

    # آپدیت تسک واقعی (اولین تسک pending مرتبط با این سفارش و ایستگاه)
    task = ProductionTask.objects.filter(
        order=item.order,
        station_name=stage,
        status='pending'
    ).first()

    if not task:
        messages.error(request, "مرحله مجاز نیست")
        return redirect('item_detail', pk=pk)

    task.status = 'done'
    task.scanned_by = request.user
    task.save()

    messages.success(request, "مرحله ثبت شد ✅")
    return redirect('item_detail', pk=pk)


@login_required
@admin_or_manager_required
def print_sheet(request, pk):
    item = get_object_or_404(
        OrderItem.objects.select_related('order__customer', 'product__category'),
        pk=pk
    )
    item.color = item.color_summary
    bom_list = item.product.bom.select_related('part').all()
    item.bompart = [{'part': b.part, 'quantity': b.quantity} for b in bom_list]
    return render(request, 'print.html', {'item': item})


@login_required
@admin_or_manager_required
def print_lable(request, pk):
    item = get_object_or_404(OrderItem.objects.select_related('order__customer', 'product__category'),pk=pk)
    item.color = item.color_summary
    return render(request, 'print_lable.html', {'item': item})

@login_required
@admin_or_manager_required
def order_print(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related('items__product__category', 'items__ordercolor'),
        id=order_id
    )
    items_data = []
    for item in order.items.all():
        items_data.append({
            'id': item.id,
            'product': item.product.name,
            'category': item.product.category.name,
            'quantity': item.quantity,
            'size': item.size,
            'colors': item.color_summary,
            'notes': item.notes
        })
    return render(request, 'order_print.html', {
        'order': order,
        'items': items_data,
        'customer': order.customer.name if order.customer else ''
    })






# -------------------------------------------------------------------
#     فایل برش
# -------------------------------------------------------------------
@login_required
@staff_or_representative_required
def export_autocut_xml(request, order_id):
    order = get_object_or_404(Order, pk=order_id)

    # فقط تسک‌های ایستگاه برش (cut) که وضعیت pending دارند
    cut_tasks = ProductionTask.objects.filter(
        order=order,
        station_name='cut',
        status='pending'
    ).select_related('part', 'part__material')

    # گروه‌بندی بر اساس متریال
    tasks_by_material = {}
    for task in cut_tasks:
        material = task.part.material
        if material not in tasks_by_material:
            tasks_by_material[material] = []
        tasks_by_material[material].append(task)

    # ایجاد ریشه XML با namespace
    NS = "http://www.King-stone.com"
    ET.register_namespace('', NS)
    root = ET.Element(f"{{{NS}}}AutoCUT", {"ver": "500"})

    project = ET.SubElement(root, f"{{{NS}}}Project", {
        "Name": "Project",
        "Selected": "0",
        "Update": "0",
        "DefaultLevel": "0",
        "UserFields": "F2,F3,F4,F5,F26,F18,F19,F20,",
        "FieldLabels": "TLGrain=دسته محصول,TLOrder=نام محصول,TLType=fcfffff,F2=نام قطعه,F3=بارکد,F4=نوار طول 1,F5=نوار طول 2,F26=نوار عرض1,F18=نوار عرض 2,F19=تحویل به,F20=نام مشتری,"
    })

    for material, tasks in tasks_by_material.items():
        # نام نوع ورق (مثلاً "gerdo-gerdo-gerdo-1") - می‌توانید از material.name یا فیلد دیگری استفاده کنید
        material_type = material.name.replace(' ', '-')  # یا هر منطق دلخواه

        data = ET.SubElement(project, f"{{{NS}}}Data", {
            "Class": "3",
            "TotalUnit": "1000000",
            "Type": material_type,
            "Ply": str(material.thickness)
        })

        objective = ET.SubElement(data, f"{{{NS}}}Objective", {"Type": "Shape", "Count": str(len(tasks))})

        for idx, task in enumerate(tasks, start=1):
            part = task.part
            # پیدا کردن OrderItem مربوطه برای گرفتن نام محصول و مشتری
            order_item = order.items.filter(product__bom__part=part).first()
            product_name = order_item.product.name if order_item else ""
            product_category = order_item.product.category if order_item else ""
            customer_name = order.user.username if order.user.username else ""

            shape = ET.SubElement(objective, f"{{{NS}}}Shape", {
                "Name": f"P{idx:03d}",
                "X": str(part.length),
                "Y": str(part.width),
                "Turn": "true" if part.turn else "false",
                "Grain": product_category or "",
                "Order": product_name,   
                "Count": str(task.quantity),
                "F2": part.f2 or part.name,
                "F3": part.f3 or "",
                "F4": part.f4 or "",
                "F5": part.f5 or "",
                "F26": part.f26 or "",
                "F18": part.f18 or "",
                "F19": part.routing_code or "",
                "F20": customer_name or "",
            })

    # تبدیل به رشته XML زیبا
    xml_str = ET.tostring(root, encoding='utf-16', method='xml')
    # minidom برای فرمت زیبا (اختیاری)
    # dom = minidom.parseString(xml_str)
    # pretty_xml = dom.toprettyxml(indent="  ")

    response = HttpResponse(xml_str, content_type='application/xml')
    response['Content-Disposition'] = f'attachment; filename="order_{order.id}_autocut.xml"'
    return response


@login_required
@staff_or_representative_required
def export_multiple_autocut(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    order_ids = request.POST.getlist('order_ids')
    if not order_ids:
        messages.error(request, "هیچ سفارشی انتخاب نشده است.")
        return redirect('order_list')

    orders = get_list_or_404(Order, pk__in=order_ids)

    # جمع‌آوری تمام تسک‌های برش (pending) برای سفارشات انتخاب‌شده
    cut_tasks = ProductionTask.objects.filter(
        order__in=orders,
        station_name='cut',
        status='pending'
    ).select_related('part', 'part__material', 'order', 'order__customer')

    if not cut_tasks.exists():
        messages.warning(request, "هیچ قطعه‌ای در انتظار برش برای سفارشات انتخاب‌شده یافت نشد.")
        return redirect('order_list')

    # گروه‌بندی بر اساس متریال
    tasks_by_material = {}
    for task in cut_tasks:
        material = task.part.material
        if material not in tasks_by_material:
            tasks_by_material[material] = []
        tasks_by_material[material].append(task)

    # ایجاد XML
    NS = "http://www.King-stone.com"
    ET.register_namespace('', NS)
    root = ET.Element(f"{{{NS}}}AutoCUT", {"ver": "500"})

    project = ET.SubElement(root, f"{{{NS}}}Project", {
        "Name": "MultipleOrders",
        "Selected": "0",
        "Update": "0",
        "DefaultLevel": "0",
        "UserFields": "F2,F3,F4,F5,F26,F18,F19,F20,",
        "FieldLabels" : "TLGrain=دسته محصول,TLOrder=نام محصول,TLType=fcfffff,F2=نام قطعه,F3=بارکد,F4=نوار طول 1,F5=نوار طول 2,F26=نوار عرض1,F18=نوار عرض 2,F19=تحویل به,F20=نام مشتری,"
        # "FieldLabels": "TLGrain=دسته محصول,TLOrder=شماره سفارش,TLType=fcfffff,F2=نام قطعه,F3=بارکد,F4=نوار طول 1,F5=نوار طول 2,F26=نوار عرض1,F18=نوار عرض 2,F19=تحویل به,F20=نام مشتری,"
    })

    shape_counter = 1
    for material, tasks in tasks_by_material.items():
        material_type = material.name.replace(' ', '-')
        data = ET.SubElement(project, f"{{{NS}}}Data", {
            "Class": "3",
            "TotalUnit": "1000000",
            "Type": material_type,
            "Ply": str(material.thickness)
        })

        objective = ET.SubElement(data, f"{{{NS}}}Objective", {
            "Type": "Shape",
            "Count": str(len(tasks))
        })

        for task in tasks:
            part = task.part
            order = task.order
            # پیدا کردن OrderItem مربوطه برای گرفتن نام محصول و مشتری
            order_item = order.items.filter(product__bom__part=part).first()
            product_name = order_item.pname if order_item else ""
            product_category = order_item.grain if order_item else ""
            customer_name = order.user.username if order.user.username else ""
            print( part.pname)
            
            shape = ET.SubElement(objective, f"{{{NS}}}Shape", {
                "Name":  f"P{shape_counter:03d}",
                "X": str(part.length),
                "Y": str(part.width),
                "Turn": "true" if part.turn else "false",
                # "Grian": product_category or "",
                # "Order": product_name or "",  
                "Grain": part.grain or product_category or "",
                "Order": part.pname,    
                "Count": str(task.quantity),
                "F2": part.f2 or part.name,
                "F3": part.f3 or "",
                "F4": part.f4 or "",
                "F5": part.f5 or "",
                "F26": part.f26 or "",
                "F18": part.f18 or "",
                "F19": part.routing_code or "",
                "F20": customer_name or "",
            })
            shape_counter += 1

    xml_str = ET.tostring(root, encoding='utf-16', method='xml')

    # *** به‌روزرسانی تسک‌ها با save() برای فعال‌سازی مرحله بعد ***
    with transaction.atomic():
        updated_count = 0
        for task in cut_tasks:
            task.status = 'done'
            task.scanned_by = request.user
            task.save()   # این متد مرحله بعد را فعال و وضعیت سفارش را به‌روز می‌کند
            updated_count += 1

    messages.success(
        request,
        f"فایل برش با موفقیت ایجاد و {updated_count} قطعه به‌عنوان انجام‌شده ثبت گردید. "
        "مراحل بعدی به‌طور خودکار فعال شدند."
    )

    response = HttpResponse(xml_str, content_type='application/xml')
    response['Content-Disposition'] = 'attachment; filename="batch_autocut.xml"'
    return response





# -------------------------------------------------------------------
#      
# -------------------------------------------------------------------
@login_required
@admin_or_manager_required
def upload_form(request):
    if request.method == 'POST':
        file = request.FILES.get('excel_file')
        if not file:
            messages.error(request, "فایلی انتخاب نشده است.")
            return redirect('upload_form')

        try:
            df = pd.read_excel(file)
        except Exception as e:
            messages.error(request, f"خطا در خواندن فایل: {e}")
            return redirect('upload_form')

        saved = 0
        for idx, row in df.iterrows():
            try:
                with transaction.atomic():
                    username = str(row.get('نام', '')).strip()
                    if not username:
                        username = f"user_{idx}"
                    user, _ = User.objects.get_or_create(username=username)

                    customer_name = str(row.get('مشتری', '')).strip()
                    if not customer_name:
                        customer_name = f"{idx}"
                    customer, _ = Customer.objects.get_or_create(
                        user=user,
                        name=customer_name
                    )
                    order_id = int(row.get('شماره'))
                    order, _ = Order.objects.get_or_create(
                        id=order_id,
                        defaults={'user': user, 'customer': customer }
                    )
                    category, _ = ProductCategory.objects.get_or_create(name=str(row.get('گروه محصول', '')).strip())
                    size_val = str(row.get('اندازه', ''))
                    if size_val in ['nan', 'استاندارد']:
                        size_val = ''
                    product, _ = Product.objects.get_or_create(
                        category=category,
                        name=str(row.get('محصول', '')).strip(),
                        # default_size=size_val
                    )
                    order_item = OrderItem.objects.create(
                        order=order,
                        id=idx+1,
                        product=product,
                        quantity=int(row.get('تعداد', 1)),
                        size=size_val,
                        notes=str(row.get('توضیحات', ''))
                    )

                    # رنگ‌ها
                    color_parts = ['بدنه', 'درب', 'دستگیره', 'پایه', 'صفحه']
                    for part in color_parts:
                        code = str(row.get(part, 'nan'))
                        if code and code != 'nan':
                            Color.objects.create(
                                part=part,
                                code=code.split('.')[0],
                                orderitem=order_item
                            )
                    saved += 1
            except Exception as e:
                logger.exception(f"خطا در ردیف {idx}: {e}")
                messages.error(request, f"خطا در ردیف {idx+1}: {e}")
        messages.success(request, f'{saved} سفارش با موفقیت ذخیره شد.')
        return redirect('upload_form')

    return render(request, 'upload.html')


@login_required
@admin_or_manager_required
def create_order(request):
    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.user = request.user
            order.save()
            messages.success(request, f'سفارش #{order.id} ایجاد شد.')
            return redirect('add_item', order_id=order.id)
    else:
        form = OrderForm()
    return render(request, 'create_order.html', {'form': form})


@login_required
@admin_or_manager_required
def add_item(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        form = OrderItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.order = order
            item.save()
            messages.success(request, 'آیتم اضافه شد.')
            return redirect('add_colors', item_id=item.id)
    else:
        form = OrderItemForm()
    return render(request, 'orders/add_item.html', {'form': form, 'order': order})


@login_required
@admin_or_manager_required
def add_colors(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id)
    if request.method == 'POST':
        parts = ['بدنه', 'درب', 'پایه', 'دستگیره', 'صفحه']
        for part in parts:
            form = ColorForm(request.POST, prefix=part)
            if form.is_valid():
                color = form.save(commit=False)
                color.orderitem = item
                color.part = part
                color.save()
        messages.success(request, 'رنگ‌ها ثبت شد.')
        return redirect('order_list')
    else:
        color_forms = [ColorForm(prefix=p) for p in ['بدنه', 'درب', 'پایه', 'دستگیره', 'صفحه']]
    return render(request, 'orders/add_colors.html', {'item': item, 'color_forms': color_forms})

@login_required
@admin_or_manager_required
def create_complete_order(request):
    if request.method == 'POST':
        form = CompleteOrderForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                customer, _ = Customer.objects.get_or_create(name=form.cleaned_data['customer_name'])
                category, _ = ProductCategory.objects.get_or_create(name=form.cleaned_data['category_name'])
                product = Product.objects.create(
                    category=category,
                    name=form.cleaned_data['product_name'],
                    size=form.cleaned_data['size']
                )
                order = Order.objects.create(user=request.user, customer=customer)
                order_item = OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=form.cleaned_data['quantity'],
                    notes=form.cleaned_data['notes'],
                    size=form.cleaned_data['size']
                )
                colors_data = [
                    ('بدنه', form.cleaned_data['rang_bazne']),
                    ('درب', form.cleaned_data['rang_darb']),
                    ('پایه', form.cleaned_data['rang_paye']),
                    ('دستگیره', form.cleaned_data['rang_dastgire']),
                ]
                for part, code in colors_data:
                    if code:
                        Color.objects.create(part=part, code=code, orderitem=order_item)
            messages.success(request, f'سفارش #{order.id} کامل ایجاد شد.')
            return redirect('order_list')
    else:
        form = CompleteOrderForm()
    return render(request, 'create_complete.html', {'form': form})








# -------------------------------------------------------------------
#      اسکن قطعات
# -------------------------------------------------------------------
@login_required
@staff_or_representative_required
def scan_part(request):
    # بررسی پروفایل کاربر
    if not hasattr(request.user, 'workerprofile'):
        messages.error(request, "")
        return redirect('dashboard')

    worker_stage = request.user.workerprofile.stage
    pending_tasks = ProductionTask.objects.filter(
        station_name=worker_stage,
        status='pending'
    ).select_related('part', 'order').order_by('order__created_at')

    if request.method == 'POST':
        barcode = request.POST.get('barcode', '').strip()
        task_id = request.POST.get('task_id')

        if task_id:
            # تکمیل دستی تسک
            task = get_object_or_404(pending_tasks, id=task_id)
            with transaction.atomic():
                task.status = 'done'
                task.scanned_by = request.user
                task.save()

            # اگر ایستگاه CNC است، فایل را برای دانلود آماده کن
            if worker_stage == 'cnc':
                # حذف .itemX از f3 برای یافتن فایل فیزیکی
                file_barcode = re.sub(r'\.item\d+$', '', task.part.f3)
                download_url = reverse('download_cnc_file', args=[file_barcode])
                messages.success(request, f"تسک '{task.part.name}' تکمیل شد. دریافت فایل...")
                return redirect(download_url)
            
            if worker_stage == 'dr':
                file_barcode = re.sub(r'\.item\d+$', '', task.part.f3)
                download_url = reverse('download_dr_file', args=[file_barcode])
                messages.success(request, f" '{task.part.name}' تکمیل شد. دریافت فایل سوراخکاری...")
                return redirect(download_url)
            
            messages.success(request, f" قطعه '{task.part.name}' با موفقیت تکمیل شد.")
            return redirect('scan_part')



        if barcode and worker_stage == 'cnc':
            # اسکن بارکد (برای ایستگاه‌های غیر CNC مستقیماً در همین ویو پردازش می‌شود)
            # (برای CNC فرم به scan_part_cnc ارسال می‌شود)
            clean_barcode = re.sub(r'\.cnc$', '', barcode, flags=re.IGNORECASE)
            try:
                part = Part.objects.get(f3=clean_barcode)
            except Part.DoesNotExist:
                messages.error(request, f"قطعه‌ای با بارکد '{barcode}' یافت نشد.")
                return redirect('scan_part')

            task = pending_tasks.filter(part=part).first()
            if not task:
                messages.error(request, f"هیچ  در انتظاری برای قطعه '{part.name}' در ایستگاه شما یافت نشد.")
                return redirect('scan_part')

            with transaction.atomic():
                task.status = 'done'
                task.scanned_by = request.user
                task.save()

            messages.success(request, f"قطعه '{part.name}' (بارکد: {barcode}) تکمیل شد.")
            return redirect('scan_part')

        messages.error(request, "لطفاً بارکد را وارد کنید یا یکی از قطعه را انتخاب نمایید.")
        return redirect('scan_part')

    # GET request
    stage_display = dict(STATION_CHOICES).get(worker_stage, worker_stage)
    context = {
        'pending_tasks': pending_tasks,
        'worker_stage': worker_stage,
        'stage_display': stage_display,
    }
    return render(request, 'scan_part.html', context)


@login_required
@staff_or_representative_required
def scan_part_cnc(request):
    """
    اسکن قطعه در ایستگاه CNC (AJAX):
    - تکمیل تسک CNC
    - دانلود خودکار فایل برنامه
    """
    if request.method != 'POST':
        return redirect('scan_part')

    barcode = request.POST.get('barcode', '').strip()
    if not barcode:
        messages.error(request, "لطفاً بارکد قطعه را وارد کنید.")
        return redirect('scan_part')

    # حذف پسوند .cnc احتمالی
    clean_barcode = re.sub(r'\.cnc$', '', barcode, flags=re.IGNORECASE)
    part = Part.objects.filter(f3=clean_barcode).first()
    if not part:
        messages.error(request, f"قطعه‌ای با بارکد '{barcode}' یافت نشد.")
        return redirect('scan_part')

    if not hasattr(request.user, 'workerprofile'):
        messages.error(request, "پروفایل کاری شما تعریف نشده است.")
        return redirect('dashboard')

    worker_stage = request.user.workerprofile.stage
    if worker_stage != 'cnc':
        messages.error(request, "شما مجاز به اسکن در ایستگاه CNC نیستید.")
        return redirect('dashboard')

    task = ProductionTask.objects.filter(
        part=part,
        station_name='cnc',
        status='pending'
    ).first()

    if not task:
        messages.error(request, f"هیچ  در انتظاری برای قطعه '{part.name}' در ایستگاه CNC یافت نشد.")
        return redirect('scan_part')

    with transaction.atomic():
        task.status = 'done'
        task.scanned_by = request.user
        task.save()

    # آماده‌سازی فایل
    source_dir = getattr(settings, 'CNC_SOURCE_DIR', '')
    extension = getattr(settings, 'CNC_FILE_EXTENSION', '.cnc')

    # حذف .itemX از f3 برای یافتن فایل فیزیکی
    file_barcode = re.sub(r'\.item\d+$', '', part.f3)
    filename = f"{file_barcode}{extension}"
    file_path = os.path.join(source_dir, filename)

    if not os.path.exists(file_path):
        messages.warning(
            request,
            f"✅ تسک CNC تکمیل شد، اما فایل '{filename}' در سرور یافت نشد."
        )
        return redirect('scan_part')

    with open(file_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['X-CNC-Status'] = 'success'
        return response

@login_required
@staff_or_representative_required
def download_cnc_file(request, barcode):
    """
    دانلود فایل CNC با بارکد داده شده.
    بارکد می‌تواند شامل .itemX باشد یا نباشد؛ جستجوی قطعه با startswith انجام می‌شود.
    """
    clean_barcode = re.sub(r'\.cnc$', '', barcode, flags=re.IGNORECASE)

    # یافتن قطعه‌ای که f3 آن با این بارکد شروع شود
    part = Part.objects.filter(f3__startswith=clean_barcode).first()
    if not part:
        raise Http404(f"قطعه‌ای با بارکد '{barcode}' یافت نشد.")

    # حذف .itemX برای ساخت نام فایل
    file_barcode = re.sub(r'\.item\d+$', '', clean_barcode)
    source_dir = getattr(settings, 'CNC_SOURCE_DIR', '')
    extension = getattr(settings, 'CNC_FILE_EXTENSION', '.cnc')
    filename = f"{file_barcode}{extension}"
    file_path = os.path.join(source_dir, filename)

    if not os.path.exists(file_path):
        raise Http404(f"فایل CNC با نام '{filename}' یافت نشد.")

    with open(file_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

@login_required
@staff_or_representative_required
def scan_part_dr(request):
    """
    اسکن قطعه در ایستگاه سوراخکاری (dr):
    - تکمیل تسک
    - دانلود خودکار فایل XML
    """
    if request.method != 'POST':
        return redirect('scan_part')

    barcode = request.POST.get('barcode', '').strip()
    if not barcode:
        messages.error(request, "لطفاً بارکد قطعه را وارد کنید.")
        return redirect('scan_part')

    # حذف پسوند احتمالی
    clean_barcode = re.sub(r'\.(scx)$', '', barcode, flags=re.IGNORECASE)
    part = Part.objects.filter(f3=clean_barcode).first()
    if not part:
        messages.error(request, f"قطعه‌ای با بارکد '{barcode}' یافت نشد.")
        return redirect('scan_part')

    if not hasattr(request.user, 'workerprofile'):
        messages.error(request, "پروفایل کاری شما تعریف نشده است.")
        return redirect('dashboard')

    worker_stage = request.user.workerprofile.stage
    if worker_stage != 'dr':
        messages.error(request, "شما مجاز به اسکن در ایستگاه سوراخکاری نیستید.")
        return redirect('dashboard')

    task = ProductionTask.objects.filter(
        part=part,
        station_name='dr',
        status='pending'
    ).first()

    if not task:
        messages.error(request, f"هیچ  در انتظاری برای قطعه '{part.name}' در ایستگاه سوراخکاری یافت نشد.")
        return redirect('scan_part')

    with transaction.atomic():
        task.status = 'done'
        task.scanned_by = request.user
        task.save()

    # آماده‌سازی فایل XML
    source_dir = getattr(settings, 'DR_SOURCE_DIR', '')
    extension = getattr(settings, 'DR_FILE_EXTENSION', '.scx')

    # حذف .itemX از f3 برای یافتن فایل فیزیکی
    file_barcode = re.sub(r'\.item\d+$', '', part.f3)
    filename = f"{file_barcode}{extension}"
    file_path = os.path.join(source_dir, filename)

    if not os.path.exists(file_path):
        messages.warning(
            request,
            f"✅  سوراخکاری تکمیل شد، اما فایل '{filename}' در سرور یافت نشد."
        )
        return redirect('scan_part')

    with open(file_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/xml')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['X-DR-Status'] = 'success'
        return response

@login_required
@staff_or_representative_required
def download_dr_file(request, barcode):
    """
    دانلود فایل XML سوراخکاری با بارکد داده شده.
    """
    clean_barcode = re.sub(r'\.(scx)$', '', barcode, flags=re.IGNORECASE)

    part = Part.objects.filter(f3__startswith=clean_barcode).first()
    if not part:
        raise Http404(f"قطعه‌ای با بارکد '{barcode}' یافت نشد.")

    file_barcode = re.sub(r'\.item\d+$', '', clean_barcode)
    source_dir = getattr(settings, 'DR_SOURCE_DIR', '')
    extension = getattr(settings, 'DR_FILE_EXTENSION', '.xml')
    filename = f"{file_barcode}{extension}"
    file_path = os.path.join(source_dir, filename)

    if not os.path.exists(file_path):
        raise Http404(f"فایل سوراخکاری با نام '{filename}' یافت نشد.")

    with open(file_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/xml')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        # response['Content-Disposition'] = f'attachment; filename="{barcode}"'
       
        return response


# -------------------------------------------------------------------
#     گزارش  تولید
# -------------------------------------------------------------------

@login_required
@admin_or_manager_required
@staff_or_representative_required
def report_orders(request):
    data = Order.objects.values('status').annotate(count=Count('id'))
    return render(request, 'reports/orders.html', {'data': data})


@login_required
@staff_or_representative_required
def report_stages(request):
    # ---------- base queryset ----------
    base_items = OrderItem.objects.select_related(
        'order__user', 'product__category'
    ).prefetch_related(
        'logs', 'packaging_units'
    )

    # ---------- text search ----------
    q = request.GET.get('q')
    if q:
        base_items = base_items.filter(
            Q(order__id__icontains=q) |
            Q(product__name__icontains=q) |
            Q(order__customer__name__icontains=q) |
            Q(order__user__username__icontains=q)
        )

    # ---------- filters ----------
    representative_id = request.GET.get('representative')
    if representative_id:
        base_items = base_items.filter(order__user_id=representative_id)

    category_id = request.GET.get('category')
    if category_id:
        base_items = base_items.filter(product__category_id=category_id)

    product_id = request.GET.get('product')
    if product_id:
        base_items = base_items.filter(product_id=product_id)

    date_from = request.GET.get('date_from')
    if date_from:
        base_items = base_items.filter(order__created_at__gte=date_from)

    date_to = request.GET.get('date_to')
    if date_to:
        base_items = base_items.filter(order__created_at__lte=date_to)

    # ---------- summary (based on filtered base_items before stage/pack/ship filters) ----------
    total = base_items.count()
    summary = {}
    for code, name in STATION_CHOICES:
        done_count = base_items.filter(logs__stage=code).distinct().count()
        summary[code] = {'name': name, 'done': done_count, 'total': total}

    # ---------- stage filters (excluding packaging & shipping) ----------
    stage_pending = request.GET.get('stage_pending')
    stage_done = request.GET.get('stage_done')
    items = base_items
    if stage_pending and stage_pending in dict(STATION_CHOICES):
        items = items.exclude(logs__stage=stage_pending)
    if stage_done and stage_done in dict(STATION_CHOICES):
        items = items.filter(logs__stage=stage_done)

    # ---------- packaging / shipping filters ----------
    packaging_status = request.GET.get('packaging_status')
    shipping_status = request.GET.get('shipping_status')

    # We'll build annotations using subqueries for precise calculations
    pack_units = PackagingUnit.objects.filter(order_item=OuterRef('pk'))
    ship_units = PackagingUnit.objects.filter(order_item=OuterRef('pk'))

    items = items.annotate(
        total_units=Count('packaging_units'),
        packed_count=Subquery(
            pack_units.filter(is_packed=True).values('order_item')
            .annotate(cnt=Count('id')).values('cnt'),
            output_field=IntegerField()
        ),
        shipped_count=Subquery(
            ship_units.filter(is_shipped=True).values('order_item')
            .annotate(cnt=Count('id')).values('cnt'),
            output_field=IntegerField()
        ),
    )

    # Apply packaging filter
    if packaging_status == 'done':
        items = items.filter(total_units__gt=0, packed_count__gte=F('total_units'))
    elif packaging_status == 'pending':
        items = items.filter(total_units__gt=0, packed_count__lt=F('total_units'))
    elif packaging_status == 'none':
        items = items.filter(total_units=0)

    # Apply shipping filter
    if shipping_status == 'done':
        items = items.filter(total_units__gt=0, shipped_count__gte=F('total_units'))
    elif shipping_status == 'pending':
        items = items.filter(total_units__gt=0, shipped_count__lt=F('total_units'))
    elif shipping_status == 'none':
        items = items.filter(total_units=0)

    # ---------- build report data ----------
    items = items.order_by('-id')
    report_data = []
    for item in items:
        stage_status = {}
        for code, name in STATION_CHOICES:
            log = item.logs.filter(stage=code).first()
            if log and log.created_at:
                jdate = log.created_at
                stage_status[code] = f"{jdate.month:02d}/{jdate.day:02d}"
            else:
                stage_status[code] = None

        # total_units is already annotated, but we also have the actual attributes from the model
        total_units = item.packaging_units.count()
        packed_units = item.packaging_units.filter(is_packed=True).count()
        shipped_units = item.packaging_units.filter(is_shipped=True).count()
        items = items.order_by('-id')

        report_data.append({
            'item': item,
            'stage_status': stage_status,
            'total_units': total_units,
            'packed_units': packed_units,
            'shipped_units': shipped_units,
            'representative': item.order.user.get_full_name() or item.order.user.username,
            'category_name': item.product.category.name,
        })

    # ---------- dropdown lists ----------
    representatives = User.objects.filter(order__isnull=False).distinct().order_by('username')
    categories = ProductCategory.objects.all()
    if category_id:
        products = Product.objects.filter(category_id=category_id).order_by('name')
    else:
        products = Product.objects.none()

    context = {
        'report_data': report_data,
        'station_choices': STATION_CHOICES,
        'summary': summary,
        'search_query': q,
        'representatives': representatives,
        'categories': categories,
        'products': products,
        'selected_representative': representative_id,
        'selected_category': category_id,
        'selected_product': product_id,
        'date_from': date_from,
        'date_to': date_to,
        'stage_pending': stage_pending,
        'stage_done': stage_done,
        'packaging_status': packaging_status or '',
        'shipping_status': shipping_status or '',
    }
    return render(request, 'reports/stages.html', context)


@login_required
@admin_or_manager_required
@staff_or_representative_required
def report_workers(request):
    data = ProductionLog.objects.values('user__username').annotate(count=Count('id'))
    return render(request, 'reports/workers.html', {'data': data})


@login_required
@admin_or_manager_required
@staff_or_representative_required
def delayed_orders(request):
    limit = timezone.now() - timedelta(days=3)
    orders = Order.objects.filter(created_at__lt=limit).exclude(status='completed')
    return render(request, 'reports/delayed.html', {'orders': orders})





# -------------------------------------------------------------------
#      ثبت  سفارش
# -------------------------------------------------------------------

@login_required
@admin_or_manager_required
def create_order_step1(request):
    form = OrderCustomerForm(user=request.user)
    if request.method == 'POST':
        form = OrderCustomerForm(request.POST, user=request.user)
        if form.is_valid():
            # تعیین نماینده (کاربر مسئول سفارش)
            if form.is_admin and form.cleaned_data.get('representative'):
                representative = form.cleaned_data['representative']
            else:
                representative = request.user

            customer = form.cleaned_data['customer']
            if not customer:
                # ایجاد مشتری جدید
                customer = Customer.objects.create(
                    user=representative,  # نماینده مسئول این مشتری
                    name=form.cleaned_data['new_customer_name'],
                    phone=form.cleaned_data['new_customer_phone'],
                    address=form.cleaned_data['new_customer_address']
                )
            # ایجاد سفارش
            order = Order.objects.create(
                user=representative,
                customer=customer,
                # number = customer.phone,
                number=form.cleaned_data.get('number', ''),   # ← مقدار امن
                status='draft'
            )
            messages.success(request, f"سفارش شماره {order.id} برای مشتری {customer.name} (نماینده: {representative.username}) ایجاد شد.")
            return redirect('create_order_step2', order_id=order.id)
    return render(request, 'orders/create_step1.html', {'form': form, 'is_admin': form.is_admin})


@login_required
@staff_or_representative_required
def ajax_load_customers(request):
    """بارگذاری مشتریان بر اساس نماینده انتخاب‌شده (برای ادمین)"""
    user_id = request.GET.get('representative')
    if user_id:
        customers = Customer.objects.filter(user_id=user_id).order_by('name')
    else:
        customers = Customer.objects.none()
    data = [{'id': c.id, 'name': c.name} for c in customers]
    return JsonResponse(data, safe=False)


@login_required
@admin_or_manager_required
def create_order_step2(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    existing_items = order.items.select_related('product__category').prefetch_related('ordercolor')

    if request.method == 'POST':
        item_form = OrderItemForm(request.POST)
        color_form = ColorSelectionForm(request.POST)
        if item_form.is_valid() and color_form.is_valid():
            with transaction.atomic():
                # دریافت محصول از فرم‌ معتبر
                product = item_form.cleaned_data['product']
                order_item = item_form.save(commit=False)
                order_item.order = order
                order_item.product = product          # ← حالا product تعریف شده است
                order_item.unit_price = product.base_price
                order_item.save()

                for part_value, _ in Color.PART_CHOICES:
                    code = color_form.cleaned_data.get(f'color_{part_value}')
                    if code:
                        Color.objects.create(
                            part=part_value,
                            code=code,
                            orderitem=order_item
                        )
                messages.success(request, f"آیتم '{order_item.product.name}' به سفارش اضافه شد.")
                if 'add_another' in request.POST:
                    return redirect('create_order_step2', order_id=order.id)
                else:
                    return redirect('order_list')
        else:
            for field, errors in item_form.errors.items():
                for error in errors:
                    messages.error(request, f"خطا در {field}: {error}")
            for field, errors in color_form.errors.items():
                for error in errors:
                    messages.error(request, f"خطا در رنگ‌ها: {error}")
    else:
        item_form = OrderItemForm()
        color_form = ColorSelectionForm()

    context = {
        'order': order,
        'item_form': item_form,
        'color_form': color_form,
        'existing_items': existing_items,
    }
    return render(request, 'orders/create_step2.html', context)


@login_required
def ajax_load_products(request):
    """بارگذاری محصولات بر اساس دسته برای فیلترهای وابسته"""
    category_id = request.GET.get('category')
    if category_id:
        products = Product.objects.filter(category_id=category_id).order_by('name')
    else:
        products = Product.objects.none()
    data = [{'id': p.id, 'name': str(p)} for p in products]
    return JsonResponse(data, safe=False)


@login_required
@staff_or_representative_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related(
            'items__product__category',
            'items__ordercolor',
            'items__logs'   # اضافه کردن prefetch برای logs
        ),
        id=order_id
    )
    
    # محاسبه وضعیت مراحل برای هر آیتم
    for item in order.items.all():
        log_stages = set(item.logs.values_list('stage', flat=True))
        item.stages = {stage: (stage in log_stages) for stage, _ in STATION_CHOICES}
    
    context = {
        'order': order,
        'station_choices': STATION_CHOICES,  # برای استفاده در سربرگ جدول
    }
    return render(request, 'orders/order_detail.html', context)




def ajax_load_product_colors(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    raw_value = product.default_colors

    # ۱. اگر خودش دیکشنری است
    if isinstance(raw_value, dict):
        defaults = raw_value

    # ۲. اگر رشته است
    elif isinstance(raw_value, str):
        # ابتدا تلاش با json.loads (برای رشته‌های معتبر JSON)
        try:
            defaults = json.loads(raw_value)
        except json.JSONDecodeError:
            # اگر ناموفق بود، با ast.literal_eval تلاش کن (برای رشته‌های شبیه پایتون)
            try:
                defaults = ast.literal_eval(raw_value)
            except (ValueError, SyntaxError):
                logger.warning(f"Cannot parse default_colors for product {product_id}: {raw_value}")
                defaults = {}

        # اطمینان از اینکه نتیجه یک دیکشنری باشد
        if not isinstance(defaults, dict):
            defaults = {}
    else:
        defaults = {}

    return JsonResponse({'defaults': defaults})





# -------------------------------------------------------------------
#     ویراش  محصولات 
# -------------------------------------------------------------------

@login_required
@admin_or_manager_required
def product_bom_edit(request, product_id):
    product = get_object_or_404(Product, pk=product_id)

    # قطعاتی که در BOM این محصول استفاده شده‌اند
    part_qs = Part.objects.filter(productbom__product=product).distinct()

    PartFormSet = modelformset_factory(
        Part,
        form=PartForm,
        extra=0,
        can_delete=False
    )

    BOMFormSet = inlineformset_factory(
        Product,
        ProductBOM,
        fields=[
            'part', 'quantity', 'color_part',
            'allow_material_override', 'color_material_map',
            'size_affected', 'size_adjustment_rule',
        ],
        widgets={
            'color_material_map': forms.Textarea(attrs={'rows': 2, 'class': 'form-control form-control-sm'}),
            'size_adjustment_rule': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        },
        extra=0,               # ← دیگر ردیف خالی اضافه نمی‌شود
        can_delete=True,
    )

    if request.method == 'POST':
        part_formset = PartFormSet(request.POST, prefix='parts', queryset=part_qs)
        bom_formset = BOMFormSet(request.POST, prefix='bom', instance=product)

        if part_formset.is_valid() and bom_formset.is_valid():
            part_formset.save()
            bom_formset.save()
            messages.success(request, '✅ اطلاعات با موفقیت ذخیره شد.')
            return redirect('product_bom_edit', product_id=product.id)
        else:
            # نمایش خطاها برای عیب‌یابی
            messages.error(request, '⚠️ خطا در ذخیره‌سازی. لطفاً فیلدها را بررسی کنید.')
            print("Part formset errors:", part_formset.errors)
            print("BOM formset errors:", bom_formset.errors)
    else:
        part_formset = PartFormSet(prefix='parts', queryset=part_qs)
        bom_formset = BOMFormSet(prefix='bom', instance=product)

    context = {
        'product': product,
        'part_formset': part_formset,
        'bom_formset': bom_formset,
    }
    return render(request, 'product_bom_edit.html', context)



@login_required
@admin_or_manager_required
def admin_product_list(request):
    products = Product.objects.select_related('category').all()
    categories = ProductCategory.objects.all()

    # جستجو
    q = request.GET.get('q')
    if q:
        products = products.filter(name__icontains=q)

    # فیلتر دسته‌بندی
    category_id = request.GET.get('category')
    if category_id:
        products = products.filter(category_id=category_id)

    context = {
        'products': products,
        'categories': categories,
        'selected_category': category_id,
        'search_query': q,
    }
    return render(request, 'admin_product_list.html', context)





# -------------------------------------------------------------------
#      خروجی اکسل از دیتا بیس (به‌روز شده با مدل‌های جدید)
# -------------------------------------------------------------------

MODEL_ORDER = [
    'ProductCategory',
    'Material',
    'Customer',
    'WorkerProfile',
    'Product',
    'Part',
    'ProductBOM',
    'Order',
    'OrderItem',
    'Color',
    'ProductionTask',
    'ProductionLog',
    'PackagingUnit',      # جدید
]

def get_model_by_name(name):
    for model in apps.get_app_config('product').get_models():
        if model.__name__ == name:
            return model
    return None


def _gregorian_to_shamsi_str(g_date):
    """تبدیل یک datetime.date میلادی (یا jdatetime.date) به رشته YYYY-MM-DD شمسی"""
    if isinstance(g_date, jdatetime.date):
        return g_date.strftime('%Y-%m-%d')
    if hasattr(g_date, 'year'):
        try:
            return jdatetime.date.fromgregorian(date=g_date).strftime('%Y-%m-%d')
        except:
            return ''
    return str(g_date)


def convert_dates_for_import(model, data):
    for field in model._meta.get_fields():
        if isinstance(field, (models.DateField, models.DateTimeField)):
            col = field.name
            if col not in data:
                continue

            val = data[col]
            is_datetime = isinstance(field, models.DateTimeField)

            # ۱. None/NaN → تاریخ امروز
            if val is None or (isinstance(val, float) and math.isnan(val)):
                if is_datetime:
                    data[col] = dt.datetime.now()
                else:
                    data[col] = jdatetime.date.today()
                continue

            # ۲. رشته
            if isinstance(val, str):
                stripped = val.strip()
                if stripped:
                    try:
                        if is_datetime:
                            # فرض می‌کنیم رشته‌ها میلادی هستند (مثل خروجی قبلی)
                            # در غیر این صورت می‌توانید _parse_shamsi_date و سپس تبدیل کنید
                            data[col] = dt.datetime.fromisoformat(stripped)
                        else:
                            # رشته شمسی → jdatetime.date
                            data[col] = _parse_shamsi_date(stripped)
                    except Exception:
                        data[col] = dt.datetime.now() if is_datetime else jdatetime.date.today()
                else:
                    data[col] = dt.datetime.now() if is_datetime else jdatetime.date.today()
                continue

            # ۳. عدد (سریال تاریخ اکسل)
            if isinstance(val, (int, float)):
                try:
                    base = dt.datetime(1899, 12, 30)
                    delta = dt.timedelta(days=int(val))
                    if isinstance(val, float) and val % 1 != 0:
                        delta += dt.timedelta(seconds=round((val % 1) * 86400))
                    greg = base + delta
                    if is_datetime:
                        data[col] = greg   # مستقیم datetime میلادی
                    else:
                        # تبدیل به jdatetime.date (برای PersianDateField)
                        data[col] = jdatetime.date.fromgregorian(date=greg.date())
                except Exception:
                    data[col] = dt.datetime.now() if is_datetime else jdatetime.date.today()
                continue

            # ۴. اشیاء Python date/datetime (ممکن است میلادی باشند)
            if isinstance(val, dt.date):
                try:
                    if isinstance(val, dt.datetime):
                        data[col] = val if is_datetime else jdatetime.date.fromgregorian(date=val.date())
                    else:  # فقط date
                        if is_datetime:
                            data[col] = dt.datetime.combine(val, dt.time.min)
                        else:
                            data[col] = jdatetime.date.fromgregorian(date=val)
                except Exception:
                    data[col] = dt.datetime.now() if is_datetime else jdatetime.date.today()
                continue

            # ۵. نوع غیرمنتظره → تاریخ امروز
            data[col] = dt.datetime.now() if is_datetime else jdatetime.date.today()
    return data


def convert_dates_for_export(model, df):
    """تاریخ‌های میلادی (DateField و DateTimeField) را به رشتهٔ شمسی مناسب تبدیل می‌کند"""
    for field in model._meta.get_fields():
        if isinstance(field, (models.DateField, models.DateTimeField)):
            col = field.name
            if col in df.columns:
                is_datetime = isinstance(field, models.DateTimeField)
                df[col] = df[col].apply(
                    lambda d: _gregorian_to_shamsi_str(d, is_datetime=is_datetime) if pd.notnull(d) else ''
                )
    return df


def _gregorian_to_shamsi_str(g_date, is_datetime=False):
    if isinstance(g_date, jdatetime.datetime):
        g_date = g_date.togregorian()
    if isinstance(g_date, jdatetime.date):
        g_date = g_date.togregorian()
    if isinstance(g_date, dt.datetime):
        return g_date.strftime('%Y-%m-%d %H:%M:%S') if is_datetime else g_date.strftime('%Y-%m-%d')
    if isinstance(g_date, dt.date):
        return g_date.strftime('%Y-%m-%d')
    return str(g_date)


def _parse_shamsi_date(date_str):
    """تبدیل رشته شمسی (YYYY-MM-DD یا YYYY/MM/DD) به jdatetime.date"""
    parts = re.split(r'[-/]', date_str.strip())
    if len(parts) == 3:
        try:
            y, m, d = map(int, parts)
            return jdatetime.date(y, m, d)
        except (ValueError, TypeError):
            pass
    # اگر نامعتبر بود، تاریخ امروز را برگردان
    return jdatetime.date.today()


def clean_data_for_model(model, data):
    NA_STRINGS = {'nan', 'none', 'null', 'na', ''}
    for field in model._meta.get_fields():
        if not field.is_relation and hasattr(field, 'null'):
            field_name = field.name
            if field_name not in data:
                continue
            value = data[field_name]

            # تبدیل float به int اگر عدد صحیح است
            if isinstance(value, float) and not math.isnan(value) and value == int(value):
                value = int(value)

            # تبدیل رشته‌های 'nan'/'none' به None
            if isinstance(value, str) and value.strip().lower() in NA_STRINGS:
                value = None
            elif isinstance(value, float) and math.isnan(value):
                value = None

            # **تاریخ و تاریخ-زمان: بعد از convert_dates_for_import، دیگر کاری نکنیم**
            if isinstance(field, (models.DateField, models.DateTimeField)):
                continue

            if value is None:
                if isinstance(field, (models.CharField, models.TextField)):
                    data[field_name] = ''
                elif isinstance(field, (models.IntegerField, models.DecimalField, models.FloatField)):
                    if field.has_default():
                        del data[field_name]
                    else:
                        data[field_name] = 0
                elif isinstance(field, models.JSONField):
                    data[field_name] = {}
                elif isinstance(field, models.BooleanField):
                    data[field_name] = False
                else:
                    if not field.null:
                        del data[field_name]
            else:
                if isinstance(field, models.CharField) and not isinstance(value, str):
                    data[field_name] = str(value)


def resolve_foreign_keys(model, data):
    for field in model._meta.get_fields():
        if field.is_relation and field.many_to_one:
            fk_attname = field.attname
            if fk_attname in data:
                fk_value = data[fk_attname]
                if fk_value is not None and not (isinstance(fk_value, float) and math.isnan(fk_value)):
                    related_model = field.related_model
                    try:
                        obj = related_model.objects.get(pk=int(fk_value))
                        data[field.name] = obj
                    except (related_model.DoesNotExist, ValueError, TypeError):
                        pass
                del data[fk_attname]




# -------------------------------------------------------------------
# ویوهای Export و Import
# -------------------------------------------------------------------
@login_required
@admin_or_manager_required
def export_all_data(request):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for model_name in MODEL_ORDER:
            model = get_model_by_name(model_name)
            if not model:
                continue
            queryset = model.objects.all()
            df = pd.DataFrame(list(queryset.values()))
            # حذف ستون‌های غیر ضروری
            for col in ['qr_code', 'image', 'password']:
                if col in df.columns:
                    df.drop(col, axis=1, inplace=True)
            # تبدیل تاریخ‌ها به شمسی
            df = convert_dates_for_export(model, df)
            df.to_excel(writer, sheet_name=model_name, index=False)

    output.seek(0)
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="selvi_all_data.xlsx"'
    return response

@login_required
@admin_or_manager_required
def import_data(request):
    if request.method == 'POST':
        file = request.FILES.get('excel_file')
        if not file:
            messages.error(request, 'فایلی انتخاب نشده است.')
            return redirect('import_data')

        try:
            xls = pd.ExcelFile(file)
            sheets_processed = 0
            for sheet_name in MODEL_ORDER:
                if sheet_name not in xls.sheet_names:
                    continue
                model = get_model_by_name(sheet_name)
                if not model:
                    continue

                df = pd.read_excel(file, sheet_name=sheet_name)
                df = df.where(pd.notnull(df), None)

                for _, row in df.iterrows():
                    data = row.to_dict()
                    data.pop('qr_code', None)
                    data.pop('image', None)

                    raw_id = data.pop('id', None)

                    # ۱. تبدیل تاریخ‌های شمسی به jdatetime
                    data = convert_dates_for_import(model, data)
                    # ۲. تمیزسازی عمومی
                    clean_data_for_model(model, data)
                    # ۳. کلیدهای خارجی
                    resolve_foreign_keys(model, data)

                    valid_id = None
                    if raw_id is not None:
                        if isinstance(raw_id, (int, float)):
                            if not math.isnan(raw_id):
                                valid_id = int(raw_id)
                        elif isinstance(raw_id, str):
                            raw_id = raw_id.strip()
                            if raw_id.lower() not in {'nan', 'none', 'null', ''}:
                                try:
                                    valid_id = int(float(raw_id))
                                except ValueError:
                                    pass

                    if valid_id is not None:
                        model.objects.update_or_create(id=valid_id, defaults=data)
                    else:
                        model.objects.create(**data)

                sheets_processed += 1

            messages.success(request, f'{sheets_processed} جدول با موفقیت پردازش شدند.')
        except Exception as e:
            import traceback
            logger.error("Import failed with traceback:")
            logger.error(traceback.format_exc())
            messages.error(request, f'خطا در پردازش فایل: {e}')

        return redirect('import_data')

    return render(request, 'import_data.html')






# -------------------------------------------------------------------
# اسکن بسته بندی
# -------------------------------------------------------------------

# views.py (بخش مربوط به scan_packaging_unit – جایگزین کامل)

@login_required
def scan_packaging_unit(request, pk):
    unit = get_object_or_404(PackagingUnit, pk=pk)
    worker_stage = request.user.workerprofile.stage if hasattr(request.user, 'workerprofile') else None
    next_url = request.GET.get('next', 'dashboard')

    # ==================================================================
    # فقط درخواست‌های POST پردازش شوند (حذف کامل GET/auto)
    # ==================================================================
    if request.method == 'POST':
        # --- بسته‌بندی ---
        if worker_stage == 'packaging':
            if not unit.is_packed:
                unit.is_packed = True
                unit.packed_at = timezone.now()
                unit.packed_by = request.user
                unit.save()

                item = unit.order_item
                if item.is_fully_packed and not ProductionLog.objects.filter(
                    order_item=item, stage='packaging'
                ).exists():
                    ProductionLog.objects.create(
                        order_item=item, stage='packaging', user=request.user,
                        notes='همه واحدها بسته‌بندی شدند'
                    )
                messages.success(request, f'✅ واحد {unit.unit_number} بسته‌بندی شد.')
            else:
                messages.warning(request, 'این واحد قبلاً بسته‌بندی شده است.')

        # --- ارسال ---
        elif worker_stage == 'shipping':
            if not unit.is_packed:
                messages.error(request, '⛔ این واحد هنوز بسته‌بندی نشده است. ابتدا باید بسته‌بندی شود.')
                return redirect(next_url)

            # دریافت پلاک از فرم (الزامی)
            plate = request.POST.get('plate', '').strip()
            if not plate:
                messages.error(request, 'لطفاً پلاک خودرو را وارد کنید.')
                # نمایش مجدد صفحه تأیید با خطا
                context = {
                    'unit': unit,
                    'can_pack': False,
                    'can_ship': True,
                    'next_url': next_url,
                    'saved_plate': request.session.get('current_plate', ''),
                }
                return render(request, 'scan_packaging_unit.html', context)

            # ذخیره در session برای استفاده‌های بعدی
            request.session['current_plate'] = plate

            if not unit.is_shipped:
                unit.is_shipped = True
                unit.shipped_at = timezone.now()
                unit.shipped_by = request.user
                unit.save()

                # ثبت لاگ محموله با پلاک صحیح
                ShipmentLog.objects.create(
                    packaging_unit=unit,
                    plate_number=plate,
                    shipped_by=request.user
                )

                item = unit.order_item
                if item.is_fully_shipped and not ProductionLog.objects.filter(
                    order_item=item, stage='shipping'
                ).exists():
                    ProductionLog.objects.create(
                        order_item=item, stage='shipping', user=request.user,
                        notes='همه واحدها ارسال شدند'
                    )
                messages.success(request, f'🚚 واحد {unit.unit_number} ارسال شد.')
            else:
                messages.warning(request, 'این واحد قبلاً ارسال شده است.')

        else:
            messages.error(request, 'شما دسترسی لازم برای این عملیات را ندارید.')

        return redirect(next_url)

    # ==================================================================
    # GET: نمایش صفحه تأیید
    # ==================================================================
    context = {
        'unit': unit,
        'can_pack': worker_stage == 'packaging' and not unit.is_packed,
        'can_ship': worker_stage == 'shipping' and unit.is_packed and not unit.is_shipped,
        'next_url': next_url,
        'saved_plate': request.session.get('current_plate', ''),  # پلاک قبلی (در صورت وجود)
    }
    return render(request, 'scan_packaging_unit.html', context)





@login_required
def undo_packaging_unit(request, pk):
    unit = get_object_or_404(PackagingUnit, pk=pk)
    worker_stage = request.user.workerprofile.stage if hasattr(request.user, 'workerprofile') else None

    if worker_stage not in ['packaging', 'shipping']:
        messages.error(request, 'شما دسترسی لازم برای لغو عملیات را ندارید.')
        return redirect('dashboard')

    # ---------- لغو بسته‌بندی ----------
    if worker_stage == 'packaging':
        if not unit.is_packed:
            messages.warning(request, 'این واحد هنوز بسته‌بندی نشده است.')
        elif unit.packed_by != request.user and not request.user.is_superuser:
            messages.error(request, 'فقط اپراتوری که این واحد را بسته‌بندی کرده می‌تواند آن را لغو کند.')
        else:
            unit.is_packed = False
            unit.packed_at = None
            unit.packed_by = None
            unit.save()

            # حذف ProductionLog مربوط به تکمیل بسته‌بندی (اگر وجود دارد)
            ProductionLog.objects.filter(order_item=unit.order_item, stage='packaging').delete()
            messages.success(request, f'✅ بسته‌بندی واحد {unit.unit_number} لغو شد.')

    # ---------- لغو ارسال ----------
    elif worker_stage == 'shipping':
        if not unit.is_shipped:
            messages.warning(request, 'این واحد هنوز ارسال نشده است.')
        elif unit.shipped_by != request.user and not request.user.is_superuser:
            messages.error(request, 'فقط اپراتوری که این واحد را ارسال کرده می‌تواند آن را لغو کند.')
        else:
            unit.is_shipped = False
            unit.shipped_at = None
            unit.shipped_by = None
            unit.save()

            # حذف ShipmentLog مربوط به این واحد (آخرین لاگ ارسال)
            ShipmentLog.objects.filter(packaging_unit=unit).delete()
            # حذف ProductionLog مربوط به تکمیل ارسال (اگر وجود دارد)
            ProductionLog.objects.filter(order_item=unit.order_item, stage='shipping').delete()
            messages.success(request, f'🚚 ارسال واحد {unit.unit_number} لغو شد.')

    next_url = request.GET.get('next', 'dashboard')
    return redirect(next_url)



# -------------------------------------------------------------------
# ۱. داشبورد مشتری (لیست سفارش‌ها)
# -------------------------------------------------------------------

@login_required
def customer_order_list(request):
    # نمایش تمام سفارش‌هایی که این کاربر ثبت کرده است (مستقل از Customer)
    orders = Order.objects.filter(user=request.user).order_by('-id')
    return render(request, 'customer/order_list.html', {'orders': orders})



# -------------------------------------------------------------------
# ۲. مرحلهٔ اول – اطلاعات مشتری
# -------------------------------------------------------------------

@login_required
def customer_create_order_step1(request):
    # مشتری فعلی کاربر (اگر وجود داشته باشد)
    existing_customer = Customer.objects.filter(user=request.user).first()

    if request.method == 'POST':
        form = CustomerInfoForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            phone = form.cleaned_data.get('phone', '')
            address = form.cleaned_data.get('address', '')
            number = form.cleaned_data.get('number', '')

            # if existing_customer:
            #     # به‌روزرسانی فقط همان رکورد
            #     existing_customer.name = name
            #     existing_customer.phone = phone
            #     existing_customer.address = address
            #     existing_customer.save()
            #     customer = existing_customer
            # else:
            #     # ایجاد مشتری جدید
            customer = Customer.objects.create(
                user=request.user,
                name=name,
                phone=phone,
                address=address
            )

            order = Order.objects.create(
                user=request.user,
                customer=customer,
                number=number,
                status='draft'
            )
            messages.success(request, 'سفارش جدید ایجاد شد. حالا محصولات را اضافه کنید.')
            return redirect('customer_create_order_step2', order_id=order.id)
    else:
        # مقداردهی اولیه فرم
        initial = {}
        if existing_customer:
            initial = {
                'name': existing_customer.name,
                'phone': existing_customer.phone,
                'address': existing_customer.address,
            }
        form = CustomerInfoForm(initial=initial)

    return render(request, 'customer/step1.html', {'form': form})





# -------------------------------------------------------------------
# ۳. مرحلهٔ دوم – افزودن محصولات
# -------------------------------------------------------------------
@login_required
def customer_create_order_step2(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)  # فقط سفارش خودش
    existing_items = order.items.select_related('product__category').prefetch_related('ordercolor')

    if request.method == 'POST':
        item_form = OrderItemForm(request.POST)
        color_form = ColorSelectionForm(request.POST)
        if item_form.is_valid() and color_form.is_valid():
            with transaction.atomic():
                product = item_form.cleaned_data['product']
                order_item = item_form.save(commit=False)
                order_item.order = order
                order_item.product = product
                order_item.unit_price = product.base_price
                order_item.save()

                for part_value, _ in Color.PART_CHOICES:
                    code = color_form.cleaned_data.get(f'color_{part_value}')
                    if code:
                        Color.objects.create(part=part_value, code=code, orderitem=order_item)
                messages.success(request, f'{order_item.product.name} به سفارش اضافه شد.')
                if 'add_another' in request.POST:
                    return redirect('customer_create_order_step2', order_id=order.id)
                else:
                    return redirect('order_invoice', order_id=order.id)
        else:
            messages.error(request, 'لطفاً خطاهای فرم را بررسی کنید.')
    else:
        item_form = OrderItemForm()
        color_form = ColorSelectionForm()

    context = {
        'order': order,
        'item_form': item_form,
        'color_form': color_form,
        'existing_items': existing_items,
    }
    return render(request, 'customer/step2.html', context)



# -------------------------------------------------------------------
#    پیش فاکتور  
# -------------------------------------------------------------------
@login_required
def order_invoice(request, order_id):
    order = get_object_or_404(Order.objects.prefetch_related('items__product__category', 'items__ordercolor'), id=order_id)
    if not (request.user.is_superuser or order.user == request.user):
        return HttpResponseForbidden()
    return render(request, 'order_invoice.html', {'order': order})






# -------------------------------------------------------------------
#    ویرایش سفارش مشتری
# -------------------------------------------------------------------
@login_required
def customer_edit_order_item(request, item_id):
    item = get_object_or_404(OrderItem, pk=item_id)

    if item.order.user != request.user:
        messages.error(request, "شما اجازه ویرایش این آیتم را ندارید.")
        return redirect('customer_order_list')

    if not (item.order.status == 'draft' and item.order.created_at == jdatetime.date.today()):
        messages.error(request, "فقط سفارش‌های پیش‌نویس امروز قابل ویرایش هستند.")
        return redirect('customer_order_detail', order_id=item.order.id)

    existing_colors = {c.part: c.code for c in item.ordercolor.all()}

    if request.method == 'POST':
        item_form = EditOrderItemForm(request.POST, instance=item)
        color_form = ColorSelectionForm(request.POST)

        if item_form.is_valid() and color_form.is_valid():
            with transaction.atomic():
                new_product = item_form.cleaned_data['product']
                if item.product != new_product:
                    item.product = new_product
                    item.unit_price = new_product.base_price
                item_form.save()

                # به‌روزرسانی رنگ‌ها
                item.ordercolor.all().delete()
                for part_value, _ in Color.PART_CHOICES:
                    code = color_form.cleaned_data.get(f'color_{part_value}')
                    if code:
                        Color.objects.create(part=part_value, code=code, orderitem=item)

                messages.success(request, "آیتم با موفقیت ویرایش شد.")
                return redirect('customer_order_detail', order_id=item.order.id)
    else:
        item_form = EditOrderItemForm(instance=item)
        color_form = ColorSelectionForm(initial={
            f'color_{part}': existing_colors.get(part, '')
            for part, _ in Color.PART_CHOICES
        })

    return render(request, 'customer/edit_order_item.html', {
        'item_form': item_form,
        'color_form': color_form,
        'item': item,
    })



# -------------------------------------------------------------------
# مشتری: جزئیات سفارش
# -------------------------------------------------------------------
@login_required
def customer_order_detail(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    if order.user != request.user:
        messages.error(request, "شما اجازه مشاهده این سفارش را ندارید.")
        return redirect('customer_order_list')

    can_edit = (order.status == 'draft' and order.created_at == jdatetime.date.today())
    
    # فرم افزودن آیتم جدید
    add_item_form = OrderItemForm()
    add_color_form = ColorSelectionForm()

    context = {
        'order': order,
        'can_edit': can_edit,
        'add_item_form': add_item_form,
        'add_color_form': add_color_form,
        'edit_customer_form': CustomerInfoForm(initial={
            'name': order.customer.name,
            'phone': order.customer.phone,
            'address': order.customer.address,
            'number': order.number,
        }),
    }
    return render(request, 'customer/order_detail.html', context)




# -------------------------------------------------------------------
# مشتری: ویرایش اطلاعات کلی سفارش (نام، شماره)
# -------------------------------------------------------------------
@login_required
def customer_edit_order_info(request, order_id):
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    if not (order.status == 'draft' and order.created_at == jdatetime.date.today()):
        messages.error(request, "فقط سفارش‌های پیش‌نویس امروز قابل ویرایش هستند.")
        return redirect('customer_order_detail', order_id=order.id)

    if request.method == 'POST':
        form = CustomerInfoForm(request.POST)
        if form.is_valid():
            # به‌روزرسانی Customer
            customer = order.customer
            customer.name = form.cleaned_data['name']
            customer.phone = form.cleaned_data.get('phone', '')
            customer.address = form.cleaned_data.get('address', '')
            customer.save()

            # به‌روزرسانی شماره سفارش
            order.number = form.cleaned_data.get('number', '')
            order.save()

            messages.success(request, "اطلاعات سفارش به‌روز شد.")
            return redirect('customer_order_detail', order_id=order.id)

    return redirect('customer_order_detail', order_id=order.id)


# -------------------------------------------------------------------
# مشتری: افزودن آیتم جدید به سفارش
# -------------------------------------------------------------------
@login_required
def customer_add_item(request, order_id):
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    if not (order.status == 'draft' and order.created_at == jdatetime.date.today()):
        messages.error(request, "فقط سفارش‌های پیش‌نویس امروز قابل ویرایش هستند.")
        return redirect('customer_order_detail', order_id=order.id)

    if request.method == 'POST':
        item_form = OrderItemForm(request.POST)
        color_form = ColorSelectionForm(request.POST)
        if item_form.is_valid() and color_form.is_valid():
            with transaction.atomic():
                product = item_form.cleaned_data['product']
                order_item = item_form.save(commit=False)
                order_item.order = order
                order_item.product = product
                order_item.unit_price = product.base_price
                order_item.save()

                for part_value, _ in Color.PART_CHOICES:
                    code = color_form.cleaned_data.get(f'color_{part_value}')
                    if code:
                        Color.objects.create(part=part_value, code=code, orderitem=order_item)

                messages.success(request, f'{product.name} به سفارش اضافه شد.')
                return redirect('customer_order_detail', order_id=order.id)
        else:
            messages.error(request, 'لطفاً خطاهای فرم را بررسی کنید.')
    return redirect('customer_order_detail', order_id=order.id)


# -------------------------------------------------------------------
# مشتری: ویرایش یک آیتم
# -------------------------------------------------------------------
@login_required
def customer_edit_order_item(request, item_id):
    item = get_object_or_404(OrderItem, pk=item_id)
    if item.order.user != request.user:
        messages.error(request, "شما اجازه ویرایش این آیتم را ندارید.")
        return redirect('customer_order_list')
    if not (item.order.status == 'draft' and item.order.created_at == jdatetime.date.today()):
        messages.error(request, "فقط سفارش‌های پیش‌نویس امروز قابل ویرایش هستند.")
        return redirect('customer_order_detail', order_id=item.order.id)

    # رنگ‌های فعلی
    existing_colors = {c.part: c.code for c in item.ordercolor.all()}

    if request.method == 'POST':
        item_form = EditOrderItemForm(request.POST, instance=item)
        color_form = ColorSelectionForm(request.POST)
        if item_form.is_valid() and color_form.is_valid():
            with transaction.atomic():
                item_form.save()
                # حذف رنگ‌های قبلی و ایجاد جدید
                item.ordercolor.all().delete()
                for part_value, _ in Color.PART_CHOICES:
                    code = color_form.cleaned_data.get(f'color_{part_value}')
                    if code:
                        Color.objects.create(part=part_value, code=code, orderitem=item)
                messages.success(request, "آیتم ویرایش شد.")
                return redirect('customer_order_detail', order_id=item.order.id)
    else:
        item_form = EditOrderItemForm(instance=item)
        color_form = ColorSelectionForm(initial={
            f'color_{part}': existing_colors.get(part, '')
            for part, _ in Color.PART_CHOICES
        })

    return render(request, 'customer/edit_order_item.html', {
        'item_form': item_form,
        'color_form': color_form,
        'item': item,
    })


# -------------------------------------------------------------------
# مشتری: حذف یک آیتم
# -------------------------------------------------------------------
@login_required
def customer_delete_order_item(request, item_id):
    item = get_object_or_404(OrderItem, pk=item_id)
    if item.order.user != request.user:
        messages.error(request, "شما اجازه حذف این آیتم را ندارید.")
        return redirect('customer_order_list')
    if not (item.order.status == 'draft' and item.order.created_at == jdatetime.date.today()):
        messages.error(request, "فقط سفارش‌های پیش‌نویس امروز قابل ویرایش هستند.")
        return redirect('customer_order_detail', order_id=item.order.id)

    if request.method == 'POST':
        order_id = item.order.id
        item.delete()
        messages.success(request, "آیتم با موفقیت حذف شد.")
        return redirect('customer_order_detail', order_id=order_id)

    return redirect('customer_order_detail', order_id=item.order.id)



# -------------------------------------------------------------------
#     حذف آیتم سفارش 
# -------------------------------------------------------------------
@login_required
def customer_delete_order_item(request, item_id):
    item = get_object_or_404(OrderItem, pk=item_id)

    # فقط صاحب سفارش بتواند حذف کند
    if item.order.user != request.user:
        messages.error(request, "شما اجازه حذف این آیتم را ندارید.")
        return redirect('customer_order_list')

    # فقط پیش‌نویس‌های امروز
    if item.order.status != 'draft' or item.order.created_at != jdatetime.date.today():
        messages.error(request, "فقط سفارش‌های پیش‌نویس امروز قابل تغییر هستند.")
        return redirect('customer_order_list')

    order_id = item.order.id
    item_name = item.product.name
    item.delete()
    messages.success(request, f"آیتم «{item_name}» با موفقیت حذف شد.")
    return redirect('customer_order_detail', order_id=order_id)



# -------------------------------------------------------------------
#    پرینت همه برگه های سفارش
# -------------------------------------------------------------------
@login_required
def order_combined_print(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related(
            'items__product__category',
            'items__product__bom__part',
            'items__ordercolor',
            'items__packaging_units',
        ),
        id=order_id
    )

    # آماده‌سازی داده‌ها برای هر آیتم
    items_data = []
    for item in order.items.all():
        # رنگ
        item.color = item.color_summary

        # BOM
        bom_list = item.product.bom.all()
        item.bompart = [{'part': b.part, 'quantity': b.quantity} for b in bom_list]

        # واحدهای بسته‌بندی
        units = item.packaging_units.all()

        items_data.append({
            'item': item,
            'units': units,
        })

    context = {
        'order': order,
        'items_data': items_data,
    }
    return render(request, 'order_combined_print.html', context)




from .models import PackagingUnit, ShipmentLog  
# -------------------------------------------------------------------
#   برگه خروج  بارگیری  
# -------------------------------------------------------------------
@login_required
@staff_or_representative_required
def report_shipped(request):
    # ---------- تاریخ شمسی (پیش‌فرض امروز) ----------
    date_str = request.GET.get('date')
    if date_str:
        try:
            y, m, d = map(int, date_str.split('-'))
            persian_date = jdatetime.date(y, m, d)
        except (ValueError, TypeError):
            persian_date = jdatetime.date.today()
    else:
        persian_date = jdatetime.date.today()

    gregorian_date = persian_date.togregorian()

    # ---------- کوئری پایه ----------
    units = PackagingUnit.objects.filter(
        is_shipped=True,
        shipped_at__date=gregorian_date
    ).select_related(
        'order_item__order__customer',
        'order_item__order__user',
        'order_item__product__category',
        'shipped_by'
    ).prefetch_related(
        'order_item__ordercolor',
        'shipment_logs'            # ← برای فیلتر پلاک لازم است
    )
    units = units.order_by('order_item__product__category__name', 'order_item__product__name')
    # ---------- فیلتر پلاک ----------
    plate = request.GET.get('plate')
    if plate:
        units = units.filter(shipment_logs__plate_number=plate)

    # ---------- فیلتر نماینده ----------
    representative_id = request.GET.get('representative')
    if representative_id:
        units = units.filter(order_item__order__user_id=representative_id)

    # ---------- فیلتر شماره سفارش ----------
    order_id = request.GET.get('order_id')
    if order_id:
        units = units.filter(order_item__order_id=order_id)

    # ---------- محاسبات مشترک ----------
    representative_name = ""
    total_price = 0
    if units.exists():
        if representative_id:
            try:
                rep = User.objects.get(pk=representative_id)
                representative_name = rep.get_full_name() or rep.username
            except User.DoesNotExist:
                pass
        else:
            representative_name = units.first().order_item.order.user.get_full_name() or units.first().order_item.order.user.username
        total_price = sum(unit.order_item.unit_price for unit in units)

    # ---------- درخواست چاپ برگه ترخیص ----------
    if request.GET.get('print'):
        return render(request, 'reports/delivery_note.html', {
            'units': units,
            'today': persian_date,
            'representative_name': representative_name,
            'total_price': total_price,
            'plate': request.GET.get('plate', ''),   # ← پلاک از فیلتر

        })

    # ---------- لیست نمایندگان برای dropdown ----------
    representatives = User.objects.filter(
        order__items__packaging_units__is_shipped=True
    ).distinct().order_by('username')

    # ---------- لیست پلاک‌های موجود (واقعی) ----------
    plates = ShipmentLog.objects.values_list('plate_number', flat=True).distinct().order_by('plate_number')

    context = {
        'units': units,
        'representatives': representatives,
        'selected_representative': representative_id,
        'selected_date': persian_date.strftime('%Y-%m-%d'),
        'selected_order': order_id or '',
        'representative_name': representative_name,
        'total_price': total_price,
        'plates': plates,
        'selected_plate': plate or '',
    }
    return render(request, 'reports/shipped.html', context)





















import json
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.forms import inlineformset_factory
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from .decorators import admin_or_manager_required
from .models import Product, ProductBOM, Part, Color
from .forms import ProductCreateForm, PartForm


# -------------------------------------------------------------------
# ویوهای محصول
# -------------------------------------------------------------------
@login_required
@admin_or_manager_required
def product_create(request):
    BOMFormSet = inlineformset_factory(
        Product, ProductBOM,
        fields=['part', 'quantity', 'color_part', 'color_material_map', 'size_adjustment_rule'],
        extra=1, can_delete=True,
        widgets={
            'part': forms.HiddenInput(),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'color_part': forms.Select(attrs={'class': 'form-select color-part-select'}),
            'color_material_map': forms.HiddenInput(),
            'size_adjustment_rule': forms.HiddenInput(attrs={'class': 'size-rule-hidden'}),
        }
    )

    if request.method == 'POST':
        product_form = ProductCreateForm(request.POST)
        formset = BOMFormSet(request.POST, prefix='bom')

        if product_form.is_valid() and formset.is_valid():
            with transaction.atomic():
                product = product_form.save(commit=False)
                default_colors = {}
                for part, _ in Color.PART_CHOICES:
                    field_name = f'color_{part}'
                    code = product_form.cleaned_data.get(field_name)
                    if code:
                        default_colors[part] = code
                product.default_colors = default_colors
                product.save()

                instances = formset.save(commit=False)
                for bom in instances:
                    bom.product = product
                    bom.allow_material_override = bool(bom.color_part)
                    bom.size_affected = bool(bom.size_adjustment_rule)
                    if not bom.color_material_map:
                        bom.color_material_map = {}
                    bom.save()
                for obj in formset.deleted_objects:
                    obj.delete()

                messages.success(request, '✅ محصول و قطعات با موفقیت ذخیره شدند.')
                return redirect('admin_product_list')
    else:
        product_form = ProductCreateForm()
        formset = BOMFormSet(prefix='bom')

    context = {
        'product_form': product_form,
        'formset': formset,
        'product': None,
        'materials': Material.objects.all(),      
        'all_parts': Part.objects.all(),          
    }
    return render(request, 'product_create.html', context)


@login_required
@admin_or_manager_required
def product_edit(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    BOMFormSet = inlineformset_factory(
        Product, ProductBOM,
        fields=['part', 'quantity', 'color_part', 'color_material_map', 'size_adjustment_rule'],
        extra=0, can_delete=True,
        widgets={
            'part': forms.HiddenInput(),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'color_part': forms.Select(attrs={'class': 'form-select color-part-select'}),
            'color_material_map': forms.HiddenInput(),
            'size_adjustment_rule': forms.HiddenInput(attrs={'class': 'size-rule-hidden'}),
        }
    )

    if request.method == 'POST':
        product_form = ProductCreateForm(request.POST, instance=product)
        formset = BOMFormSet(request.POST, prefix='bom', instance=product)

        if product_form.is_valid() and formset.is_valid():
            with transaction.atomic():
                product = product_form.save(commit=False)
                default_colors = {}
                for part, _ in Color.PART_CHOICES:
                    field_name = f'color_{part}'
                    code = product_form.cleaned_data.get(field_name)
                    if code:
                        default_colors[part] = code
                product.default_colors = default_colors
                product.save()

                instances = formset.save(commit=False)
                for bom in instances:
                    bom.product = product
                    bom.allow_material_override = bool(bom.color_part)
                    bom.size_affected = bool(bom.size_adjustment_rule)
                    if not bom.color_material_map:
                        bom.color_material_map = {}
                    bom.save()
                for obj in formset.deleted_objects:
                    obj.delete()

                messages.success(request, '✅ محصول با موفقیت ویرایش شد.')
                return redirect('admin_product_list')
    else:
        product_form = ProductCreateForm(instance=product)
        formset = BOMFormSet(prefix='bom', instance=product)

    context = {
        'product_form': product_form,
        'formset': formset,
        'product': product,
        'materials': Material.objects.all(),      
        'all_parts': Part.objects.all(),          
    }
    return render(request, 'product_create.html', context)


# -------------------------------------------------------------------
# ویوهای AJAX قطعه
# -------------------------------------------------------------------
@login_required
@admin_or_manager_required
def ajax_create_part(request):
    """ایجاد قطعه جدید از طریق AJAX"""
    if request.method == 'POST':
        form = PartForm(request.POST)
        if form.is_valid():
            part = form.save(commit=False)
            part.f2 = part.name
            part.save()
            return JsonResponse({'success': True, 'id': part.id, 'name': str(part)})
        return JsonResponse({'success': False, 'errors': form.errors})
    return JsonResponse({'success': False})


@login_required
@admin_or_manager_required
def ajax_get_part(request, part_id):
    """دریافت اطلاعات یک قطعه برای ویرایش (JSON)"""
    part = get_object_or_404(Part, pk=part_id)
    data = {
        'id': part.id,
        'name': part.name,
        'material': part.material_id,
        'length': str(part.length),
        'width': str(part.width),
        'grain': part.grain,
        'pname': part.pname,
        'turn': part.turn,
        'f26': part.f26,
        'f18': part.f18,
        'f4': part.f4,
        'f5': part.f5,
        'f3': part.f3,
        'routing_code': part.routing_code,
        'base_part': part.base_part_id,
    }
    return JsonResponse(data)


@login_required
@admin_or_manager_required
def ajax_edit_part(request, part_id):
    """ویرایش قطعه موجود از طریق AJAX"""
    part = get_object_or_404(Part, pk=part_id)
    if request.method == 'POST':
        form = PartForm(request.POST, instance=part)
        if form.is_valid():
            part = form.save(commit=False)
            part.f2 = part.name
            part.save()
            return JsonResponse({'success': True, 'id': part.id, 'name': str(part)})
        return JsonResponse({'success': False, 'errors': form.errors})
    return JsonResponse({'success': False})













from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages

@login_required
def set_plate(request):
    if request.method == 'POST':
        plate = request.POST.get('plate', '').strip()
        if plate:
            request.session['current_plate'] = plate
            messages.success(request, f'پلاک "{plate}" برای بارگیری فعال شد.')
        else:
            request.session.pop('current_plate', None)
            messages.warning(request, 'پلاک پاک شد.')
        return redirect('scan_part')   # می‌توانید به صفحهٔ اسکن یا هر جای دیگر هدایت کنید
    current_plate = request.session.get('current_plate', '')
    return render(request, 'set_plate.html', {'current_plate': current_plate})
















# views.py - بخش ارسال‌های مشتری

@login_required
def customer_shipments(request):
    """لیست ارسال‌های مشتری (گروه‌بندی شده بر اساس پلاک و تاریخ)"""
    # دریافت سفارش‌های کاربر
    orders = Order.objects.filter(user=request.user)
    
    # دریافت واحدهای ارسال‌شده مرتبط با سفارش‌های کاربر
    shipments = (
        PackagingUnit.objects
        .filter(order_item__order__in=orders, is_shipped=True)
        .select_related(
            'order_item__order__customer',
            'order_item__product__category',
            'order_item__order__user'
        )
        .prefetch_related('shipment_logs', 'order_item__ordercolor')
        .order_by('-shipped_at')
    )
    
    # گروه‌بندی بر اساس پلاک و تاریخ
    groups = {}
    for unit in shipments:
        log = unit.shipment_logs.first()
        if log:
            key = f"{log.plate_number}_{log.shipped_at.date()}"
            if key not in groups:
                groups[key] = {
                    'plate': log.plate_number,
                    'date': log.shipped_at,
                    'units': [],
                    'total_price': 0,
                }
            groups[key]['units'].append(unit)
            groups[key]['total_price'] += int(unit.order_item.unit_price or 0)
    
    # تبدیل به لیست برای مرتب‌سازی (جدیدترین اول)
    shipment_groups = list(groups.values())
    shipment_groups.sort(key=lambda x: x['date'], reverse=True)
    
    context = {
        'shipment_groups': shipment_groups,
    }
    return render(request, 'customer/shipments.html', context)


@login_required
def customer_shipment_detail(request, plate, date):
    """نمایش جزئیات یک سری ارسال (برگه ترخیص)"""
    from datetime import datetime
    import jdatetime
    
    try:
        ship_date = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, 'تاریخ نامعتبر است.')
        return redirect('customer_shipments')
    
    # دریافت سفارش‌های کاربر
    orders = Order.objects.filter(user=request.user)
    
    # دریافت واحدهای ارسال‌شده با آن پلاک و تاریخ
    units = (
        PackagingUnit.objects
        .filter(
            order_item__order__in=orders,
            is_shipped=True,
            shipment_logs__plate_number=plate,
            shipped_at__date=ship_date
        )
        .select_related(
            'order_item__order__customer',
            'order_item__product__category',
            'order_item__order__user'
        )
        .prefetch_related('shipment_logs', 'order_item__ordercolor')
        .order_by('order_item__order__id', 'order_item__product__name')
    )
    
    if not units.exists():
        messages.warning(request, 'هیچ ارسالی با این مشخصات یافت نشد.')
        return redirect('customer_shipments')
    
    # اطلاعات نماینده و مشتری
    first_unit = units.first()
    representative = first_unit.order_item.order.user
    representative_name = representative.get_full_name() or representative.username
    customer_name = first_unit.order_item.order.customer.name
    
    # محاسبه جمع کل
    total_price = sum(int(u.order_item.unit_price or 0) for u in units)
    
    # تاریخ شمسی
    shamsi_date = jdatetime.date.fromgregorian(date=ship_date).strftime('%Y/%m/%d')
    
    context = {
        'units': units,
        'plate': plate,
        'date': ship_date,
        'shamsi_date': shamsi_date,
        'representative_name': representative_name,
        'customer_name': customer_name,
        'total_price': total_price,
    }
    return render(request, 'customer/shipment_detail.html', context)


# -------------------------------------------------------------------
#     روند نقاشی و برنامه‌ریزی روزانه
# -------------------------------------------------------------------

@login_required
@admin_or_manager_required
def assign_painting_process(request, item_id):
    from .utils import get_unique_color_codes_for_item, get_painting_process_for_color
    from .models import PaintingProcess, ProductionTask, create_paint_tasks

    item = get_object_or_404(OrderItem, pk=item_id)

    if request.method == 'POST':
        with transaction.atomic():
            ProductionTask.objects.filter(
                order=item.order,
                station_name='paint',
                order_item=item
            ).delete()

            global_base = ProductionTask.objects.filter(order=item.order).aggregate(
                max_step=models.Max('step_order')
            )['max_step'] or 0

            new_tasks = []
            errors = []

            color_codes = get_unique_color_codes_for_item(item)
            item_colors = {c.part: c.code for c in item.ordercolor.all()}

            if not color_codes:
                errors.append("⚠️ هیچ کد رنگی برای این آیتم یافت نشد.")

            for color_code in color_codes:
                painting_process = get_painting_process_for_color(color_code)
                if not painting_process:
                    errors.append(f"❌ کد رنگ {color_code}: روند نقاشی فعالی یافت نشد.")
                    continue

                sample_part = item.product.bom.first().part if item.product.bom.exists() else None
                if not sample_part:
                    errors.append(f"❌ کد رنگ {color_code}: قطعه‌ای در BOM یافت نشد.")
                    continue

                total_qty = item.quantity
                color_part_name = next((part for part, code in item_colors.items() if code == color_code), f"رنگ {color_code}")

                create_paint_tasks(
                    tasks_list=new_tasks,
                    order=item.order,
                    part=sample_part,
                    quantity=total_qty,
                    process=painting_process,
                    base_step=global_base,
                    order_item=item,
                    color_part=color_part_name
                )
                global_base += painting_process.stages.count()

            if new_tasks:
                ProductionTask.objects.bulk_create(new_tasks)
                messages.success(
                    request,
                    f"✅ {len(new_tasks)} تسک نقاشی برای آیتم {item.id} ایجاد شد."
                )
                for err in errors:
                    messages.warning(request, err)
            else:
                for err in errors:
                    messages.error(request, err)
                messages.error(request, "❌ هیچ تسک نقاشی‌ای ایجاد نشد.")

        return redirect('item_detail', pk=item_id)

    color_codes = get_unique_color_codes_for_item(item)
    return render(request, 'assign_painting.html', {
        'item': item,
        'color_codes': color_codes,
        'has_colors': item.ordercolor.exists() or bool(item.product.default_colors),
    })


@login_required
@admin_or_manager_required
def daily_schedule_print(request):
    """نمایش و چاپ برنامه روزانه کارگران نقاشی"""
    from django.db.models import Sum
    from .models import ProductionTask, WorkerProfile

    date_str = request.GET.get('date')
    if date_str:
        try:
            y, m, d = map(int, date_str.split('-'))
            selected_date = jdatetime.date(y, m, d)
        except (ValueError, TypeError):
            selected_date = jdatetime.date.today()
    else:
        selected_date = jdatetime.date.today()

    gregorian_date = selected_date.togregorian()

    # واکشی یکجای همهٔ تسک‌های نقاشیِ برنامه‌ریزی‌شده در این روز
    tasks = list(
        ProductionTask.objects.filter(
            station_name='paint',
            scheduled_start__date=gregorian_date
        ).select_related('order', 'order_item__order', 'order_item__product', 'part', 'painting_stage', 'assigned_worker')
        .order_by('scheduled_start')
    )

    # گروه‌بندی بر اساس کارگر تخصیص‌یافته (با سطل «تخصیص‌نیافته»)
    grouped = {}
    for task in tasks:
        worker = task.assigned_worker
        key = worker.id if worker else None
        grouped.setdefault(key, []).append(task)

    workers_by_id = {
        wp.user_id: wp.user
        for wp in WorkerProfile.objects.filter(user_id__in=[k for k in grouped if k])
    }

    schedule_data = []
    for worker_id, worker_tasks in grouped.items():
        if worker_id:
            worker = workers_by_id.get(worker_id)
            label = worker.get_full_name() if worker else f"کارگر #{worker_id}"
        else:
            label = "تخصیص‌نیافته"
        total_duration = sum(t.painting_stage.duration_minutes if t.painting_stage else 0 for t in worker_tasks)
        schedule_data.append({
            'worker_label': label,
            'worker': workers_by_id.get(worker_id) if worker_id else None,
            'tasks': worker_tasks,
            'total_duration': total_duration,
        })

    context = {
        'schedule_data': schedule_data,
        'selected_date': selected_date,
        'selected_date_str': selected_date.strftime('%Y/%m/%d'),
        'gregorian_date': gregorian_date,
        'today': jdatetime.date.today(),
        'today_str': jdatetime.date.today().strftime('%Y/%m/%d'),
        'yesterday': (selected_date - jdatetime.timedelta(days=1)).strftime('%Y-%m-%d'),
        'tomorrow': (selected_date + jdatetime.timedelta(days=1)).strftime('%Y-%m-%d'),
    }
    return render(request, 'daily_schedule_print.html', context)


@login_required
@admin_or_manager_required
def auto_assign_tasks_view(request):
    """اجرای دستی تخصیص خودکار کارگران به تسک‌های نقاشی"""
    if request.method == 'POST':
        from .utils import auto_assign_paint_tasks
        auto_assign_paint_tasks()
        messages.success(request, "تخصیص خودکار کارگران انجام شد.")
    return redirect('dashboard')


# -------------------------------------------------------------------
#     پنل مدیریت جامع نقاشی
# -------------------------------------------------------------------

@login_required
@admin_or_manager_required
def painting_management_dashboard(request):
    """داشبورد مدیریت نقاشی - صفحه اصلی با خلاصه اطلاعات"""
    from .utils import get_painting_ready_items_queryset, get_unscheduled_ready_items, painting_nav_context

    recent_tasks = ProductionTask.objects.filter(
        station_name='paint'
    ).select_related('order', 'part', 'painting_stage', 'assigned_worker', 'order_item__product').order_by('-id')[:10]

    context = {
        'active_tab': 'dashboard',
        'total_processes': PaintingProcess.objects.count(),
        'active_processes': PaintingProcess.objects.filter(is_active=True).count(),
        'total_stages': PaintingStage.objects.count(),
        'total_workers': WorkerProfile.objects.filter(stage='paint').count(),
        'pending_tasks': ProductionTask.objects.filter(station_name='paint', status__in=['pending', 'waiting']).count(),
        'unassigned_tasks': ProductionTask.objects.filter(station_name='paint', assigned_worker__isnull=True, status__in=['pending', 'waiting']).count(),
        'ready_items_count': get_painting_ready_items_queryset().count(),
        'unscheduled_ready_count': get_unscheduled_ready_items().count(),
        'recent_tasks': recent_tasks,
        **painting_nav_context(),
    }
    return render(request, 'painting_management/dashboard.html', context)


@login_required
@admin_or_manager_required
def painting_processes_view(request):
    """مدیریت روندهای نقاشی (لیست، ایجاد، ویرایش، حذف)"""
    from .models import PaintingProcess
    from .forms import PaintingProcessForm

    from .utils import painting_nav_context

    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        action = request.POST.get('action')

        if action == 'create':
            form = PaintingProcessForm(request.POST)
            if form.is_valid():
                process = form.save()
                return JsonResponse({'success': True, 'id': process.id, 'name': process.name})
            return JsonResponse({'success': False, 'errors': form.errors})

        elif action == 'edit':
            process_id = request.POST.get('process_id')
            process = get_object_or_404(PaintingProcess, pk=process_id)
            form = PaintingProcessForm(request.POST, instance=process)
            if form.is_valid():
                form.save()
                return JsonResponse({'success': True})
            return JsonResponse({'success': False, 'errors': form.errors})

        elif action == 'delete':
            process_id = request.POST.get('process_id')
            process = get_object_or_404(PaintingProcess, pk=process_id)
            process.delete()
            return JsonResponse({'success': True})

        elif action == 'toggle_active':
            process_id = request.POST.get('process_id')
            process = get_object_or_404(PaintingProcess, pk=process_id)
            process.is_active = not process.is_active
            process.save()
            return JsonResponse({'success': True, 'is_active': process.is_active})

    # GET: نمایش لیست
    processes = PaintingProcess.objects.all().annotate(stage_count=Count('stages')).order_by('-is_active', 'name')

    # جستجو
    search = request.GET.get('search')
    if search:
        processes = processes.filter(Q(name__icontains=search) | Q(code__icontains=search))

    paginator = Paginator(processes, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'active_tab': 'processes',
        'processes': page_obj,
        'search': search,
        'form': PaintingProcessForm(),
        **painting_nav_context(),
    }
    return render(request, 'painting_management/processes.html', context)


@login_required
@admin_or_manager_required
def painting_process_detail_api(request, process_id):
    """بازگرداندن داده‌های یک روند برای فرم ویرایش (AJAX)"""
    from .models import PaintingProcess

    process = get_object_or_404(PaintingProcess, pk=process_id)
    return JsonResponse({
        'id': process.id,
        'name': process.name,
        'code': process.code,
        'color_codes': process.color_codes or [],
        'is_active': process.is_active,
        'description': process.description or '',
    })


@login_required
@admin_or_manager_required
def painting_stages_view(request, process_id=None):
    """مدیریت مراحل نقاشی برای یک روند خاص"""
    from .models import PaintingProcess, PaintingStage
    from .forms import PaintingStageForm

    from .utils import painting_nav_context

    process = None
    if process_id:
        process = get_object_or_404(PaintingProcess, pk=process_id)

    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        action = request.POST.get('action')

        if action == 'create':
            form = PaintingStageForm(request.POST)
            if form.is_valid():
                stage = form.save()
                return JsonResponse({'success': True, 'id': stage.id, 'name': stage.name})
            return JsonResponse({'success': False, 'errors': form.errors})

        elif action == 'edit':
            stage_id = request.POST.get('stage_id')
            stage = get_object_or_404(PaintingStage, pk=stage_id)
            form = PaintingStageForm(request.POST, instance=stage)
            if form.is_valid():
                form.save()
                return JsonResponse({'success': True})
            return JsonResponse({'success': False, 'errors': form.errors})

        elif action == 'delete':
            stage_id = request.POST.get('stage_id')
            stage = get_object_or_404(PaintingStage, pk=stage_id)
            stage.delete()
            return JsonResponse({'success': True})

        elif action == 'reorder':
            # تغییر ترتیب مراحل
            stage_ids = request.POST.getlist('stage_ids[]')
            with transaction.atomic():
                for idx, stage_id in enumerate(stage_ids, start=1):
                    stage = PaintingStage.objects.get(pk=stage_id)
                    stage.order = idx
                    stage.save()
            return JsonResponse({'success': True})

    # GET: نمایش لیست مراحل
    stages = PaintingStage.objects.all()
    if process:
        stages = stages.filter(process=process)
    stages = stages.select_related('process').order_by('process__name', 'order')

    # جستجو
    search = request.GET.get('search')
    if search:
        stages = stages.filter(Q(name__icontains=search) | Q(process__name__icontains=search))

    paginator = Paginator(stages, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'active_tab': 'stages',
        'stages': page_obj,
        'process': process,
        'search': search,
        'form': PaintingStageForm(),
        'processes': PaintingProcess.objects.all(),
        **painting_nav_context(),
    }
    return render(request, 'painting_management/stages.html', context)


@login_required
@admin_or_manager_required
def painting_stage_detail_api(request, stage_id):
    """بازگرداندن داده‌های یک مرحله برای فرم ویرایش (AJAX)"""
    from .models import PaintingStage

    stage = get_object_or_404(PaintingStage, pk=stage_id)
    return JsonResponse({
        'id': stage.id,
        'process': stage.process_id,
        'order': stage.order,
        'name': stage.name,
        'duration_minutes': stage.duration_minutes,
        'drying_time_minutes': stage.drying_time_minutes,
        'required_skill': stage.required_skill,
    })


@login_required
@admin_or_manager_required
def painting_workers_view(request):
    """مدیریت کارگران نقاشی و مهارت‌هایشان"""
    import json
    from .models import WorkerProfile
    from .forms import WorkerProfileForm

    from .utils import painting_nav_context

    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        action = request.POST.get('action')

        if action == 'create':
            form = WorkerProfileForm(request.POST)
            if form.is_valid():
                worker = form.save()
                return JsonResponse({'success': True, 'id': worker.id, 'name': worker.user.username})
            return JsonResponse({'success': False, 'errors': form.errors})

        elif action == 'edit':
            worker_id = request.POST.get('worker_id')
            worker = get_object_or_404(WorkerProfile, pk=worker_id)
            form = WorkerProfileForm(request.POST, instance=worker)
            if form.is_valid():
                form.save()
                return JsonResponse({'success': True})
            return JsonResponse({'success': False, 'errors': form.errors})

        elif action == 'delete':
            worker_id = request.POST.get('worker_id')
            worker = get_object_or_404(WorkerProfile, pk=worker_id)
            worker.delete()
            return JsonResponse({'success': True})

        elif action == 'assign_skills':
            # به‌روزرسانی JSON مهارت‌ها
            worker_id = request.POST.get('worker_id')
            worker = get_object_or_404(WorkerProfile, pk=worker_id)
            skills = request.POST.get('skills', '[]')
            try:
                worker.skills = json.loads(skills)
                worker.save()
                return JsonResponse({'success': True})
            except json.JSONDecodeError:
                return JsonResponse({'success': False, 'error': 'فرمت JSON نامعتبر'})

    # GET: نمایش لیست کارگران
    workers = WorkerProfile.objects.filter(stage='paint').select_related('user').annotate(
        active_tasks=Count(
            'user__assigned_tasks',
            filter=Q(user__assigned_tasks__station_name='paint', user__assigned_tasks__status__in=['pending', 'waiting'])
        )
    ).order_by('user__username')

    # جستجو
    search = request.GET.get('search')
    if search:
        workers = workers.filter(
            Q(user__username__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
        )

    paginator = Paginator(workers, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'active_tab': 'workers',
        'workers': page_obj,
        'search': search,
        'form': WorkerProfileForm(),
        'skill_choices': PaintingStage.SKILL_CHOICES,
        **painting_nav_context(),
    }
    return render(request, 'painting_management/workers.html', context)


@login_required
@admin_or_manager_required
def painting_schedule_view(request):
    """برنامه‌ریزی و تخصیص کارگران به تسک‌های نقاشی"""
    from .utils import get_unscheduled_ready_items, parse_jalali_date, painting_nav_context

    date_str = request.GET.get('date')
    selected_date = parse_jalali_date(date_str)
    gregorian_date = selected_date.togregorian()

    tasks = list(
        ProductionTask.objects.filter(
            station_name='paint',
            scheduled_start__date=gregorian_date,
        ).select_related(
            'order_item__order', 'order_item__product', 'order_item__product__category', 'painting_stage', 'assigned_worker',
        ).prefetch_related('order_item__ordercolor').order_by('scheduled_start', 'step_order')
    )

    grouped_tasks = {}
    for task in tasks:
        if task.assigned_worker:
            label = task.assigned_worker.get_full_name() or task.assigned_worker.username
        else:
            label = 'تخصیص نشده'
        grouped_tasks.setdefault(label, []).append(task)

    workers = WorkerProfile.objects.filter(stage='paint').select_related('user')

    from collections import defaultdict
    workers_by_skill = defaultdict(list)
    for wp in workers:
        for skill in (wp.skills or []):
            workers_by_skill[skill].append(wp)

    unassigned_tasks = list(
        ProductionTask.objects.filter(
            station_name='paint',
            assigned_worker__isnull=True,
            status__in=['pending', 'waiting'],
            scheduled_start__date=gregorian_date,
        ).select_related(
            'order_item__order', 'order_item__product', 'order_item__product__category', 'painting_stage',
        ).prefetch_related('order_item__ordercolor').order_by('scheduled_start', 'step_order')
    )

    ready_unscheduled = get_unscheduled_ready_items()

    stats = {
        'total_tasks': len(tasks),
        'assigned_tasks': sum(1 for t in tasks if t.assigned_worker),
        'unassigned_tasks': len(unassigned_tasks),
        'ready_unscheduled': ready_unscheduled.count(),
        'total_duration': sum(t.painting_stage.duration_minutes if t.painting_stage else 0 for t in tasks),
    }

    context = {
        'active_tab': 'schedule',
        'grouped_tasks': grouped_tasks,
        'unassigned_tasks': unassigned_tasks,
        'ready_unscheduled': ready_unscheduled,
        'selected_date': selected_date,
        'selected_date_str': selected_date.strftime('%Y-%m-%d'),
        'selected_date_display': selected_date.strftime('%Y/%m/%d'),
        'workers': workers,
        'workers_by_skill': dict(workers_by_skill),
        'stats': stats,
        'yesterday': (selected_date - jdatetime.timedelta(days=1)).strftime('%Y-%m-%d'),
        'tomorrow': (selected_date + jdatetime.timedelta(days=1)).strftime('%Y-%m-%d'),
        'schedule_date': selected_date.strftime('%Y-%m-%d'),
        **painting_nav_context(),
    }
    return render(request, 'painting_management/schedule.html', context)


@login_required
@admin_or_manager_required
def painting_ready_list(request):
    """آیتم‌های آماده نقاشی (لاگ mon + تسک pending)"""
    from .utils import get_painting_ready_items_queryset, painting_nav_context

    search = request.GET.get('search')
    process_id = request.GET.get('process')

    ready_items = get_painting_ready_items_queryset(search=search, process_id=process_id)

    context = {
        'active_tab': 'ready',
        'items': ready_items,
        'search': search,
        'processes': PaintingProcess.objects.filter(is_active=True),
        'selected_process': process_id,
        'schedule_date': jdatetime.date.today().strftime('%Y-%m-%d'),
        **painting_nav_context(),
    }
    return render(request, 'painting_management/ready_list.html', context)


@login_required
@admin_or_manager_required
def painting_add_to_schedule(request):
    """افزودن آیتم‌های انتخاب‌شده به برنامه روزانه (AJAX)"""
    from .utils import parse_jalali_date, schedule_paint_items_for_date

    if request.method != 'POST' or request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'success': False, 'error': 'درخواست نامعتبر'})

    item_ids = request.POST.getlist('item_ids[]') or request.POST.getlist('item_ids')
    if not item_ids:
        return JsonResponse({'success': False, 'error': 'هیچ آیتمی انتخاب نشده است'})

    try:
        target_date = parse_jalali_date(request.POST.get('date'))
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)})

    try:
        count = schedule_paint_items_for_date(item_ids, target_date)
        if count == 0:
            return JsonResponse({'success': False, 'error': 'آیتم انتخاب‌شده واجد شرایط نیست یا قبلاً برنامه‌ریزی شده'})
        return JsonResponse({
            'success': True,
            'message': f'{count} تسک به برنامه {target_date.strftime("%Y/%m/%d")} اضافه شد.',
            'scheduled_count': count,
            'redirect': reverse('painting_schedule') + f'?date={target_date.strftime("%Y-%m-%d")}',
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@admin_or_manager_required
def painting_assign_process(request):
    """تخصیص خودکار روند نقاشی به یک آیتم سفارش بر اساس کدهای رنگی (AJAX)"""
    from .utils import get_unique_color_codes_for_item, get_painting_process_for_color

    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        item_id = request.POST.get('item_id')

        if not item_id:
            return JsonResponse({'success': False, 'error': 'اطلاعات ناقص'})

        item = get_object_or_404(OrderItem, pk=item_id)

        try:
            with transaction.atomic():
                ProductionTask.objects.filter(
                    order=item.order,
                    station_name='paint',
                    order_item=item
                ).delete()

                global_base = ProductionTask.objects.filter(order=item.order).aggregate(
                    max_step=models.Max('step_order')
                )['max_step'] or 0

                color_codes = get_unique_color_codes_for_item(item)
                new_tasks = []

                for color_code in color_codes:
                    painting_process = get_painting_process_for_color(color_code)
                    if not painting_process:
                        continue

                    sample_part = item.product.bom.first().part if item.product.bom.exists() else None
                    if not sample_part:
                        continue

                    create_paint_tasks(
                        new_tasks, item.order, sample_part, item.quantity,
                        painting_process, global_base, order_item=item, color_part=f"رنگ {color_code}"
                    )
                    global_base += painting_process.stages.count()

                if new_tasks:
                    ProductionTask.objects.bulk_create(new_tasks)

                return JsonResponse({'success': True, 'message': 'روند نقاشی با موفقیت اعمال شد.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'درخواست نامعتبر'})


@login_required
@admin_or_manager_required
def painting_auto_assign(request):
    """اجرای تخصیص خودکار کارگران (AJAX)"""
    from .utils import auto_assign_paint_tasks, parse_jalali_date

    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            target_date = None
            if request.POST.get('date'):
                target_date = parse_jalali_date(request.POST.get('date'))

            auto_assign_paint_tasks(target_date=target_date)

            assigned_qs = ProductionTask.objects.filter(
                station_name='paint',
                assigned_worker__isnull=False,
                status__in=['pending', 'waiting'],
            )
            if target_date:
                assigned_qs = assigned_qs.filter(scheduled_start__date=target_date.togregorian())

            return JsonResponse({
                'success': True,
                'message': 'تخصیص خودکار با موفقیت انجام شد.',
                'assigned_count': assigned_qs.count(),
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'درخواست نامعتبر'})


@login_required
@admin_or_manager_required
def painting_get_available_workers(request):
    """دریافت لیست کارگران با مهارت خاص (AJAX) برای انتخاب دستی"""
    from .models import WorkerProfile

    skill = request.GET.get('skill')
    if not skill:
        return JsonResponse({'workers': []})

    # فیلتر در سمت پایتون (skills__contains روی SQLite پشتیبانی نمی‌شود)
    workers = WorkerProfile.objects.filter(stage='paint').select_related('user')
    data = [{
        'id': w.user.id,
        'name': w.user.get_full_name() or w.user.username,
        'active_tasks': w.user.assigned_tasks.filter(status__in=['pending', 'waiting']).count()
    } for w in workers if skill in (w.skills or [])]

    return JsonResponse({'workers': data})


@login_required
@admin_or_manager_required
def painting_assign_worker(request):
    """تخصیص دستی یک کارگر به یک تسک نقاشی (AJAX)"""
    from .models import ProductionTask
    from django.contrib.auth.models import User

    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        task_id = request.POST.get('task_id')
        worker_id = request.POST.get('worker_id')
        if not task_id or not worker_id:
            return JsonResponse({'success': False, 'error': 'اطلاعات ناقص'})

        task = get_object_or_404(ProductionTask, pk=task_id, station_name='paint')
        worker_user = get_object_or_404(User, pk=worker_id)
        task.assigned_worker = worker_user
        task.save()
        return JsonResponse({'success': True})

    return JsonResponse({'success': False, 'error': 'درخواست نامعتبر'})


@login_required
@admin_or_manager_required
def painting_clear_schedule(request):
    """پاک کردن تمام برنامه‌ریزی‌های روز انتخاب‌شده (AJAX)"""
    from .utils import parse_jalali_date

    if request.method != 'POST' or request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'success': False, 'error': 'درخواست نامعتبر'})

    date_str = request.POST.get('date')
    if not date_str:
        return JsonResponse({'success': False, 'error': 'تاریخ ارسال نشده'})

    try:
        target_date = parse_jalali_date(date_str)
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)})

    gregorian = target_date.togregorian()
    tasks = ProductionTask.objects.filter(
        station_name='paint',
        scheduled_start__date=gregorian,
    )
    count = tasks.count()
    tasks.update(scheduled_start=None, scheduled_end=None, assigned_worker=None)
    return JsonResponse({
        'success': True,
        'message': f'{count} تسک از برنامه {target_date.strftime("%Y/%m/%d")} حذف شد.',
        'cleared_count': count,
    })

