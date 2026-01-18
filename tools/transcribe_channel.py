#!/usr/bin/env python3
"""
Channel transcriber - downloads audio and transcribes using local speaches service.
Supports resumable processing, retries, and concurrent transcription.
"""
import argparse
import json
import logging
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx
from tqdm import tqdm


@dataclass
class TranscriptionConfig:
    """Configuration for transcription service."""
    base_url: str
    endpoint: str
    mode: str  # "openai" or "generic"
    model: str
    language: str
    timeout: int


@dataclass
class VideoTask:
    """Video processing task."""
    video_id: str
    title: str
    url: str
    output_dir: Path


def setup_logging(log_file: Optional[Path] = None, verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def sanitize_filename(filename: str) -> str:
    """Sanitize filenames for Windows compatibility."""
    invalid_chars = '<>:"|?*\\/'
    for char in invalid_chars:
        filename = filename.replace(char, "_")
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    return filename


def load_videos(input_path: Path) -> list[dict[str, Any]]:
    """Load videos from JSONL file."""
    logger = logging.getLogger(__name__)
    videos = []
    
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        sys.exit(1)
    
    with input_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                video = json.loads(line)
                videos.append(video)
            except json.JSONDecodeError as e:
                logger.warning(f"Skipping invalid JSON at line {line_num}: {e}")
    
    logger.info(f"Loaded {len(videos)} videos from {input_path}")
    return videos


def download_audio(video_url: str, output_path: Path, cache_dir: Path) -> bool:
    """
    Download audio from YouTube video using yt-dlp.
    
    Args:
        video_url: YouTube video URL
        output_path: Path to save audio file
        cache_dir: Cache directory for yt-dlp
    
    Returns:
        True if successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    if output_path.exists():
        logger.debug(f"Audio already exists: {output_path}")
        return True
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Use yt-dlp to download best audio
    cmd = [
        "yt-dlp",
        "-f", "bestaudio/best",
        "-x",  # Extract audio
        "--audio-format", "mp3",
        "--audio-quality", "0",  # Best quality
        "-o", str(output_path.with_suffix(".%(ext)s")),
        "--cache-dir", str(cache_dir),
        "--no-warnings",
        "--no-playlist",
        video_url,
    ]
    
    logger.debug(f"Downloading audio: {' '.join(cmd)}")
    
    try:
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
        
        # yt-dlp adds .mp3 extension
        actual_path = output_path.with_suffix(".mp3")
        if actual_path != output_path:
            actual_path.rename(output_path)
        
        if output_path.exists():
            logger.debug(f"Downloaded: {output_path}")
            return True
        else:
            logger.error(f"Download completed but file not found: {output_path}")
            return False
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Download failed: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Download error: {e}")
        return False


def transcribe_audio_openai_style(
    audio_path: Path,
    config: TranscriptionConfig,
    client: httpx.Client,
) -> Optional[dict[str, Any]]:
    """
    Transcribe audio using OpenAI-compatible API endpoint.
    
    Args:
        audio_path: Path to audio file
        config: Transcription configuration
        client: HTTP client
    
    Returns:
        Transcription result dict or None if failed
    """
    logger = logging.getLogger(__name__)
    url = f"{config.base_url.rstrip('/')}{config.endpoint}"
    
    logger.debug(f"Transcribing via OpenAI-style API: {url}")
    
    try:
        with audio_path.open("rb") as audio_file:
            files = {"file": (audio_path.name, audio_file, "audio/mpeg")}
            data = {
                "model": config.model,
                "language": config.language,
                "task": "transcribe",  # CRITICAL: Force transcribe, not translate
                "translate": "false",   # Some servers honor this flag to disable translation
                "output_language": config.language,  # Some servers use this instead of language
                "response_format": "verbose_json",
            }
            
            # Add initial_prompt to help force language detection
            # This is a hint for Whisper models
            if config.language == "es":
                data["initial_prompt"] = "Transcribe en español sin traducir. No traduzcas. Mantén el idioma original."
            elif config.language == "en":
                data["initial_prompt"] = "Transcribe in English without translating. Do not translate."
            
            logger.info(
                f"Sending transcription request: model={config.model}, language={config.language}, "
                "task=transcribe, translate=false"
            )
            
            response = client.post(
                url,
                files=files,
                data=data,
                timeout=config.timeout,
            )
            response.raise_for_status()
            
            result = response.json()
            detected_lang = result.get("language", "unknown")
            logger.info(f"Transcription successful: {len(result.get('text', ''))} chars, detected_language={detected_lang}")
            
            # Warn if language mismatch
            if detected_lang != config.language and detected_lang != "unknown":
                logger.warning(f"Language mismatch! Requested={config.language}, Detected={detected_lang}")
            
            return result
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.debug(f"Endpoint not found (404), will try fallback")
            return None
        logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return None


def transcribe_audio_generic_style(
    audio_path: Path,
    config: TranscriptionConfig,
    client: httpx.Client,
) -> Optional[dict[str, Any]]:
    """
    Transcribe audio using generic API endpoint.
    
    Args:
        audio_path: Path to audio file
        config: Transcription configuration
        client: HTTP client
    
    Returns:
        Transcription result dict or None if failed
    """
    logger = logging.getLogger(__name__)
    url = f"{config.base_url.rstrip('/')}/transcribe"
    
    logger.debug(f"Transcribing via generic API: {url}")
    
    try:
        with audio_path.open("rb") as audio_file:
            files = {"file": (audio_path.name, audio_file, "audio/mpeg")}
            data = {
                "model": config.model,
                "language": config.language,
                "task": "transcribe",  # CRITICAL: Force transcribe, not translate
                "translate": "false",   # Some servers honor this flag to disable translation
                "output_language": config.language,  # Some servers use this instead of language
            }
            
            # Add initial_prompt to help force language detection
            if config.language == "es":
                data["initial_prompt"] = "Transcribe en español sin traducir. No traduzcas. Mantén el idioma original."
            elif config.language == "en":
                data["initial_prompt"] = "Transcribe in English without translating. Do not translate."
            
            logger.info(
                f"Sending transcription request: model={config.model}, language={config.language}, "
                "task=transcribe, translate=false"
            )
            
            response = client.post(
                url,
                files=files,
                data=data,
                timeout=config.timeout,
            )
            response.raise_for_status()
            
            result = response.json()
            detected_lang = result.get("language", "unknown")
            logger.info(f"Transcription successful: {len(result.get('text', ''))} chars, detected_language={detected_lang}")
            
            # Warn if language mismatch
            if detected_lang != config.language and detected_lang != "unknown":
                logger.warning(f"Language mismatch! Requested={config.language}, Detected={detected_lang}")
            
            return result
            
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return None


def transcribe_audio(
    audio_path: Path,
    config: TranscriptionConfig,
) -> Optional[dict[str, Any]]:
    """
    Transcribe audio using configured service with automatic fallback.
    
    Args:
        audio_path: Path to audio file
        config: Transcription configuration
    
    Returns:
        Transcription result dict or None if failed
    """
    logger = logging.getLogger(__name__)
    
    with httpx.Client() as client:
        if config.mode == "openai":
            # Try OpenAI-compatible endpoint first
            result = transcribe_audio_openai_style(audio_path, config, client)
            if result is not None:
                return result
            
            # Fallback to generic endpoint
            logger.info("Falling back to generic endpoint")
            result = transcribe_audio_generic_style(audio_path, config, client)
            if result is not None:
                return result
        else:
            # Try generic endpoint
            result = transcribe_audio_generic_style(audio_path, config, client)
            if result is not None:
                return result
    
    return None


def format_timestamp(seconds: float) -> str:
    """Format seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(segments: list[dict[str, Any]]) -> str:
    """Generate SRT subtitle format from segments."""
    srt_lines = []
    
    for i, segment in enumerate(segments, 1):
        start = segment.get("start", 0)
        end = segment.get("end", 0)
        text = segment.get("text", "").strip()
        
        if not text:
            continue
        
        srt_lines.append(f"{i}")
        srt_lines.append(f"{format_timestamp(start)} --> {format_timestamp(end)}")
        srt_lines.append(text)
        srt_lines.append("")  # Empty line between subtitles
    
    return "\n".join(srt_lines)


def save_transcription(
    result: dict[str, Any],
    output_dir: Path,
    video_id: str,
    title: str,
) -> None:
    """
    Save transcription results to files.
    
    Args:
        result: Transcription result from API
        output_dir: Output directory for this video
        video_id: Video ID
        title: Video title
    """
    logger = logging.getLogger(__name__)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Extract text
    text = result.get("text", "")
    
    # Save plain text
    txt_path = output_dir / "transcript.txt"
    txt_path.write_text(text, encoding="utf-8")
    logger.debug(f"Saved text: {txt_path}")
    
    # Save JSON with metadata
    json_data = {
        "video_id": video_id,
        "title": title,
        "text": text,
        "segments": result.get("segments", []),
        "language": result.get("language"),
        "duration": result.get("duration"),
    }
    json_path = output_dir / "transcript.json"
    json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.debug(f"Saved JSON: {json_path}")
    
    # Generate and save SRT if segments available
    segments = result.get("segments", [])
    if segments:
        srt_content = generate_srt(segments)
        srt_path = output_dir / "transcript.srt"
        srt_path.write_text(srt_content, encoding="utf-8")
        logger.debug(f"Saved SRT: {srt_path}")
    else:
        logger.warning("No segments available for SRT generation")


def process_video(
    task: VideoTask,
    config: TranscriptionConfig,
    cache_dir: Path,
    delete_audio: bool,
    skip_existing: bool,
    retries: int,
    retry_backoff: float,
) -> tuple[str, bool, Optional[str]]:
    """
    Process a single video: download audio and transcribe.
    
    Args:
        task: Video task
        config: Transcription configuration
        cache_dir: Cache directory
        delete_audio: Whether to delete audio after processing
        skip_existing: Whether to skip if outputs exist
        retries: Number of retries on failure
        retry_backoff: Backoff time between retries (seconds)
    
    Returns:
        Tuple of (video_id, success, error_message)
    """
    logger = logging.getLogger(__name__)
    
    # Check if already processed
    txt_path = task.output_dir / "transcript.txt"
    json_path = task.output_dir / "transcript.json"
    
    if skip_existing and txt_path.exists() and json_path.exists():
        logger.info(f"Skipping {task.video_id} (already processed)")
        return (task.video_id, True, None)
    
    logger.info(f"Processing: {task.title[:50]}...")
    
    # Download audio
    audio_path = task.output_dir / "audio.mp3"
    
    for attempt in range(retries):
        if attempt > 0:
            logger.info(f"Retry {attempt}/{retries-1} for {task.video_id}")
            time.sleep(retry_backoff * attempt)
        
        # Download
        if not download_audio(task.url, audio_path, cache_dir):
            if attempt == retries - 1:
                return (task.video_id, False, "Audio download failed")
            continue
        
        # Transcribe
        result = transcribe_audio(audio_path, config)
        if result is None:
            if attempt == retries - 1:
                return (task.video_id, False, "Transcription failed")
            continue
        
        # Save results
        try:
            save_transcription(result, task.output_dir, task.video_id, task.title)
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            if attempt == retries - 1:
                return (task.video_id, False, f"Save failed: {e}")
            continue
        
        # Clean up audio if requested
        if delete_audio and audio_path.exists():
            audio_path.unlink()
            logger.debug(f"Deleted audio: {audio_path}")
        
        return (task.video_id, True, None)
    
    return (task.video_id, False, "Max retries exceeded")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Transcribe YouTube channel videos using local speaches service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/transcribe_channel.py --in data/videos.jsonl --speaches-model whispernlarge
  python tools/transcribe_channel.py --in data/videos.jsonl --concurrency 4 --skip-existing
  python tools/transcribe_channel.py --in data/videos.jsonl --speaches-mode generic --speaches-endpoint /transcribe
        """,
    )
    
    # Input/output
    parser.add_argument(
        "--in",
        dest="input",
        type=Path,
        default=Path("data/videos.jsonl"),
        help="Input JSONL file with video list",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("out"),
        help="Output directory for transcripts (default: out/)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".cache"),
        help="Cache directory for downloads (default: .cache/)",
    )
    
    # Speaches configuration
    parser.add_argument(
        "--speaches-base-url",
        default=os.getenv("SPEACHES_BASE_URL", "http://localhost:8000"),
        help="Base URL for speaches service (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--speaches-endpoint",
        default=os.getenv("SPEACHES_ENDPOINT", "/v1/audio/transcriptions"),
        help="Endpoint path (default: /v1/audio/transcriptions)",
    )
    parser.add_argument(
        "--speaches-mode",
        choices=["openai", "generic"],
        default=os.getenv("SPEACHES_MODE", "openai"),
        help="API mode: openai or generic (default: openai)",
    )
    parser.add_argument(
        "--speaches-model",
        default=os.getenv("SPEACHES_MODEL", "whispernlarge"),
        help="Model name to use (default: whispernlarge)",
    )
    parser.add_argument(
        "--language",
        default=os.getenv("LANGUAGE", "es"),
        help="Language code (default: es)",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.getenv("TIMEOUT_SECONDS", "1800")),
        help="Request timeout in seconds (default: 1800)",
    )
    
    # Processing options
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip videos that already have outputs",
    )
    parser.add_argument(
        "--delete-audio",
        action="store_true",
        help="Delete audio files after transcription",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="Number of concurrent transcription workers (default: 2)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Number of retries on failure (default: 3)",
    )
    parser.add_argument(
        "--retry-backoff-seconds",
        type=float,
        default=5.0,
        help="Backoff time between retries in seconds (default: 5.0)",
    )
    
    # Logging
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Log file path (default: logs/run.log)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_file = args.log_file or Path("logs/run.log")
    setup_logging(log_file, args.verbose)
    logger = logging.getLogger(__name__)
    
    # Load videos
    videos = load_videos(args.input)
    if not videos:
        logger.error("No videos to process")
        sys.exit(1)
    
    # Create config
    config = TranscriptionConfig(
        base_url=args.speaches_base_url,
        endpoint=args.speaches_endpoint,
        mode=args.speaches_mode,
        model=args.speaches_model,
        language=args.language,
        timeout=args.timeout_seconds,
    )
    
    logger.info(f"Transcription config: {config.base_url} | model={config.model} | lang={config.language}")
    
    # Create tasks
    tasks = []
    for video in videos:
        video_id = video["video_id"]
        title = video["title"]
        url = video["url"]
        
        safe_id = sanitize_filename(video_id)
        output_dir = args.out_dir / safe_id
        
        task = VideoTask(
            video_id=video_id,
            title=title,
            url=url,
            output_dir=output_dir,
        )
        tasks.append(task)
    
    logger.info(f"Processing {len(tasks)} videos with {args.concurrency} workers")
    
    # Process videos
    failures = []
    successes = 0
    
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        future_to_task = {
            executor.submit(
                process_video,
                task,
                config,
                args.cache_dir,
                args.delete_audio,
                args.skip_existing,
                args.retries,
                args.retry_backoff_seconds,
            ): task
            for task in tasks
        }
        
        with tqdm(total=len(tasks), desc="Processing videos", unit="video") as pbar:
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    video_id, success, error = future.result()
                    if success:
                        successes += 1
                    else:
                        failures.append({"video_id": video_id, "title": task.title, "error": error})
                        logger.error(f"Failed: {video_id} - {error}")
                except Exception as e:
                    logger.error(f"Unexpected error processing {task.video_id}: {e}")
                    failures.append({"video_id": task.video_id, "title": task.title, "error": str(e)})
                finally:
                    pbar.update(1)
    
    # Save failures
    if failures:
        failures_path = Path("data/failures.jsonl")
        failures_path.parent.mkdir(parents=True, exist_ok=True)
        with failures_path.open("w", encoding="utf-8") as f:
            for failure in failures:
                f.write(json.dumps(failure, ensure_ascii=False) + "\n")
        logger.warning(f"Wrote {len(failures)} failures to {failures_path}")
    
    # Summary
    logger.info(f"Completed: {successes}/{len(tasks)} successful, {len(failures)} failed")
    
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
