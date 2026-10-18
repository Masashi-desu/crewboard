"""Consistent SQLite snapshot plus local assets; never overwrites a destination."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint(connection):
    content = []
    for name, sql in connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        quoted = '"' + name.replace('"', '""') + '"'
        rows = [list(row) for row in connection.execute('SELECT * FROM ' + quoted)]
        content.append([name,sql,sorted(rows, key=lambda r: json.dumps(r,ensure_ascii=False,default=str))])
    return hashlib.sha256(json.dumps(content,ensure_ascii=False,default=str,sort_keys=True).encode()).hexdigest()


def readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)


def assets(directory):
    return {str(p.relative_to(directory)).replace('\\','/'): digest(p)
            for p in directory.rglob('*') if p.is_file()
            and p.name not in ('jobs.db','jobs.db-wal','jobs.db-shm','manifest.json')
            and p.suffix != '.log'}


def verify(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if digest(directory / 'jobs.db') != manifest['db_sha256'] or assets(directory) != manifest['assets']:
        raise ValueError('backup checksum mismatch')
    connection = readonly(directory / 'jobs.db')
    try:
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('invalid backup DB')
        if fingerprint(connection) != manifest['fingerprint']: raise ValueError('backup fingerprint mismatch')
        for (icon,) in connection.execute("SELECT icon FROM assignees WHERE icon LIKE '/avatars/%'"):
            if 'avatars/' + Path(icon).name not in manifest['assets']: raise ValueError('backup avatar missing')
    finally: connection.close()
    return manifest


def create(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('backup must use a separate directory')
    if destination.exists(): raise ValueError('backup destination already exists')
    before = assets(source)
    destination.mkdir(parents=True)
    connection = readonly(source / 'jobs.db')
    target = sqlite3.connect(destination / 'jobs.db')
    try:
        connection.backup(target)
        snapshot_fingerprint = fingerprint(target)
    finally:
        target.close(); connection.close()
    for name in before:
        path = destination / name; path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, path)
    if before != assets(source) or before != assets(destination):
        raise ValueError('assets changed during backup; discard this incomplete destination and retry')
    manifest = dict(origin_data_dir=str(source), db_sha256=digest(destination / 'jobs.db'),
                    fingerprint=snapshot_fingerprint, assets=before)
    (destination / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    verify(destination)
    return manifest


def restore(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    verify(source)
    if destination.exists(): raise ValueError('restore destination already exists; use a new directory')
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('restore must use a separate directory')
    shutil.copytree(source, destination)
    return verify(destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['create','restore','verify'])
    parser.add_argument('--source', required=True)
    parser.add_argument('--destination')
    args = parser.parse_args()
    if args.operation != 'verify' and not args.destination: parser.error('--destination required')
    result = verify(args.source) if args.operation == 'verify' else globals()[args.operation](args.source,args.destination)
    print(json.dumps(result,ensure_ascii=False,indent=2))
