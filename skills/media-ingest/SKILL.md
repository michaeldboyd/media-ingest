---
name: media-ingest
description: >
  Ingest, catalog, and semantically tag media assets (photos and video) from camera imports.
  Use this skill whenever the user wants to process, tag, describe, catalog, archive, or organize
  media files — even if they just say things like "process my footage", "tag these photos",
  "catalog this SD card dump", "what's in these clips", or "help me organize my camera roll".
  Also trigger when the user mentions keywords like: ingest, media, footage, clips, photos,
  archive, keyframes, visual analysis, or media catalog. This skill handles the full pipeline
  from raw camera files to a searchable, keyword-tagged media library.
---

# Media Ingest — Visual Analysis & Semantic Tagging

This skill processes raw media files (photos and video) and produces a rich, searchable catalog
with semantic keyword tags, natural language descriptions, and technical metadata.

## What It Does

Given a folder of media files, this skill will:

1. **Scan** the folder for supported media types (images and video)
2. **Extract keyframes** from video files using ffmpeg (at smart intervals based on clip length)
3. **Analyze visually** — send keyframes and photos to Claude for description
4. **Generate semantic tags** — expressive, searchable keywords for each asset
5. **Write a natural language description** of what's happening in each clip or photo
6. **Record technical metadata** — resolution, duration, codec, file size, camera info (EXIF)
7. **Store results** as JSON sidecar files alongside originals AND in a central SQLite catalog

## Supported File Types

- **Photos**: .jpg, .jpeg, .png, .tiff, .heic, .heif, .webp, .cr2, .cr3, .nef, .arw, .dng, .raf
- **Video**: .mp4, .mov, .avi, .mkv, .mts, .m2ts, .mxf, .r3d, .braw

## Dependencies

The skill needs these tools available on the system:

- **ffmpeg** — for extracting keyframes and reading video metadata (via ffprobe)
- **Python 3** with: `Pillow` (image handling), `exiftool` or `pillow` for EXIF

If ffmpeg is not installed, the skill will attempt to install it and inform the user.

## How to Use

### Single file
```
"Ingest this clip and tag it" (with file uploaded or path provided)
```

### Batch folder
```
"Process all the footage in /path/to/folder"
"Ingest everything on my SD card at /Volumes/EOS_DIGITAL/DCIM"
```

### Search the catalog
```
"Find all clips tagged with 'sunset'"
"Show me everything from the beach trip"
"What footage do I have of the city skyline?"
```

## Pipeline Steps

### Step 1: Scan & Discover

Scan the target folder (recursively) for supported file types. Build a manifest of files
to process. Skip files that already have a sidecar JSON (unless the user asks to re-process).

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/scan_media.py /path/to/media/folder
```

This produces a `manifest.json` listing all discovered files with basic filesystem metadata.

### Step 2: Extract Technical Metadata

For each file, extract technical metadata:

- **Video**: Use `ffprobe` to get duration, resolution, codec, frame rate, bitrate
- **Photos**: Use Pillow/EXIF to get resolution, camera model, lens, ISO, aperture, shutter speed, GPS coordinates, date taken

### Step 3: Extract Keyframes (Video Only)

For video files, extract representative keyframes using ffmpeg:

- Clips under 10 seconds: extract 3 frames (start, middle, end)
- Clips 10-60 seconds: extract 1 frame every 5 seconds
- Clips 1-5 minutes: extract 1 frame every 15 seconds
- Clips over 5 minutes: extract 1 frame every 30 seconds (max 20 frames)

Store keyframes in a temporary `.keyframes/` directory next to the video file.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract_keyframes.py /path/to/video.mp4 --output-dir /tmp/keyframes/
```

### Step 4: Visual Analysis & Tagging

This is the core intelligence step. For each media file:

1. Load the image (or keyframes for video) into the conversation
2. Analyze the visual content using Claude's vision capabilities
3. Generate the following structured output:

```json
{
  "file": "DJI_0042.MP4",
  "type": "video",
  "description": "Aerial drone shot flying over a coastal town at golden hour. The camera slowly pans from the harbor with small fishing boats to the hillside covered in white and pastel-colored houses. Ocean waves break against a stone seawall. A church steeple is visible on the hilltop. Light cloud cover with warm sunset tones.",
  "tags": [
    "aerial", "drone", "coastal", "town", "golden-hour", "sunset",
    "harbor", "boats", "fishing-boats", "hillside", "houses",
    "ocean", "waves", "seawall", "church", "steeple", "clouds",
    "mediterranean", "cinematic", "slow-pan", "establishing-shot"
  ],
  "scene_type": "exterior/aerial",
  "mood": ["warm", "serene", "cinematic"],
  "time_of_day": "golden hour / sunset",
  "weather": "partly cloudy",
  "motion": "slow pan left-to-right",
  "shot_type": "wide establishing shot",
  "notable_elements": [
    "fishing boats in harbor",
    "pastel hillside houses",
    "church steeple on hilltop",
    "breaking waves on seawall"
  ]
}
```

#### Tagging Guidelines

Tags should be:
- **Specific and concrete** — prefer "golden-retriever" over "dog" (include both if relevant)
- **Multi-level** — include broad categories AND specific details ("animal", "dog", "golden-retriever")
- **Action-oriented** where applicable — "running", "talking", "cooking", "dancing"
- **Descriptive of mood/tone** — "moody", "bright", "dramatic", "intimate"
- **Inclusive of technical shot info** — "close-up", "wide-shot", "handheld", "slow-motion", "timelapse"
- **Lowercase, hyphenated for multi-word** — "time-lapse", "golden-hour", "over-the-shoulder"

Aim for 10-30 tags per asset. More tags = better searchability. Don't be shy.

#### Description Guidelines

Descriptions should read like a script supervisor's notes or a stock footage description:
- Start with the shot type and primary subject
- Describe camera movement if any
- Note lighting, time of day, weather
- Mention notable objects, people (by description, not name — that comes in Phase 3), and actions
- Keep it to 2-4 sentences for photos, 3-6 sentences for video
- Be factual and observational, not interpretive

### Step 5: Write Sidecar JSON

For each processed file, write a `.meta.json` sidecar file alongside the original:

```
DJI_0042.MP4
DJI_0042.MP4.meta.json
```

The sidecar contains the full analysis output plus technical metadata.

### Step 6: Update Central Catalog

Append/update the central SQLite catalog at the root of the media folder:

```
/path/to/media/folder/media_catalog.db
```

Schema:
```sql
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,           -- 'photo' or 'video'
    file_size_bytes INTEGER,
    description TEXT,
    scene_type TEXT,
    mood TEXT,                          -- JSON array
    time_of_day TEXT,
    weather TEXT,
    motion TEXT,
    shot_type TEXT,
    notable_elements TEXT,              -- JSON array
    -- Technical metadata
    duration_seconds REAL,             -- video only
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
    -- Processing metadata
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
```

Use the catalog_db.py script to upsert assets:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/catalog_db.py upsert /path/to/media/folder/media_catalog.db /path/to/asset.meta.json
```

### Searching the Catalog

When the user wants to search their media, use the catalog_db.py search command:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/catalog_db.py search /path/to/media/folder/media_catalog.db "search terms"
```

Or query the SQLite catalog directly:

```sql
-- Find assets by tag
SELECT a.* FROM assets a
JOIN tags t ON a.id = t.asset_id
WHERE t.tag LIKE '%sunset%';

-- Find assets by description
SELECT * FROM assets WHERE description LIKE '%beach%';

-- Combine tag and description search
SELECT DISTINCT a.* FROM assets a
LEFT JOIN tags t ON a.id = t.asset_id
WHERE t.tag LIKE '%ocean%' OR a.description LIKE '%ocean%';
```

Present results in a readable format with the description, top tags, and file path.

## Output Summary

After processing, present a summary to the user:

```
✅ Media Ingest Complete
━━━━━━━━━━━━━━━━━━━━━
📁 Folder: /Volumes/EOS_DIGITAL/DCIM
📊 Processed: 47 files (32 video, 15 photos)
⏭️  Skipped: 3 files (already cataloged)
🏷️  Total tags generated: 892
💾 Catalog: /Volumes/EOS_DIGITAL/DCIM/media_catalog.db

Top tags across this batch:
  #outdoor (28)  #daylight (24)  #nature (19)  #wide-shot (15)  #handheld (12)
```

## Future Phases (Not Yet Implemented)

### Phase 2: Audio Transcription
- Extract audio from video via ffmpeg
- Transcribe with Whisper (with speaker diarization)
- Align transcript timestamps with keyframes
- Add dialogue content to tags and catalog

### Phase 3: Face Detection & Recognition
- Detect faces in keyframes/photos using face_recognition library
- Maintain a known-persons registry with face encodings
- Tag assets with person names
- Link detected faces to speaker diarization segments
- Enable search by person: "show me all clips with Sarah"

## References

For detailed schema information and helper scripts, see:
- `${CLAUDE_PLUGIN_ROOT}/scripts/scan_media.py` — Media file discovery and manifest building
- `${CLAUDE_PLUGIN_ROOT}/scripts/extract_keyframes.py` — FFmpeg-based keyframe extraction
- `${CLAUDE_PLUGIN_ROOT}/scripts/catalog_db.py` — SQLite catalog management
- `${CLAUDE_PLUGIN_ROOT}/skills/media-ingest/references/tag_taxonomy.md` — Detailed tagging taxonomy and guidelines
