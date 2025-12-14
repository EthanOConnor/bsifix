# Project Context

## Goal
To reliability fix WAV files that are incompatible with legacy BSI radio automation software, specifically handling metadata import failures and playback issues.

## Problem
Legacy BSI software often fails to import or play modern WAV files due to:
1.  **Format Incompatibility**: Support for standard `WAVE_FORMAT_PCM` (0x0001) but rejection of `WAVE_FORMAT_EXTENSIBLE` (0xFFFE), which many modern encoders (like ffmpeg default or recent DAW exports) use for 24-bit audio.
2.  **Metadata Requirements**: Expectation of specific chunk structures, notably valid `bext` (Broadcast Wave Format) and `cart` chunks, often placed *before* the audio data for efficient reading.
3.  **Strict ASCII**: Inability to handle UTF-8/Unicode characters in RIFF `INFO` chunks, leading to "mojibake" or import errors.

## Solution: BSIFix.py
A Python-based utility that acts as a robust "cleaner" and "injector" pipeline:
1.  **Transcode**: Forces conversion to clean 24-bit PCM using `ffmpeg`.
2.  **Structural Repair**: Python post-processing coerces any remaining Extensible headers to standard PCM.
3.  **Injector**: Generates and inserts standards-compliant `bext` and `cart` chunks.
4.  **Efficiency**: Uses streaming to handle large files with minimal RAM footprint.
