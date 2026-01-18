#!/usr/bin/env python3
"""
Generate voice profile with linguistic style analysis.
Analyzes word frequency, common phrases, and generates a profile report.
"""
import argparse
import json
import logging
import re
import sys
from collections import Counter
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


def tokenize(text: str, language: str = "es") -> list[str]:
    """
    Tokenize text into words.
    
    Args:
        text: Input text
        language: Language code (for potential language-specific processing)
    
    Returns:
        List of lowercase word tokens
    """
    # Remove punctuation and split
    text = text.lower()
    # Keep letters, numbers, and common accented characters
    text = re.sub(r"[^\w\sáéíóúñüàèìòùâêîôûäëïöü]", " ", text)
    words = text.split()
    
    # Filter out very short words and numbers
    words = [w for w in words if len(w) > 2 and not w.isdigit()]
    
    return words


def get_ngrams(words: list[str], n: int) -> list[str]:
    """
    Generate n-grams from word list.
    
    Args:
        words: List of words
        n: N-gram size
    
    Returns:
        List of n-grams as space-separated strings
    """
    if len(words) < n:
        return []
    
    ngrams = []
    for i in range(len(words) - n + 1):
        ngram = " ".join(words[i:i+n])
        ngrams.append(ngram)
    
    return ngrams


def load_stopwords(language: str = "es") -> set[str]:
    """
    Load basic stopwords for filtering.
    
    Args:
        language: Language code
    
    Returns:
        Set of stopwords
    """
    # Basic Spanish stopwords
    if language == "es":
        return {
            "el", "la", "de", "que", "y", "a", "en", "un", "ser", "se", "no", "haber",
            "por", "con", "su", "para", "como", "estar", "tener", "le", "lo", "todo",
            "pero", "más", "hacer", "o", "poder", "decir", "este", "ir", "otro", "ese",
            "si", "me", "ya", "ver", "porque", "dar", "cuando", "él", "muy", "sin",
            "vez", "mucho", "saber", "qué", "sobre", "mi", "alguno", "mismo", "yo",
            "también", "hasta", "año", "dos", "querer", "entre", "así", "primero",
            "desde", "grande", "eso", "ni", "nos", "llegar", "pasar", "tiempo", "ella",
            "sí", "día", "uno", "bien", "poco", "deber", "entonces", "poner", "cosa",
            "tanto", "hombre", "parecer", "nuestro", "tan", "donde", "ahora", "parte",
            "después", "vida", "quedar", "siempre", "creer", "hablar", "llevar", "dejar",
            "nada", "cada", "seguir", "menos", "nuevo", "encontrar", "algo", "solo",
            "decir", "usted", "puede", "está", "sido", "tiene", "del", "los", "las",
            "una", "es", "son", "han", "era", "hay", "son", "sus", "fue", "esto",
            "aquí", "todos", "esta", "estas", "estos", "estos", "esa", "esas", "esos",
        }
    else:
        # Basic English stopwords
        return {
            "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it",
            "for", "not", "on", "with", "he", "as", "you", "do", "at", "this", "but",
            "his", "by", "from", "they", "we", "say", "her", "she", "or", "an", "will",
            "my", "one", "all", "would", "there", "their", "what", "so", "up", "out",
            "if", "about", "who", "get", "which", "go", "me", "when", "make", "can",
            "like", "time", "no", "just", "him", "know", "take", "people", "into",
            "year", "your", "good", "some", "could", "them", "see", "other", "than",
            "then", "now", "look", "only", "come", "its", "over", "think", "also",
            "back", "after", "use", "two", "how", "our", "work", "first", "well",
            "way", "even", "new", "want", "because", "any", "these", "give", "day",
            "most", "us", "is", "was", "are", "been", "has", "had", "were", "said",
            "did", "having", "may", "should", "could", "being",
        }


def analyze_transcripts(input_dir: Path, language: str = "es", top_n: int = 50) -> dict[str, Any]:
    """
    Analyze transcripts and generate statistics.
    
    Args:
        input_dir: Directory containing video subdirectories
        language: Language code for stopword filtering
        top_n: Number of top items to include
    
    Returns:
        Dictionary with analysis results
    """
    logger = logging.getLogger(__name__)
    
    if not input_dir.exists():
        logger.error(f"Input directory not found: {input_dir}")
        sys.exit(1)
    
    # Find all transcript files
    transcript_files = sorted(input_dir.glob("*/transcript.txt"))
    
    if not transcript_files:
        logger.warning(f"No transcript.txt files found in {input_dir}")
        return {}
    
    logger.info(f"Analyzing {len(transcript_files)} transcripts")
    
    # Load stopwords
    stopwords = load_stopwords(language)
    
    # Collect all words
    all_words = []
    all_texts = []
    total_chars = 0
    
    for transcript_file in transcript_files:
        try:
            text = transcript_file.read_text(encoding="utf-8")
            all_texts.append(text)
            total_chars += len(text)
            words = tokenize(text, language)
            all_words.extend(words)
        except Exception as e:
            logger.error(f"Failed to read {transcript_file}: {e}")
    
    logger.info(f"Collected {len(all_words)} words from {total_chars:,} characters")
    
    # Filter out stopwords for content analysis
    content_words = [w for w in all_words if w not in stopwords]
    
    # Word frequency
    word_freq = Counter(content_words)
    top_words = word_freq.most_common(top_n)
    
    # 2-grams
    bigrams = []
    for text in all_texts:
        words = tokenize(text, language)
        bigrams.extend(get_ngrams(words, 2))
    
    bigram_freq = Counter(bigrams)
    top_bigrams = bigram_freq.most_common(top_n)
    
    # 3-grams
    trigrams = []
    for text in all_texts:
        words = tokenize(text, language)
        trigrams.extend(get_ngrams(words, 3))
    
    trigram_freq = Counter(trigrams)
    top_trigrams = trigram_freq.most_common(top_n)
    
    # Statistics
    stats = {
        "total_videos": len(transcript_files),
        "total_characters": total_chars,
        "total_words": len(all_words),
        "unique_words": len(set(all_words)),
        "unique_content_words": len(set(content_words)),
        "avg_chars_per_video": total_chars // len(transcript_files) if transcript_files else 0,
        "avg_words_per_video": len(all_words) // len(transcript_files) if transcript_files else 0,
        "top_words": top_words,
        "top_bigrams": top_bigrams,
        "top_trigrams": top_trigrams,
    }
    
    return stats


def generate_report(stats: dict[str, Any], output_path: Path) -> None:
    """
    Generate markdown report from analysis statistics.
    
    Args:
        stats: Analysis statistics
        output_path: Output markdown file path
    """
    logger = logging.getLogger(__name__)
    
    if not stats:
        logger.warning("No statistics to report")
        return
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with output_path.open("w", encoding="utf-8") as f:
        f.write("# Voice Profile Analysis\n\n")
        
        # Overview
        f.write("## Overview\n\n")
        f.write(f"- **Total Videos**: {stats['total_videos']}\n")
        f.write(f"- **Total Characters**: {stats['total_characters']:,}\n")
        f.write(f"- **Total Words**: {stats['total_words']:,}\n")
        f.write(f"- **Unique Words**: {stats['unique_words']:,}\n")
        f.write(f"- **Unique Content Words**: {stats['unique_content_words']:,}\n")
        f.write(f"- **Avg Characters/Video**: {stats['avg_chars_per_video']:,}\n")
        f.write(f"- **Avg Words/Video**: {stats['avg_words_per_video']:,}\n")
        f.write("\n")
        
        # Top words
        f.write("## Top Words\n\n")
        f.write("Most frequently used content words (stopwords excluded):\n\n")
        f.write("| Rank | Word | Count |\n")
        f.write("|------|------|-------|\n")
        for i, (word, count) in enumerate(stats['top_words'][:30], 1):
            f.write(f"| {i} | {word} | {count:,} |\n")
        f.write("\n")
        
        # Top bigrams
        f.write("## Top 2-grams\n\n")
        f.write("Most frequently used two-word phrases:\n\n")
        f.write("| Rank | Phrase | Count |\n")
        f.write("|------|--------|-------|\n")
        for i, (phrase, count) in enumerate(stats['top_bigrams'][:30], 1):
            f.write(f"| {i} | {phrase} | {count:,} |\n")
        f.write("\n")
        
        # Top trigrams
        f.write("## Top 3-grams\n\n")
        f.write("Most frequently used three-word phrases:\n\n")
        f.write("| Rank | Phrase | Count |\n")
        f.write("|------|--------|-------|\n")
        for i, (phrase, count) in enumerate(stats['top_trigrams'][:30], 1):
            f.write(f"| {i} | {phrase} | {count:,} |\n")
        f.write("\n")
    
    logger.info(f"Generated report: {output_path}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate voice profile with linguistic style analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/voice_profile.py --in out --out data/voice_profile.md
  python tools/voice_profile.py --in out --out data/voice_profile.md --language es --top-n 100
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
        default=Path("data/voice_profile.md"),
        help="Output markdown report path (default: data/voice_profile.md)",
    )
    parser.add_argument(
        "--language",
        default="es",
        help="Language code for stopword filtering (default: es)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=50,
        help="Number of top items to include (default: 50)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    
    logger = logging.getLogger(__name__)
    logger.info("Starting voice profile analysis")
    
    # Analyze transcripts
    stats = analyze_transcripts(args.input, args.language, args.top_n)
    
    # Generate report
    generate_report(stats, args.out)
    
    logger.info("Analysis complete")


if __name__ == "__main__":
    main()
