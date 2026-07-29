with open('product/templates/painting_management/workers.html', encoding='utf-8', errors='replace') as f:
    content = f.read()
for needle in ['painting_worker_exclusion_api', 'exclusion_api', 'exclusionModal', 'btn-exclusion']:
    idx = 0
    found = 0
    while True:
        idx = content.find(needle, idx)
        if idx == -1:
            break
        found += 1
        start = max(0, idx - 200)
        end = min(len(content), idx + 300)
        print(f'=== {needle} (#{found}) ===')
        print(repr(content[start:end]))
        print()
        idx += len(needle)
    if found == 0:
        print(f'{needle}: NOT FOUND')
