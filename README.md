# media-ingest

> **Note:** This plugin was mostly vibed up by Claude. YMMV.

Point it at a folder of media files and it will scan, extract keyframes, analyze visuals using Claude's vision, generate rich tags, and store everything in a searchable catalog.

## What it does

1. **Scans** a folder for supported photo and video formats
2. **Extracts keyframes** from video using ffmpeg (adaptive strategy based on clip length)
3. **Analyzes visuals** via Claude's vision — generates descriptions, semantic tags, mood, shot type, and more
4. **Writes `.meta.json` sidecars** alongside each original file
5. **Stores results** in a central SQLite catalog for fast searching

## Supported formats

**Photos:** `.jpg` `.jpeg` `.png` `.tiff` `.heic` `.heif` `.webp` `.cr2` `.cr3` `.nef` `.arw` `.dng` `.raf`

**Video:** `.mp4` `.mov` `.avi` `.mkv` `.mts` `.m2ts` `.mxf` `.r3d` `.braw`

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- Python 3.10+
- ffmpeg and ffprobe
- Pillow (`pip install Pillow`)

## Installation

Clone the repo into your project and run the setup script:

```bash
git clone https://github.com/michaeldboyd/media-ingest.git
cd media-ingest
./scripts/setup.sh
```

Or manually: ensure `ffmpeg` and `Pillow` are installed, then open Claude Code in any parent directory containing this plugin folder.

## Usage

### Ingest media

```
/ingest /path/to/media/folder
```

Scans the folder, extracts keyframes from video, analyzes everything visually, and builds the catalog. Each file gets a `.meta.json` sidecar with tags, description, and technical metadata. A `media_catalog.db` SQLite database is created at the root of the media folder.

### Search the catalog

```
/search-media sunset ocean
```

Searches tags and descriptions across your catalog and returns matching assets.

### Natural language

The plugin also activates automatically when you say things like:

- "Tag these photos"
- "Process my footage"
- "Catalog this SD card dump"
- "What clips do I have of the city?"

## How tagging works

Each asset gets 10-30 semantic tags across categories like subject matter, environment, lighting, weather, camera/shot type, action, mood, color palette, and production context. Tags are lowercase and hyphenated (`golden-hour`, `slow-motion`, `establishing-shot`).

See `skills/media-ingest/references/tag_taxonomy.md` for the full taxonomy.

## Project structure

```
media-ingest/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest
├── commands/
│   ├── ingest.md                # /ingest slash command
│   └── search-media.md          # /search-media slash command
├── skills/
│   └── media-ingest/
│       ├── SKILL.md             # Core skill (pipeline, tagging guidelines, schema)
│       └── references/
│           └── tag_taxonomy.md  # Tag vocabulary and conventions
└── scripts/
    ├── setup.sh                 # Dependency checker and installer
    ├── scan_media.py            # Media file discovery
    ├── extract_keyframes.py     # FFmpeg keyframe extraction
    └── catalog_db.py            # SQLite catalog management
```

## License

Apache 2.0 — see [LICENSE](LICENSE).
