#!/usr/bin/env python3
"""
catalog_db.py — SQLite catalog management for the media ingest skill.

Usage:
    # Initialize or update the catalog with a processed asset
    python catalog_db.py upsert /path/to/catalog.db /path/to/asset.meta.json

    # Search the catalog
    python catalog_db.py search /path/to/catalog.db "sunset ocean"

    # Show stats
    python catalog_db.py stats /path/to/catalog.db

    # List all tags
    python catalog_db.py tags /path/to/catalog.db

    # Export catalog as JSON
    python catalog_db.py export /path/to/catalog.db [--output catalog.json]
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size_bytes INTEGER,
    description TEXT,
    scene_type TEXT,
    mood TEXT,
    time_of_day TEXT,
    weather TEXT,
    motion TEXT,
    shot_type TEXT,
    notable_elements TEXT,
    duration_seconds REAL,
    resolution_width INTEGER,
    resolution_height INTEGER,
    codec TEXT,
    frame_rate REAL,
    camera_model TEXT,
    lens TEXT,
    iso INTEGER,
    aperture TEXT,
    shutter_speed TEXT,
    gps_lat REAL,
    gps_lon REAL,
    date_taken TEXT,
    processed_at TEXT,
    keyframe_count INTEGER
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id),
    UNIQUE(asset_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);
CREATE INDEX IF NOT EXISTS idx_assets_filepath ON assets(filepath);
CREATE INDEX IF NOT EXISTS idx_assets_file_type ON assets(file_type);
CREATE INDEX IF NOT EXISTS idx_assets_date_taken ON assets(date_taken);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize the database and return a connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


def upsert_asset(conn: sqlite3.Connection, meta: dict) -> int:
    """Insert or update an asset from its .meta.json data. Returns the asset ID."""
    technical = meta.get('technical_metadata', {})

    # Build the values dict
    values = {
        'filepath': meta.get('filepath', ''),
        'filename': meta.get('filename', ''),
        'file_type': meta.get('type', meta.get('file_type', '')),
        'file_size_bytes': technical.get('file_size_bytes'),
        'description': meta.get('description', ''),
        'scene_type': meta.get('scene_type', ''),
        'mood': json.dumps(meta.get('mood', [])),
        'time_of_day': meta.get('time_of_day', ''),
        'weather': meta.get('weather', ''),
        'motion': meta.get('motion', ''),
        'shot_type': meta.get('shot_type', ''),
        'notable_elements': json.dumps(meta.get('notable_elements', [])),
        'duration_seconds': technical.get('duration_seconds'),
        'resolution_width': technical.get('width', technical.get('resolution_width')),
        'resolution_height': technical.get('height', technical.get('resolution_height')),
        'codec': technical.get('codec', ''),
        'frame_rate': technical.get('frame_rate'),
        'camera_model': technical.get('camera_model', ''),
        'lens': technical.get('lens', ''),
        'iso': technical.get('iso'),
        'aperture': technical.get('aperture', ''),
        'shutter_speed': technical.get('shutter_speed', ''),
        'gps_lat': technical.get('gps_lat'),
        'gps_lon': technical.get('gps_lon'),
        'date_taken': technical.get('date_taken', ''),
        'processed_at': meta.get('processed_at', datetime.now().isoformat()),
        'keyframe_count': meta.get('keyframe_count', 0),
    }

    # Upsert the asset
    columns = ', '.join(values.keys())
    placeholders = ', '.join(['?'] * len(values))
    update_clause = ', '.join([f'{k}=excluded.{k}' for k in values.keys() if k != 'filepath'])

    conn.execute(
        f"""INSERT INTO assets ({columns}) VALUES ({placeholders})
            ON CONFLICT(filepath) DO UPDATE SET {update_clause}""",
        list(values.values())
    )

    # Get the asset ID
    cursor = conn.execute("SELECT id FROM assets WHERE filepath = ?", (values['filepath'],))
    asset_id = cursor.fetchone()['id']

    # Replace tags
    conn.execute("DELETE FROM tags WHERE asset_id = ?", (asset_id,))
    tags = meta.get('tags', [])
    for tag in tags:
        conn.execute(
            "INSERT OR IGNORE INTO tags (asset_id, tag) VALUES (?, ?)",
            (asset_id, tag.lower().strip())
        )

    conn.commit()
    return asset_id


def search_catalog(conn: sqlite3.Connection, query: str) -> list[dict]:
    """Search the catalog by tags and descriptions."""
    terms = query.lower().split()
    if not terms:
        return []

    # Build WHERE clause: each term must match in tags OR description
    conditions = []
    params = []
    for term in terms:
        conditions.append(
            "(t.tag LIKE ? OR a.description LIKE ? OR a.scene_type LIKE ?)"
        )
        like_term = f"%{term}%"
        params.extend([like_term, like_term, like_term])

    where_clause = " AND ".join(conditions)

    sql = f"""
        SELECT a.*,
               (SELECT GROUP_CONCAT(tag, ', ') FROM tags WHERE asset_id = a.id) as all_tags
        FROM assets a
        LEFT JOIN tags t ON a.id = t.asset_id
        WHERE {where_clause}
        GROUP BY a.id
        ORDER BY a.date_taken DESC, a.processed_at DESC
    """

    cursor = conn.execute(sql, params)
    results = []
    for row in cursor:
        results.append(dict(row))
    return results


def show_stats(conn: sqlite3.Connection) -> None:
    """Print catalog statistics."""
    total = conn.execute("SELECT COUNT(*) as n FROM assets").fetchone()['n']
    photos = conn.execute("SELECT COUNT(*) as n FROM assets WHERE file_type='photo'").fetchone()['n']
    videos = conn.execute("SELECT COUNT(*) as n FROM assets WHERE file_type='video'").fetchone()['n']
    tag_count = conn.execute("SELECT COUNT(DISTINCT tag) as n FROM tags").fetchone()['n']
    total_tags = conn.execute("SELECT COUNT(*) as n FROM tags").fetchone()['n']

    print(f"\n📊 Media Catalog Stats")
    print(f"━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Total assets:   {total}")
    print(f"  Photos:         {photos}")
    print(f"  Videos:         {videos}")
    print(f"  Unique tags:    {tag_count}")
    print(f"  Total tag uses: {total_tags}")

    # Top tags
    cursor = conn.execute("""
        SELECT tag, COUNT(*) as cnt
        FROM tags
        GROUP BY tag
        ORDER BY cnt DESC
        LIMIT 15
    """)
    print(f"\n  Top tags:")
    for row in cursor:
        print(f"    #{row['tag']} ({row['cnt']})")
    print()


def list_tags(conn: sqlite3.Connection) -> None:
    """List all unique tags with counts."""
    cursor = conn.execute("""
        SELECT tag, COUNT(*) as cnt
        FROM tags
        GROUP BY tag
        ORDER BY tag
    """)
    for row in cursor:
        print(f"  #{row['tag']} ({row['cnt']})")


def export_catalog(conn: sqlite3.Connection, output_path: str) -> None:
    """Export entire catalog as JSON."""
    assets = []
    cursor = conn.execute("SELECT * FROM assets ORDER BY date_taken DESC")
    for row in cursor:
        asset = dict(row)
        # Get tags for this asset
        tag_cursor = conn.execute(
            "SELECT tag FROM tags WHERE asset_id = ? ORDER BY tag",
            (asset['id'],)
        )
        asset['tags'] = [t['tag'] for t in tag_cursor]
        # Parse JSON fields
        for field in ('mood', 'notable_elements'):
            if asset.get(field):
                try:
                    asset[field] = json.loads(asset[field])
                except json.JSONDecodeError:
                    pass
        assets.append(asset)

    with open(output_path, 'w') as f:
        json.dump({'assets': assets, 'exported_at': datetime.now().isoformat()}, f, indent=2)

    print(f"📤 Exported {len(assets)} assets to {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Media catalog management')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # upsert
    p_upsert = subparsers.add_parser('upsert', help='Add/update asset from .meta.json')
    p_upsert.add_argument('db_path', help='Path to SQLite database')
    p_upsert.add_argument('meta_json', help='Path to .meta.json file')

    # search
    p_search = subparsers.add_parser('search', help='Search the catalog')
    p_search.add_argument('db_path', help='Path to SQLite database')
    p_search.add_argument('query', help='Search terms')

    # stats
    p_stats = subparsers.add_parser('stats', help='Show catalog statistics')
    p_stats.add_argument('db_path', help='Path to SQLite database')

    # tags
    p_tags = subparsers.add_parser('tags', help='List all tags')
    p_tags.add_argument('db_path', help='Path to SQLite database')

    # export
    p_export = subparsers.add_parser('export', help='Export catalog as JSON')
    p_export.add_argument('db_path', help='Path to SQLite database')
    p_export.add_argument('--output', '-o', default='catalog_export.json')

    args = parser.parse_args()
    conn = init_db(args.db_path)

    if args.command == 'upsert':
        with open(args.meta_json) as f:
            meta = json.load(f)
        asset_id = upsert_asset(conn, meta)
        print(f"✅ Upserted asset #{asset_id}: {meta.get('filename', 'unknown')}")

    elif args.command == 'search':
        results = search_catalog(conn, args.query)
        if not results:
            print(f"No results for: {args.query}")
        else:
            print(f"\n🔍 {len(results)} result(s) for: {args.query}\n")
            for r in results:
                print(f"  📄 {r['filename']}  ({r['file_type']})")
                print(f"     {r['description'][:120]}...")
                print(f"     Tags: {r['all_tags']}")
                print(f"     Path: {r['filepath']}")
                print()

    elif args.command == 'stats':
        show_stats(conn)

    elif args.command == 'tags':
        list_tags(conn)

    elif args.command == 'export':
        export_catalog(conn, args.output)

    conn.close()


if __name__ == '__main__':
    main()
