import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pymongo import MongoClient
import json

cli = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=4000)
db = cli['SyntaxVision']

def print_tree(node, depth=0):
    indent = '  ' * depth
    hp = 'HAPPY' if node.get('on_happy_path') else 'branch'
    lines = f"L{node.get('line_start','?')}-{node.get('line_end','?')}"
    print(f"{indent}[{hp}] {node['type'].upper():8s} {node['name']:30s} {lines}")
    print(f"{indent}         {node['annotation'][:90]}")
    for child in node.get('children', []):
        print_tree(child, depth + 1)

for doc in db['ControlFlow'].find({'model': 'claude'}, {'file':1, 'tree':1}):
    print(f"\n{'='*60}")
    print(f"FILE: {doc['file']}")
    print('='*60)
    for child in doc['tree'].get('children', []):
        print_tree(child, 1)
