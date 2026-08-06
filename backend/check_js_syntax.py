from pathlib import Path
import re

path = Path('api/templates/api/index.html')
text = path.read_text(encoding='utf-8', errors='strict')
# Extract the first <script> block only
script_start = text.find('<script>')
script_end = text.find('</script>', script_start)
if script_start == -1 or script_end == -1:
    raise SystemExit('Script block not found')
script = text[script_start + len('<script>'):script_end]
# Remove HTML comments if any
script = re.sub(r'<!--.*?-->', '', script, flags=re.S)

# Sanity: try parsing with node if available via subprocess
import subprocess
import json

node_cmd = [
    'node',
    '-e',
    "const fs = require('fs'); const path = process.argv[1]; const src = fs.readFileSync(path, 'utf8'); new Function(src); console.log('OK');",
    'temp_script.js'
]

# Write temporary script to avoid quoting issues
Path('temp_script.js').write_text(script, encoding='utf-8')
try:
    result = subprocess.run(node_cmd, capture_output=True, text=True)
    print('node exit', result.returncode)
    print('stdout:', result.stdout)
    print('stderr:', result.stderr)
finally:
    Path('temp_script.js').unlink()
