#!/usr/bin/env python3
"""
extract_keyframes.py — Smart keyframe extraction for visual story analysis.

Usage:
    python extract_keyframes.py /path/to/video.mp4 --output-dir /tmp/keyframes/
    python extract_keyframes.py /path/to/video.mp4  # outputs to .keyframes/ next to video
    python extract_keyframes.py /path/to/video.mp4 --strategy scene  # scene detection only
    python extract_keyframes.py /path/to/video.mp4 --strategy interval  # fixed interval only
    python extract_keyframes.py /path/to/video.mp4 --strategy hybrid  # best of both (default)

Extraction Strategies:

  HYBRID (default, recommended):
    Combines scene-change detection with guaranteed minimum frame density.
    Scene detection catches cuts, transitions, and significant visual changes.
    Minimum density ensures slow pans, gradual lighting changes, etc. aren't missed.
    The result is merged and deduplicated so you get the most informative set of frames.

  SCENE:
    Pure scene-change detection using ffmpeg's scene filter.
    Great for edited footage with cuts. May under-sample long static shots.

  INTERVAL:
    Fixed-interval extraction based on clip duration.
    Predictable frame count. May miss important moments between intervals.

Frame Count Philosophy:
    The goal is to extract enough frames to reconstruct the STORY of the clip.
    A human watching the keyframes in sequence should be able to understand
    what happened — not just what the scene looked like at one moment.
    Think of it like a comic strip version of the video.

    For a 60-second clip, ~12-15 frames is usually right.
    For a 5-minute clip, ~25-30 frames captures most narrative beats.
    Scene detection naturally adapts: a fast montage gets more frames,
    a slow landscape pan gets fewer.
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Video metadata helpers
# ---------------------------------------------------------------------------

def get_video_info(video_path: str) -> dict:
    """Get duration and stream info via ffprobe."""
    cmd = [
        'ffprobe', '-v', 'quiet',
        '-print_format', 'json',
        '-show_format', '-show_streams',
        video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        duration = float(data['format']['duration'])

        video_stream = {}
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                video_stream = stream
                break

        return {
            'duration': duration,
            'width': video_stream.get('width'),
            'height': video_stream.get('height'),
            'codec': video_stream.get('codec_name'),
            'frame_rate': video_stream.get('r_frame_rate'),
            'bit_rate': video_stream.get('bit_rate'),
            'format': data.get('format', {}),
        }
    except (subprocess.CalledProcessError, KeyError, json.JSONDecodeError) as e:
        print(f"Error reading video info: {e}", file=sys.stderr)
        sys.exit(1)


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mm or MM:SS.mm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:05.2f}"
    return f"{m:02d}:{s:05.2f}"


# ---------------------------------------------------------------------------
# Strategy: Fixed interval
# ---------------------------------------------------------------------------

def calculate_interval_timestamps(duration: float) -> list[float]:
    """
    Duration-based frame extraction with adaptive density.

    The idea: shorter clips need relatively more frames per second of footage
    because every moment matters. Longer clips can afford lower density
    because there's more redundancy.

    Duration        Interval    Typical frame count
    < 5s            ~1.5s       2-3 frames
    5-30s           3s          3-10 frames
    30s-2min        5s          6-24 frames
    2-10min         10s         12-60 frames (cap 30)
    > 10min         15s         up to 40 frames
    """
    if duration <= 0:
        return [0.1]

    if duration < 5:
        # Very short: start, middle, end
        if duration < 2:
            return [0.1, max(duration - 0.1, 0.2)]
        return [0.1, duration / 2, max(duration - 0.2, duration / 2 + 0.1)]

    elif duration <= 30:
        interval = 3.0
        max_frames = 15
    elif duration <= 120:
        interval = 5.0
        max_frames = 25
    elif duration <= 600:
        interval = 10.0
        max_frames = 30
    else:
        interval = 15.0
        max_frames = 40

    # Generate timestamps, offset slightly from start/end to avoid black frames
    timestamps = []
    t = 0.5
    while t < duration - 0.3:
        timestamps.append(round(t, 2))
        t += interval

    # Always include a frame near the end (last 10% of clip)
    end_frame = duration - min(1.0, duration * 0.05)
    if timestamps and (end_frame - timestamps[-1]) > interval * 0.3:
        timestamps.append(round(end_frame, 2))

    # Cap frame count — if over limit, subsample evenly
    if len(timestamps) > max_frames:
        step = len(timestamps) / max_frames
        timestamps = [timestamps[int(i * step)] for i in range(max_frames)]

    # Guarantee minimum of 2 frames
    if len(timestamps) < 2 and duration > 1:
        timestamps = [0.5, max(duration - 0.5, 1.0)]

    return timestamps


# ---------------------------------------------------------------------------
# Strategy: Scene detection
# ---------------------------------------------------------------------------

def detect_scene_changes(video_path: str, duration: float,
                         threshold: float = 0.3,
                         min_frames: int = 3,
                         max_frames: int = 40) -> list[float]:
    """
    Use ffmpeg's scene detection to find frames where the visual content
    changes significantly (cuts, transitions, major movement).

    The threshold (0.0-1.0) controls sensitivity:
      0.2 = very sensitive, catches subtle changes
      0.3 = balanced (default)
      0.5 = only catches hard cuts

    If scene detection finds too few frames (common for single-shot footage),
    we fall back to interval-based extraction for those gaps.
    """
    # Adaptive threshold based on duration — longer clips can afford to be pickier
    if duration > 300:
        threshold = max(threshold, 0.35)

    cmd = [
        'ffmpeg', '-i', video_path,
        '-vf', f"select='gt(scene,{threshold})',showinfo",
        '-vsync', 'vfr',
        '-f', 'null', '-'
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        stderr_output = result.stderr
    except subprocess.TimeoutExpired:
        print("  ⚠ Scene detection timed out, falling back to interval", file=sys.stderr)
        return []
    except subprocess.CalledProcessError:
        print("  ⚠ Scene detection failed, falling back to interval", file=sys.stderr)
        return []

    # Parse timestamps from ffmpeg showinfo output
    # Lines look like: [Parsed_showinfo_1 ...] n:   0 pts:  12345 pts_time:1.234 ...
    timestamps = []
    for line in stderr_output.split('\n'):
        match = re.search(r'pts_time:(\d+\.?\d*)', line)
        if match:
            ts = float(match.group(1))
            if 0.1 < ts < (duration - 0.1):
                timestamps.append(round(ts, 2))

    # Deduplicate and sort
    timestamps = sorted(set(timestamps))

    # Cap at max
    if len(timestamps) > max_frames:
        step = len(timestamps) / max_frames
        timestamps = [timestamps[int(i * step)] for i in range(max_frames)]

    return timestamps


# ---------------------------------------------------------------------------
# Strategy: Hybrid (recommended)
# ---------------------------------------------------------------------------

def hybrid_timestamps(video_path: str, duration: float,
                      scene_threshold: float = 0.3) -> list[float]:
    """
    Best-of-both: scene detection for narrative beats + minimum interval
    density so we don't miss slow changes.

    Algorithm:
    1. Run scene detection to find visual change points
    2. Calculate a minimum-density interval grid
    3. Merge both lists
    4. Deduplicate (remove timestamps within 1.5s of each other)
    5. Always include first and last frames

    This ensures:
    - Hard cuts and transitions are always captured (scene detection)
    - Slow pans, gradual lighting changes aren't missed (interval grid)
    - Static shots don't generate excessive redundant frames (dedup)
    """
    print("  🔍 Running scene detection...")
    scene_timestamps = detect_scene_changes(video_path, duration, scene_threshold)
    print(f"     Found {len(scene_timestamps)} scene changes")

    # Minimum density: at least 1 frame every N seconds, depending on duration
    if duration < 30:
        min_interval = 4.0
    elif duration < 120:
        min_interval = 8.0
    elif duration < 600:
        min_interval = 12.0
    else:
        min_interval = 20.0

    density_timestamps = []
    t = 0.5
    while t < duration - 0.3:
        density_timestamps.append(round(t, 2))
        t += min_interval

    # Merge both lists
    all_timestamps = sorted(set(scene_timestamps + density_timestamps))

    # Always include near-start and near-end
    if all_timestamps and all_timestamps[0] > 1.0:
        all_timestamps.insert(0, 0.3)
    end_frame = round(duration - min(0.5, duration * 0.03), 2)
    if all_timestamps and (end_frame - all_timestamps[-1]) > 1.5:
        all_timestamps.append(end_frame)

    # Deduplicate: remove timestamps within 1.5s of each other
    # Prefer scene-detected timestamps (they're more meaningful)
    scene_set = set(scene_timestamps)
    deduplicated = []
    for ts in all_timestamps:
        if not deduplicated:
            deduplicated.append(ts)
            continue
        gap = ts - deduplicated[-1]
        if gap >= 1.5:
            deduplicated.append(ts)
        elif ts in scene_set and deduplicated[-1] not in scene_set:
            # Replace the interval frame with the scene-detected one
            deduplicated[-1] = ts

    # Final cap
    max_frames = 40 if duration > 300 else 30
    if len(deduplicated) > max_frames:
        step = len(deduplicated) / max_frames
        deduplicated = [deduplicated[int(i * step)] for i in range(max_frames)]

    # Guarantee minimum of 2
    if len(deduplicated) < 2 and duration > 1:
        deduplicated = [0.3, round(max(duration - 0.5, 0.6), 2)]

    print(f"     Merged to {len(deduplicated)} frames (scene + density, deduplicated)")
    return deduplicated


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------

def extract_frames(video_path: str, timestamps: list[float],
                   output_dir: str) -> list[dict]:
    """Extract JPEG frames at specified timestamps."""
    os.makedirs(output_dir, exist_ok=True)
    frames = []

    for i, ts in enumerate(timestamps, 1):
        output_file = os.path.join(output_dir, f"frame_{i:03d}.jpg")
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(ts),
            '-i', video_path,
            '-frames:v', '1',
            '-q:v', '2',  # High quality JPEG
            output_file
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            frames.append({
                'index': i,
                'timestamp_seconds': ts,
                'timestamp_formatted': format_timestamp(ts),
                'path': os.path.abspath(output_file)
            })
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr[:200] if e.stderr else 'unknown error'
            print(f"  ⚠ Failed to extract frame at {ts}s: {err_msg}", file=sys.stderr)

    return frames


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Smart keyframe extraction for visual story analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Strategies:
  hybrid    Scene detection + minimum density grid (default, recommended)
  scene     Pure scene-change detection
  interval  Fixed-interval based on duration

Examples:
  %(prog)s video.mp4                          # hybrid, default output dir
  %(prog)s video.mp4 -s scene -t 0.2          # sensitive scene detection
  %(prog)s video.mp4 -s interval -o ./frames  # interval, custom output
        """
    )
    parser.add_argument('video', type=str, help='Path to video file')
    parser.add_argument('--output-dir', '-o', type=str, default=None,
                        help='Output directory for keyframes')
    parser.add_argument('--strategy', '-s', type=str, default='hybrid',
                        choices=['hybrid', 'scene', 'interval'],
                        help='Extraction strategy (default: hybrid)')
    parser.add_argument('--threshold', '-t', type=float, default=0.3,
                        help='Scene detection threshold 0.0-1.0 (default: 0.3)')
    args = parser.parse_args()

    video_path = Path(args.video).resolve()
    if not video_path.is_file():
        print(f"Error: {video_path} not found", file=sys.stderr)
        sys.exit(1)

    # Default output dir
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = video_path.parent / '.keyframes' / video_path.stem

    # Check ffmpeg
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except FileNotFoundError:
        print("Error: ffmpeg not found. Please install ffmpeg.", file=sys.stderr)
        print("  macOS:   brew install ffmpeg", file=sys.stderr)
        print("  Ubuntu:  sudo apt install ffmpeg", file=sys.stderr)
        sys.exit(1)

    # Get video info
    info = get_video_info(str(video_path))
    duration = info['duration']

    print(f"🎬 Processing: {video_path.name}")
    print(f"   Duration:   {format_timestamp(duration)} ({duration:.1f}s)")
    print(f"   Resolution: {info['width']}x{info['height']}")
    print(f"   Strategy:   {args.strategy}")

    # Calculate timestamps based on strategy
    if args.strategy == 'hybrid':
        timestamps = hybrid_timestamps(str(video_path), duration, args.threshold)
    elif args.strategy == 'scene':
        timestamps = detect_scene_changes(str(video_path), duration, args.threshold)
        if len(timestamps) < 2:
            print("  ⚠ Too few scene changes detected, adding interval frames")
            interval_ts = calculate_interval_timestamps(duration)
            timestamps = sorted(set(timestamps + interval_ts))
    else:
        timestamps = calculate_interval_timestamps(duration)

    print(f"\n   Extracting {len(timestamps)} keyframes...")

    # Extract frames
    frames = extract_frames(str(video_path), timestamps, str(output_dir))

    # Build metadata
    result = {
        'source_video': str(video_path),
        'duration_seconds': duration,
        'extraction_strategy': args.strategy,
        'scene_threshold': args.threshold if args.strategy != 'interval' else None,
        'frame_count': len(frames),
        'video_metadata': {
            'codec': info['codec'],
            'width': info['width'],
            'height': info['height'],
            'frame_rate': info['frame_rate'],
            'bit_rate': info.get('bit_rate'),
        },
        'format_metadata': {
            'format_name': info['format'].get('format_name'),
            'size_bytes': int(info['format'].get('size', 0)),
            'bit_rate': info['format'].get('bit_rate'),
        },
        'frames': frames
    }

    # Write info file
    info_path = output_dir / 'keyframes_info.json'
    with open(info_path, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"\n   ✅ Extracted {len(frames)} frames to: {output_dir}")
    print(f"   📝 Info: {info_path}")
    print()

    # Summary table
    print(f"   {'#':<4} {'Time':<12} {'File':<20}")
    print(f"   {'─'*4} {'─'*12} {'─'*20}")
    for frame in frames:
        print(f"   {frame['index']:<4} {frame['timestamp_formatted']:<12} {Path(frame['path']).name}")

    # Print density stats
    if len(frames) >= 2:
        gaps = [frames[i+1]['timestamp_seconds'] - frames[i]['timestamp_seconds']
                for i in range(len(frames)-1)]
        avg_gap = sum(gaps) / len(gaps)
        min_gap = min(gaps)
        max_gap = max(gaps)
        print(f"\n   Frame density:")
        print(f"     Average gap: {avg_gap:.1f}s")
        print(f"     Min gap:     {min_gap:.1f}s")
        print(f"     Max gap:     {max_gap:.1f}s")
        print(f"     Coverage:    {frames[-1]['timestamp_seconds'] - frames[0]['timestamp_seconds']:.1f}s "
              f"of {duration:.1f}s ({(frames[-1]['timestamp_seconds'] - frames[0]['timestamp_seconds'])/duration*100:.0f}%)")


if __name__ == '__main__':
    main()
