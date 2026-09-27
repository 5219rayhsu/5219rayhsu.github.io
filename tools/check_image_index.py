"""Verify the image inventory, trilingual labels, paths and unchanged file bytes."""
import hashlib
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
entries = json.loads((root / 'site-data/image-index.json').read_text())['images']
renames = json.loads((root / 'site-data/image-rename-map.json').read_text())
actual = {p.relative_to(root).as_posix() for p in (root / 'assets/img').rglob('*') if p.is_file()}
assert len(entries) == len({e['path'] for e in entries}), 'Duplicate image index paths'
assert actual == {e['path'] for e in entries}, 'Missing or unindexed images'
for entry in entries:
    path = root / entry['path']
    assert path.resolve().is_relative_to((root / 'assets/img').resolve()), entry['path']
    assert re.fullmatch(r'[a-z0-9][a-z0-9.-]*', path.name), path.name
    assert set(entry['names']) == {'zh', 'en', 'ja'} and all(entry['names'].values()), path
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], path
    assert renames.get(entry['old_path'], entry['old_path']) == entry['path'], path
assert set(renames.values()) <= actual, 'Broken rename mapping'
print(f'PASS: {len(entries)} images, English filenames, trilingual labels, paths and SHA-256')
