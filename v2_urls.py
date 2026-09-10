from django.urls import path, include

app_name = 'v2'

urlpatterns = [
    path('sales/', include('sales.urls')),
    path('products/', include('products.urls')),
    path('bom/', include('bom.urls')),
    path('inventory/', include('inventory.urls_v2')),
    path('warehouse/', include('warehouse.urls')),
    path('production/', include('production.urls')),
    path('planning/', include('planning.urls')),
    path('painting/', include('painting.urls')),
    path('quality/', include('quality.urls')),
    path('packaging/', include('packaging.urls')),
    path('shipping/', include('shipping.urls')),
    path('reporting/', include('reporting.urls')),
    path('api/', include('v2_api.urls')),
]
