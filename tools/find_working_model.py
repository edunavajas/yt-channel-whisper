#!/usr/bin/env python3
"""
Test different Whisper models to find one that works correctly with Spanish.
"""
import argparse
import sys
from pathlib import Path

import httpx


def test_model(audio_path: Path, base_url: str, model: str, language: str = "es"):
    """Test a single model."""
    
    url = f"{base_url}/v1/audio/transcriptions"
    
    print(f"\nTesting model: {model}")
    print("-" * 60)
    
    try:
        with httpx.Client(timeout=300) as client:
            with audio_path.open("rb") as audio_file:
                files = {"file": (audio_path.name, audio_file, "audio/mpeg")}
                data = {
                    "model": model,
                    "language": language,
                    "task": "transcribe",
                    "response_format": "verbose_json",
                }
                
                response = client.post(url, files=files, data=data)
                
                if response.status_code != 200:
                    print(f"[FAIL] Status {response.status_code}: {response.text[:200]}")
                    return False
                
                result = response.json()
                text = result.get("text", "")
                detected_lang = result.get("language", "N/A")
                
                # Check if Spanish
                spanish_words = ["entonces", "aquí", "voy", "hacer", "este", "para", "porque", "bueno"]
                english_words = ["then", "here", "going", "make", "this", "for", "because", "well"]
                
                spanish_count = sum(1 for w in spanish_words if w in text.lower())
                english_count = sum(1 for w in english_words if w in text.lower())
                
                print(f"Language detected: {detected_lang}")
                print(f"Text preview: {text[:150]}...")
                print(f"Spanish words found: {spanish_count}")
                print(f"English words found: {english_count}")
                
                if spanish_count >= english_count and "entonces" in text.lower():
                    print("[OK] This model works correctly with Spanish!")
                    return True
                else:
                    print("[FAIL] Model is translating or transcribing incorrectly")
                    return False
                    
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test different models for Spanish transcription")
    parser.add_argument("--audio", type=Path, required=True, help="Audio file path")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL")
    parser.add_argument("--language", default="es", help="Language code")
    
    args = parser.parse_args()
    
    if not args.audio.exists():
        print(f"ERROR: Audio file not found: {args.audio}")
        sys.exit(1)
    
    print("=" * 60)
    print("Testing different Whisper models for Spanish transcription")
    print("=" * 60)
    
    # Common Whisper model names
    models_to_test = [
        # OpenAI official models
        "openai/whisper-large-v3",
        "openai/whisper-large-v2",
        "openai/whisper-medium",
        "openai/whisper-small",
        
        # Short names
        "large-v3",
        "large-v2",
        "medium",
        "small",
        
        # Faster Whisper
        "large-v3",
        "large-v2",
        
        # Your current model (for comparison)
        "Systran/faster-distil-whisper-large-v3",
    ]
    
    working_models = []
    
    for model in models_to_test:
        if test_model(args.audio, args.base_url, model, args.language):
            working_models.append(model)
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if working_models:
        print(f"\nWorking models ({len(working_models)}):")
        for model in working_models:
            print(f"  - {model}")
        print(f"\nRecommendation: Use --speaches-model \"{working_models[0]}\"")
    else:
        print("\n[CRITICAL] No working models found!")
        print("\nPossible issues:")
        print("  1. Your speaches server has a configuration issue")
        print("  2. The service is set to translate by default")
        print("  3. Need to check speaches server logs/config")
        print("\nNext steps:")
        print("  1. Check your speaches server configuration")
        print("  2. Try calling the API directly with curl")
        print("  3. Check speaches server logs for errors")


if __name__ == "__main__":
    main()
