"""Generate local performance input without committing the large CSV."""
import argparse
import csv
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--rows', type=int, default=100000)
parser.add_argument('--output', default='../data/generated.csv')
args = parser.parse_args()
path = Path(args.output)
path.parent.mkdir(parents=True, exist_ok=True)
with path.open('w', newline='', encoding='utf-8') as target:
    writer = csv.writer(target)
    writer.writerow(['indicator', 'type', 'confidence', 'source', 'first_seen'])
    for i in range(args.rows):
        writer.writerow([f'host-{i % 80000}.example', 'domain', i % 101, 'generated', '2026-01-01'])
print(f'Wrote {args.rows} rows to {path}')
