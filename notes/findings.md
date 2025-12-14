# Investigation Findings

## "Good" vs "Bad" File Analysis

We analyzed two fixtures to determine the authoritative cause of BSI incompatibility.

### The "Bad" File
*   **Path**: `test/fixtures/bad/01 5 Kangaroos Jumping On The Bed.wav`
*   **Format**: `WAVE_FORMAT_EXTENSIBLE` (Header `0xFFFE`)
*   **Chunk Size**: `fmt` chunk was 40 bytes.
*   **Issue**: While the underlying audio was PCM, the *container structure* used the Extensible wrapper. Legacy parsers (like BSI) often hard-check for `WAVE_FORMAT_PCM` (0x0001) and a 16-byte `fmt` chunk. When they encounter 0xFFFE or a 40-byte chunk, they fail.
*   **Metadata**: Contained standard LIST/INFO tags but lacked `cart` or `bext` chunks.

### The "Good" File
*   **Path**: `test/fixtures/good/01 ABC Remix (feat. Snoop Dogg).wav`
*   **Format**: `WAVE_FORMAT_PCM` (Header `0x0001`)
*   **Chunk Size**: `fmt` chunk was 16 bytes.
*   **Metadata**: Contained Chinese characters in `IGNR` (Genre). This proved that the *file format* (WAV) can technically hold UTF-8, and if BSI accepted this file, it implies BSI might be tolerant of UTF-8 in `INFO` chunks (or at least ignores them safely), but definitely requires PCM `fmt` headers.

## Conclusion
The primary blocker is the **WAVE_FORMAT_EXTENSIBLE** header.
A secondary requirement for professional integration is the presence of **BWF (bext)** and **CART** chunks, which BSI uses for title/artist display and automation cues.

## Strategy Implemented
1.  **Force PCM**: We interpret `0xFFFE` `fmt` chunks and, if the subformat is PCM, rewrite the header to `0x0001` with a size of 16 bytes.
2.  **Prepend Metadata**: We inject `bext` and `cart` chunks *immediately after* the `fmt` chunk and *before* the `data` chunk. This optimization allows BSI to read all metadata without scanning the entire file.
