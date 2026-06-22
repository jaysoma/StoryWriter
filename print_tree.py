import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pymongo import MongoClient

cli = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=4000)
db = cli['SyntaxVision']

BRANCH  = '├── '
LAST    = '└── '
VBAR    = '│   '
SPACE   = '    '

TYPE_ICON = {
    'file':     '📄',
    'function': '⚙️ ',
    'block':    '▣ ',
    'if':       '◈ ',
    'except':   '⚠️ ',
    'loop':     '↺ ',
    'else':     '◇ ',
    'try':      '◎ ',
}

def render(node, prefix='', is_last=True):
    connector = LAST if is_last else BRANCH
    icon = TYPE_ICON.get(node.get('type', ''), '  ')
    hp   = '' if node.get('on_happy_path', True) else '  [branch]'
    name = node.get('name', '?')
    ls, le = node.get('line_start', '?'), node.get('line_end', '?')
    lines = f'  L{ls}–{le}' if ls != '?' else ''
    ann   = node.get('annotation', '')
    short = (ann[:72] + '…') if len(ann) > 75 else ann

    print(f'{prefix}{connector}{icon} {name}{lines}{hp}')
    child_prefix = prefix + (SPACE if is_last else VBAR)
    print(f'{child_prefix}    {short}')

    children = node.get('children', [])
    for i, child in enumerate(children):
        render(child, child_prefix, is_last=(i == len(children) - 1))

for doc in db['ControlFlow'].find({'model': 'claude'}, {'file': 1, 'tree': 1}).sort('file', 1):
    root = doc['tree']
    print(f'\n{"━" * 70}')
    icon = TYPE_ICON.get(root.get('type', 'file'), '📄')
    print(f'{icon} {root["name"]}')
    print('━' * 70)
    children = root.get('children', [])
    for i, child in enumerate(children):
        render(child, '', is_last=(i == len(children) - 1))
    print()
