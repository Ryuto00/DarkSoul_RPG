#!/usr/bin/env python3

import re

# Read the file
with open('main.py', 'r') as f:
    content = f.read()

# Fix method definitions that are not properly indented
# Look for method definitions at start of line and add 4 spaces
lines = content.split('\n')
fixed_lines = []

for i, line in enumerate(lines):
    # Check if this is a method definition that needs fixing
    if line.startswith('def _load_static_level') or line.startswith('def _load_pcg_level'):
        # Add 4 spaces to properly indent as class method
        fixed_lines.append('    ' + line)
    else:
        fixed_lines.append(line)

# Write back
with open('main.py', 'w') as f:
    f.write('\n'.join(fixed_lines))

print("Fixed indentation")