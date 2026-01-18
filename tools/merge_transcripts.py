#!/usr/bin/env python3
"""
Merge all transcripts into a single corpus file.
"""
import argparse
import logging
import sys
from pathlib import Path


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def merge_transcripts(input_dir: Path, output_path: Path, separator: str = "\n\n---\n\n") -> None:
    """
    Merge all transcript.txt files into a single corpus.
    
    Args:
        input_dir: Directory containing video subdirectories
        output_path: Output corpus file path
        separator: Separator between transcripts
    """
    logger = logging.getLogger(__name__)
    
    if not input_dir.exists():
        logger.error(f"Input directory not found: {input_dir}")
        sys.exit(1)
    
    # Find all transcript.txt files
    transcript_files = sorted(input_dir.glob("*/transcript.txt"))
    
    if not transcript_files:
        logger.warning(f"No transcript.txt files found in {input_dir}")
        return
    
    logger.info(f"Found {len(transcript_files)} transcripts to merge")
    
    # Merge transcripts
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with output_path.open("w", encoding="utf-8") as out_file:
        for i, transcript_file in enumerate(transcript_files):
            try:
                text = transcript_file.read_text(encoding="utf-8").strip()
                
                if text:
                    if i > 0:
                        out_file.write(separator)
                    
                    # Add video ID as header
                    video_id = transcript_file.parent.name
                    out_file.write(f"# Video: {video_id}\n\n")
                    out_file.write(text)
                    out_file.write("\n")
                    
                    logger.debug(f"Merged: {transcript_file}")
                else:
                    logger.warning(f"Empty transcript: {transcript_file}")
                    
            except Exception as e:
                logger.error(f"Failed to read {transcript_file}: {e}")
    
    # Get file size
    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(f"Wrote corpus to {output_path} ({size_mb:.2f} MB)")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Merge all transcripts into a single corpus file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/merge_transcripts.py --in out --out data/corpus.txt
  python tools/merge_transcripts.py --in out --out data/corpus.txt --separator "\\n\\n===\\n\\n"
        """,
    )
    parser.add_argument(
        "--in",
        dest="input",
        type=Path,
        default=Path("out"),
        help="Input directory containing video subdirectories (default: out/)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/corpus.txt"),
        help="Output corpus file path (default: data/corpus.txt)",
    )
    parser.add_argument(
        "--separator",
        default="\n\n---\n\n",
        help="Separator between transcripts (default: \\n\\n---\\n\\n)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    
    merge_transcripts(args.input, args.out, args.separator)


if __name__ == "__main__":
    main()
