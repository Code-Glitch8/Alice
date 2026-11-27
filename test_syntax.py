import ast
try:
    with open('D:\alicegit\alice\planner\ai_planner.py') as f:
        ast.parse(f.read())
    print('Syntax OK')
except SyntaxError as e:
    print(f'Error at line {e.lineno}: {e.text}')
    import sys
    sys.exit(1)