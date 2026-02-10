#!/usr/bin/env python3
"""
scan_media.py — Discover and catalog all supported media files in a folder.

Usage:
    python scan_media.py /path/to/media/folder [--output manifest.json] [--force]

Produces a manifest.json listing every discovered media file with basic
filesystem metadata. Skips files that already have .meta.json sidecars
unless --force is specified.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PHOTO_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.tiff', '.tif',
    '.heic', '.heif', '.webp',
    '.cr2', '.cr3', '.nef', '.arw', '.dng', '.raf'
}

VIDEO_EXTENSIONS = {
    '.mp4', '.mov', '.avi', '.mkv',
    '.mts', '.m2ts', '.mxf',
    '.r3d', '.braw'
}

ALL_EXTENSIONS = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS


def classify_file(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in PHOTO_EXTENSIONS:
        return 'photo'
    elif ext in VIDEO_EXTENSIONS:
        return 'video'
    return None


def has_sidecar(path: Path) -> bool:
    return path.with_name(path.name + '.meta.json').exists()


def scan_folder(folder: Path, force: bool = False) -> list[dict]:
    """Recursively scan folder for media files."""
    manifest = []

    for root, _dirs, files in os.walk(folder):
        # Skip hidden directories and keyframe temp dirs
        root_path = Path(root)
        if any(part.startswith('.') for part in root_path.parts):
            continue

        for fname in sorted(files):
            fpath = root_path / fname

            # Skip hidden files
            if fname.startswith('.'):
                continue

            file_type = classify_file(fpath)
            if file_type is None:
                continue

            already_processed = has_sidecar(fpath)
            if already_processed and not force:
                manifest.append({
                    'filepath': str(fpath.resolve()),
                    'filename': fname,
                    'file_type': file_type,
                    'file_size_bytes': fpath.stat().st_size,
                    'modified': datetime.fromtimestamp(fpath.stat().st_mtime).isoformat(),
                    'status': 'skipped',
                    'reason': 'sidecar exists'
                })
                continue

            manifest.append({
                'filepath': str(fpath.resolve()),
                'filename': fname,
                'file_type': file_type,
                'file_size_bytes': fpath.stat().st_size,
                'modified': datetime.fromtimestamp(fpath.stat().st_mtime).isoformat(),
                'status': 'pending'
            })

    return manifest


def print_summary(manifest: list[dict]) -> None:
    pending = [f for f in manifest if f['status'] == 'pending']
    skipped = [f for f in manifest if f['status'] == 'skipped']
    photos = [f for f in pending if f['file_type'] == 'photo']
    videos = [f for f in pending if f['file_type'] == 'video']

    print(f"\n📁 Media Scan Results")
    print(f"━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Total found:   {len(manifest)}")
    print(f"  To process:    {len(pending)} ({len(photos)} photos, {len(videos)} videos)")
    print(f"  Already done:  {len(skipped)}")

    total_size = sum(f['file_size_bytes'] for f in pending)
    if total_size > 1_000_000_000:
        print(f"  Total size:    {total_size / 1_000_000_000:.1f} GB")
    else:
        print(f"  Total size:    {total_size / 1_000_000:.1f} MB")
    print()


def main():
    parser = argparse.ArgumentParser(description='Scan folder for media files')
    parser.add_argument('folder', type=str, help='Path to media folder')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='Output manifest path (default: <folder>/manifest.json)')
    parser.add_argument('--force', '-f', action='store_true',
                        help='Re-process files that already have sidecars')
    args = parser.parse_args()

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"Error: {folder} is not a directory", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output) if args.output else folder / 'manifest.json'

    manifest = scan_folder(folder, force=args.force)
    print_summary(manifest)

    with open(output_path, 'w') as f:
        json.dump({
            'scan_date': datetime.now().isoformat(),
            'source_folder': str(folder),
            'file_count': len(manifest),
            'files': manifest
        }, f, indent=2)

    print(f"📝 Manifest written to: {output_path}")


if __name__ == '__main__':
    main()
