# Usage Guide

## Quick Start (Interactive)
The easiest way to use BSIFix is via the wrapper script, which handles dependencies automatically.

```bash
./bsifix.sh
```
This launches the **Interactive Wizard**, prompting you for:
1.  Source files (e.g. `Imports/*.wav`)
2.  Fix Mode (Copy vs In-Place)

## Batch Processing (CLI)
You can automate the process by passing arguments directly.

```bash
# Fix all WAVs in a folder (creates 'Fixed for BSI' subfolder)
./bsifix.sh "/Volumes/Music_Import/*.wav"

# Multiple sources
./bsifix.sh "Folder1/*.wav" "Folder2/*.wav"
```

## Options

### In-Place Fix
Overwrite the original files instead of creating copies.
*Warning: Destructive operation.*

```bash
./bsifix.sh --in-place "Target/*.wav"
```

### Parallel Control
By default, BSIFix uses all available CPU cores. You can limit this:

```bash
./bsifix.sh --parallel 2 "Target/*.wav"
```

## Manual Installation (Without Wrapper)
If you prefer to manage your own Python environment:

1.  **Install FFmpeg**: `brew install ffmpeg`
2.  **Install Python Libs**: `pip install rich`
3.  **Run**: `python3 BSIFix.py ...`
