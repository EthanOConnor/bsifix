# Architecture & Design (v3.0)

## Design Philosophy
*   **Dependency Minimal**: Relies only on `ffmpeg` (industry standard) and `rich` (UI), avoiding obscure libraries like `bwfmetaedit` or `sox`.
*   **Robustness**: Handles large files via streaming; resilient to metadata character sets.
*   **Production Ready**: Includes interactive wizards and parallel processing.

## Pipeline Steps

### 1. Analysis & Metadata Extraction
*   Uses `ffprobe` (JSON mode) to extract exhaustive metadata (Title, Artist, Album, Composer, Track, etc.).
*   Fallbacks provided for missing compulsory fields.

### 2. Transcoding (FFmpeg)
*   **Command**: `ffmpeg -i src.wav -c:a pcm_s24le -map_metadata -1 ... -f wav tmp.wav`
*   **Purpose**: Ensures the audio data is strictly 24-bit Little Endian PCM.
*   **Metadata**: Metadata is re-injected via CLI arguments to ensure `ffmpeg` writes a valid RIFF `INFO` chunk with UTF-8 support.

### 3. Post-Processing & Injection (Python)
*   **Streaming Reader**: A generator yields chunks (`(id, size, data/offset)`) from the `ffmpeg` output.
    *   Small chunks (<1MB) are read into memory.
    *   Large chunks (`data`) are yielded as file offsets to prevent RAM spikes.
*   **Format Coercion**: Detects `0xFFFE` (Extensible) in `fmt ` chunk. If found, rewrites it to `0x0001` (PCM) and adjusts the chunk size to 16 bytes.
*   **Chunk Injection**:
    *   Generates a **Version 0 BWF (bext)** chunk (Strict ASCII).
    *   Generates a **CART** chunk (Strict ASCII) with cut ID and producer info.
    *   **Ordering (v3.1)**: The new file is written as `RIFF -> fmt -> data -> bext -> cart -> LIST`. This "Audio First" approach is required for legacy BSI compatibility, which fails if metadata chunks precede the audio.

### 4. Concurrency
*   Uses `concurrent.futures.ProcessPoolExecutor` to spawn worker processes.
*   Each worker handles one file independently (temp file creation -> atomic move).
*   The main thread manages the `rich` UI progress bar.

## Virtual Environment
A `bsifix.sh` wrapper ensures a consistent execution environment:
*   Creates local `.venv` if missing.
*   Installs `rich`.
*   Executes `BSIFix.py`.
