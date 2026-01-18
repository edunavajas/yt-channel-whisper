#!/usr/bin/env python3
"""
Channel video indexer - enumerates all videos from a YouTube channel without API keys.
Uses yt-dlp to scrape channel video list and produces a JSONL index.
"""
import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def sanitize_filename(filename: str) -> str:
    """Sanitize filenames for Windows compatibility."""
    invalid_chars = '<>:"|?*'
    for char in invalid_chars:
        filename = filename.replace(char, "_")
    return filename


def index_channel(channel_url: str, output_path: Path) -> None:
    """
    Index all videos from a YouTube channel using yt-dlp.
    
    Args:
        channel_url: YouTube channel URL (videos page)
        output_path: Path to output JSONL file
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Indexing channel: {channel_url}")
    
    # Prepare yt-dlp command
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-single-json",
        "--skip-download",
        "--no-warnings",
        "--extractor-args", "youtube:skip=authcheck",
        channel_url,
    ]
    
    logger.debug(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"yt-dlp failed with exit code {e.returncode}")
        logger.error(f"stderr: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        logger.error("yt-dlp not found. Please install it: pip install yt-dlp")
        sys.exit(1)
    
    # Parse JSON output
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse yt-dlp JSON output: {e}")
        logger.debug(f"Output: {result.stdout[:500]}")
        sys.exit(1)
    
    # Extract video entries
    entries = data.get("entries", [])
    if not entries:
        logger.warning("No videos found in channel")
        return
    
    logger.info(f"Found {len(entries)} videos")
    
    # Write JSONL output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    video_count = 0
    with output_path.open("w", encoding="utf-8") as f:
        for entry in entries:
            if not entry:  # Skip None entries
                continue
            
            video_id = entry.get("id")
            if not video_id:
                logger.warning("Skipping entry without ID")
                continue
            
            video_data = {
                "video_id": video_id,
                "title": entry.get("title", "Unknown"),
                "url": entry.get("url") or f"https://www.youtube.com/watch?v={video_id}",
                "upload_date": entry.get("upload_date"),
                "duration": entry.get("duration"),
                "view_count": entry.get("view_count"),
                "channel": entry.get("channel"),
                "channel_id": entry.get("channel_id"),
            }
            
            f.write(json.dumps(video_data, ensure_ascii=False) + "\n")
            video_count += 1
    
    logger.info(f"Wrote {video_count} videos to {output_path}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Index all videos from a YouTube channel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/channel_index.py --channel-url "https://www.youtube.com/@handle/videos" --out data/videos.jsonl
  python tools/channel_index.py --channel-url "https://www.youtube.com/c/ChannelName/videos" --out data/videos.jsonl
        """,
    )
    parser.add_argument(
        "--channel-url",
        required=True,
        help="YouTube channel URL (e.g., https://www.youtube.com/@handle/videos)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/videos.jsonl"),
        help="Output JSONL file path (default: data/videos.jsonl)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    
    index_channel(args.channel_url, args.out)


if __name__ == "__main__":
    main()
