import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pymongo import MongoClient
cli = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=4000)
d = cli['pipeline_visualizer']['apps'].find_one({})
anns = d.get('annotations', {}).get('annotations', [])
for a in anns:
    print(f"Line {a['line']:3d}: {a['text']}")
