with open('product/views.py', encoding='utf-8', errors='replace') as f:
    content = f.read()

start = content.find('def painting_workers_view')
end = content.find('def painting_worker_excluded_items', start)
section = content[start:end]

# Find context dict
ctx_start = section.rfind('context = {')
if ctx_start > 0:
    ctx_section = section[ctx_start:ctx_start+800]
    print(ctx_section)
else:
    print("context not found")
