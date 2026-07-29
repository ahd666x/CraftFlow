with open('product/views.py', encoding='utf-8', errors='replace') as f:
    content = f.read()

idx = content.find('def painting_worker_exclusion_api(')
with open('C:/Windows/Temp/kilo/exclusion_view_content.txt', 'w', encoding='utf-8') as out:
    out.write(content[idx:idx+800])

idx2 = content.find('def search_products_api(')
with open('C:/Windows/Temp/kilo/search_view.txt', 'w', encoding='utf-8') as out:
    out.write(content[idx2:idx2+400])

# Also find URL patterns for painting/ workers
idx3 = content.find('urlpatterns')
# Skip to second occurrence (the urls.py file, not views.py)
out2 = open('C:/Windows/Temp/kilo/urls_content.txt', 'w', encoding='utf-8')
with open('product/urls.py', encoding='utf-8') as f2:
    urls_content = f2.read()
out2.write(urls_content[:6000])
out2.close()

print('Done - check C:/Windows/Temp/kilo/')
