# BSIFix

A production-grade utility to fix WAV compatibility issues for legacy BSI radio automation software.

## Features
*   **Fixes Format**: Converts `WAVE_FORMAT_EXTENSIBLE` to standard PCM.
*   **Injects Metadata**: Adds standards-compliant BWF (`bext`) and CART chunks.
*   **Robust**: Handles large files via streaming and preserves Unicode text.
*   **Fast**: Parallel processing for bulk libraries.

## Quick Start

```bash
# Verify environment and launch wizard
./bsifix.sh
```

## Documentation

*   [Usage Guide](notes/usage.md)
*   [Findings & Analysis](notes/findings.md) (Why BSI fails)
*   [Architecture](notes/architecture.md) (How v3.0 works)
*   [Project Context](notes/project_context.md)

## Requirements
*   macOS / Linux
*   `ffmpeg` (must be in PATH)
*   Python 3 + `rich` (handled by `bsifix.sh`)
