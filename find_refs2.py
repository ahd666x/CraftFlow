with open('product/templates/painting_management/workers.html', encoding='utf-8', errors='replace') as f:
    content = f.read()
for needle in ['painting_worker_exclusion_api', 'exclusionModal', 'btn-exclusion']:
    idx = 0
    found = 0
    results = []
    while True:
        idx = content.find(needle, idx)
        if idx == -1:
            break
        found += 1
        start = max(0, idx - 150)
        end = min(len(content), idx + 250)
        results.append((found, start, content[start:end]))
        idx += len(needle)
    with open(f'C:/Windows/Temp/kilo/refs_{needle}.txt', 'w', encoding='utf-8') as out:
        out.write(f'Found {found} occurrences of {needle}\n')
        for num, start, snippet in results:
            out.write(f'=== #{num} at pos {start} ===\n')
            out.write(snippet)
            out.write('\n\n')
