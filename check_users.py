import os
with open('product/templates/painting_management/users.html', encoding='utf-8', errors='replace') as f:
    content = f.read()
for line in content.splitlines():
    if '{% url' in line:
        print(line.strip())
