---
description: Scan and catalog media files with semantic tags and descriptions
argument-hint: [path-to-file-or-folder]
allowed-tools:
  - Bash(python3:*)
  - Bash(python:*)
  - Bash(ffmpeg:*)
  - Bash(ffprobe:*)
  - Read
  - Write
  - Glob
  - Grep
---

Ingest media at the specified path: $ARGUMENTS

Follow the media-ingest skill instructions to process this path. The full pipeline is:

1. **Scan** for supported media files using the scanner script:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/scan_media.py $ARGUMENTS
   ```

2. **Extract keyframes** from any video files found (use hybrid strategy):
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract_keyframes.py <video_path> --strategy hybrid
   ```

3. **Analyze visuals** — load each image or set of keyframes into the conversation and generate semantic tags and descriptions using Claude's vision capabilities. Follow the tagging guidelines and tag taxonomy defined in the media-ingest skill. Aim for 10-30 tags per asset.

4. **Write .meta.json sidecars** alongside each original file with the full analysis output (description, tags, scene_type, mood, time_of_day, weather, motion, shot_type, notable_elements, plus technical metadata).

5. **Update the catalog database** for each processed asset:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/catalog_db.py upsert <db_path> <meta_json_path>
   ```
   The catalog database lives at `media_catalog.db` in the root of the media folder being processed.

6. **Present a summary** showing files processed (photos vs video), files skipped, total tags generated, and the catalog database path.
