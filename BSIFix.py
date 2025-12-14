#!/usr/bin/env python3
"""
BSI WAV Fixer — v3.0 (Production)
Maximally compliant WAV fixer for BSI radio automation software.

Features:
  - Fixes WAVE_FORMAT_EXTENSIBLE incompatible with legacy BSI.
  - Injects standard 'bext' and 'cart' chunks (before data).
  - Preserves Unicode metadata in RIFF INFO chunks.
  - Interactive mode (wizard) when run without arguments.
  - Parallel processing for high performance.
  - Progress bars and detailed status reporting.

Dependencies:
  - python3
  - ffmpeg (must be in PATH)
  - rich (pip install rich)

Usage:
  python3 BSIFix.py                    # Interactive Wizard
  python3 BSIFix.py "folder/*.wav"     # Batch mode
  python3 BSIFix.py --in-place "*.wav" # Overwrite files
"""

import argparse
import glob
import json
import os
import shutil
import struct
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from typing import Optional, List, Tuple

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
    from rich.prompt import Prompt, Confirm
    from rich.panel import Panel
    from rich.table import Table
except ImportError:
    print("ERROR: 'rich' library not found. Please run: pip install rich")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Configuration & Constants
# ------------------------------------------------------------------------------

SCRIPT_VERSION = "3.1"
OUT_DIR_NAME = "Fixed for BSI"
DEFAULT_GENRE = "Children's Music"
COPY_BUF_SIZE = 1024 * 1024  # 1MB buffer for streaming

console = Console()

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def which_or_die(cmd):
    if not shutil.which(cmd):
        console.print(f"[bold red]ERROR:[/bold red] '{cmd}' not found. Please install '{cmd}' (e.g. brew install ffmpeg).")
        sys.exit(2)

def get_ffprobe_metadata(path):
    """Return a dict of tags from ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        path
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        data = json.loads(res.stdout)
        return data.get("format", {}).get("tags", {})
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return {}

def ascii_clean(s, max_len=None):
    """Enforce ASCII, replacing non-ascii with '?', and truncate."""
    if not s:
        s = ""
    b = s.encode("ascii", "replace") # Replace with '?'
    s_ascii = b.decode("ascii")
    if max_len and len(s_ascii) > max_len:
        s_ascii = s_ascii[:max_len]
    return s_ascii

def pad_bytes(b_data, length):
    if len(b_data) > length:
        return b_data[:length]
    return b_data + b'\x00' * (length - len(b_data))

# ------------------------------------------------------------------------------
# Chunk Builders
# ------------------------------------------------------------------------------

def build_bext_chunk(title, artist, date_str, time_str):
    """Build BWF 'bext' chunk data (Version 0). Everything strictly ASCII."""
    desc = ascii_clean(title, 256).encode('ascii')
    orig = ascii_clean(artist, 32).encode('ascii')
    
    # OriginatorReference: Unique ID.
    orig_ref = b'bsifix-' + os.urandom(8).hex().encode('ascii')
    orig_ref = pad_bytes(orig_ref, 32)
    
    if not date_str:
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        
    b_date = ascii_clean(date_str, 10).encode('ascii')
    b_time = ascii_clean(time_str, 8).encode('ascii')
    
    time_ref_low = 0
    time_ref_high = 0
    version = 0
    umid = b'\x00' * 64
    
    out = bytearray()
    out.extend(pad_bytes(desc, 256))
    out.extend(pad_bytes(orig, 32))
    out.extend(pad_bytes(orig_ref, 32))
    out.extend(pad_bytes(b_date, 10))
    out.extend(pad_bytes(b_time, 8))
    out.extend(struct.pack('<IIH', time_ref_low, time_ref_high, version))
    out.extend(umid)
    out.extend(b'\x00' * 190) # Loudness(10) + Reserved(180)
    
    coding_hist = b"CodingHistory=BSIFix3.1\r\n"
    out.extend(coding_hist)
    
    return out

def build_cart_chunk(title, artist, cut_id):
    """Build 'cart' chunk. Enforce ASCII."""
    def p(s, l):
        return pad_bytes(ascii_clean(s, l).encode('ascii'), l)
        
    out = bytearray()
    out.extend(p("0101", 4))
    out.extend(p(title, 64))
    out.extend(p(artist, 64))
    out.extend(p(cut_id, 64))
    out.extend(p("", 64*4)) # ClientID...OutCue
    out.extend(p("", 10)) # StartDate
    out.extend(p("", 8))  # StartTime
    out.extend(p("", 10)) # EndDate
    out.extend(p("", 8))  # EndTime
    out.extend(p("BSIFix", 64)) # ProducerAppID
    out.extend(p(SCRIPT_VERSION, 64)) # ProducerAppVersion
    out.extend(p("", 64)) # UserDef
    out.extend(struct.pack('<I', 0)) # dwLevelReference
    out.extend(b'\x00' * 64) # PostTimer
    out.extend(b'\x00' * 276) # Reserved
    out.extend(p("", 1024)) # URL
    
    return out

# ------------------------------------------------------------------------------
# Processing
# ------------------------------------------------------------------------------

def yield_chunks(f):
    """
    Generator that reads RIFF chunks.
    """
    f.seek(12) # Skip RIFF header
    while True:
        header = f.read(8)
        if not header or len(header) != 8:
            break
        cid, size = struct.unpack('<4sI', header)
        
        # If it's a data chunk or very large, return offset
        if cid == b'data' or size > 1024*1024:
            offset = f.tell()
            yield cid, size, offset
            f.seek(size, 1) # Skip
        else:
            data = f.read(size)
            yield cid, size, data
            
        if size % 2 == 1:
            f.read(1)

def process_single_file(src: str, out_root: Optional[str], in_place: bool) -> str:
    """
    Worker function to process a single file.
    Returns: "SUCCESS", "SKIPPED", "ERROR: <msg>"
    """
    try:
        src_abs = os.path.abspath(src)
        base = os.path.splitext(os.path.basename(src))[0]
        parent = os.path.basename(os.path.dirname(src_abs))
        
        if in_place:
            # For in-place, we initially write to a temp file in the SAME directory
            # to ensure atomic move working efficiently
            out_dir = os.path.dirname(src_abs)
            dest = src_abs # Final target is source
            tmp_final = src_abs + ".bsifix.tmp.wav"
        else:
            if not out_root: return "ERROR: No output root"
            out_dir = os.path.join(out_root, parent)
            os.makedirs(out_dir, exist_ok=True)
            dest = os.path.join(out_dir, base + ".BSI.wav")
            if os.path.exists(dest):
                return "SKIPPED: Exists"
            tmp_final = dest + ".tmp.wav"

        # 1. Gather Metadata
        tags = get_ffprobe_metadata(src_abs)
        title = tags.get("title", base)
        artist = tags.get("artist", "Unknown Artist")
        album = tags.get("album", "")
        date = tags.get("date", tags.get("date_created", str(datetime.now().year)))
        genre = tags.get("genre", DEFAULT_GENRE)
        track = tags.get("track", "")
        composer = tags.get("composer", "")
        comment = tags.get("comment", "")
        encoded_by = tags.get("encoded_by", "")
        
        # 2. FFmpeg Pass (Transcode)
        ffmpeg_tmp = tmp_final + ".ffmpeg.wav"
        
        # Build metadata args
        meta_args = []
        for k, v in [
            ("title", title), ("artist", artist), ("album", album), 
            ("date", date), ("genre", genre), ("track", track),
            ("composer", composer), ("comment", comment), ("encoded_by", encoded_by)
        ]:
            if v:
                meta_args.extend(["-metadata", f"{k}={v}"])

        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", src_abs,
            "-c:a", "pcm_s24le",
            "-map_metadata", "-1", # Clear input metadata
        ] + meta_args + [
            "-f", "wav",
            ffmpeg_tmp
        ]
        
        subprocess.run(cmd, check=True)
        
        # 3. Post-Process Chunks (Streaming)
        with open(ffmpeg_tmp, 'rb') as f_in:
            header = f_in.read(12)
            riff, _, wave = struct.unpack('<4sI4s', header)
            
            input_chunks = list(yield_chunks(f_in))
            
        new_chunks_info = [] 
        
        bext_data = build_bext_chunk(title, artist, None, None)
        cart_data = build_cart_chunk(title, artist, base)
        
        fmt_chunk = None
        data_chunk_info = None
        other_chunks = []
        
        for cid, size, payload in input_chunks:
            if cid == b'fmt ':
                if isinstance(payload, bytes) and len(payload) >= 20:
                     wFormatTag = struct.unpack('<H', payload[:2])[0]
                     if wFormatTag == 0xFFFE: # Extensible -> PCM
                         nChannels, nSamplesPerSec, nAvgBytes, nBlockAlign, wBits = struct.unpack('<HIIHH', payload[2:16])
                         payload = struct.pack('<HHIIHH', 0x0001, nChannels, nSamplesPerSec, nAvgBytes, nBlockAlign, wBits)
                fmt_chunk = (cid, payload)
            elif cid == b'data':
                data_chunk_info = (cid, size, payload)
            elif cid in (b'bext', b'cart'):
                 pass 
            else:
                other_chunks.append((cid, size, payload))
                
        # Assembly
        with open(ffmpeg_tmp, 'rb') as f_in, open(tmp_final, 'wb') as f_out:
            f_out.write(b'RIFF\x00\x00\x00\x00WAVE')
            
            # 1. fmt
            if fmt_chunk:
                f_out.write(fmt_chunk[0])
                f_out.write(struct.pack('<I', len(fmt_chunk[1])))
                f_out.write(fmt_chunk[1])
                if len(fmt_chunk[1]) % 2 == 1: f_out.write(b'\x00')
                
            # 2. Data (Immediate audio for legacy compat)
            if data_chunk_info:
                cid, size, offset = data_chunk_info
                f_out.write(cid)
                f_out.write(struct.pack('<I', size))
                f_in.seek(offset)
                remaining = size
                while remaining > 0:
                    chunk = f_in.read(min(remaining, COPY_BUF_SIZE))
                    if not chunk: break
                    f_out.write(chunk)
                    remaining -= len(chunk)
                if size % 2 == 1: f_out.write(b'\x00')

            # 3. bext/cart (Metadata at end)
            for cid, d in [(b'bext', bext_data), (b'cart', cart_data)]:
                f_out.write(cid)
                f_out.write(struct.pack('<I', len(d)))
                f_out.write(d)
                if len(d) % 2 == 1: f_out.write(b'\x00')
                
            # 4. Others (LIST, etc)
            for cid, size, payload in other_chunks:
                f_out.write(cid)
                f_out.write(struct.pack('<I', size))
                if isinstance(payload, int): # Offset
                    f_in.seek(payload)
                    remaining = size
                    while remaining > 0:
                        chunk = f_in.read(min(remaining, COPY_BUF_SIZE))
                        if not chunk: break
                        f_out.write(chunk)
                        remaining -= len(chunk)
                else:
                    f_out.write(payload)
                if size % 2 == 1: f_out.write(b'\x00')
            
            file_size = f_out.tell()
            f_out.seek(4)
            f_out.write(struct.pack('<I', file_size - 8))
            
        # Cleanup temp
        if os.path.exists(ffmpeg_tmp):
            os.remove(ffmpeg_tmp)
            
        # Final move
        os.replace(tmp_final, dest)
        
        return "SUCCESS"

    except Exception as e:
        return f"ERROR: {str(e)}"


# ------------------------------------------------------------------------------
# Orchestration
# ------------------------------------------------------------------------------

def run_batch(files: List[str], in_place: bool, parallel: int = None):
    out_root = None
    if not in_place:
        out_root = os.path.abspath(os.path.join(os.getcwd(), OUT_DIR_NAME))
        console.print(f"[bold blue]Output Directory:[/bold blue] {out_root}")
    else:
        console.print(f"[bold red]WARNING: Running in IN-PLACE mode. Original files will be overwritten.[/bold red]")

    # Check dependencies
    which_or_die("ffmpeg")
    which_or_die("ffprobe")
    
    if not files:
        console.print("[yellow]No files found to process.[/yellow]")
        return

    workers = parallel or (os.cpu_count() or 4)
    console.print(f"Processing [bold]{len(files)}[/bold] files with [bold]{workers}[/bold] workers...")
    
    success = 0
    skipped = 0
    errors = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task_id = progress.add_task("Fixing WAVs...", total=len(files))
        
        with ProcessPoolExecutor(max_workers=workers) as executor:
            future_to_file = {executor.submit(process_single_file, f, out_root, in_place): f for f in files}
            
            for future in as_completed(future_to_file):
                f = future_to_file[future]
                try:
                    res = future.result()
                    if res == "SUCCESS":
                        success += 1
                        # console.log(f"[green]✓[/green] {os.path.basename(f)}")
                    elif res.startswith("SKIPPED"):
                        skipped += 1
                        console.log(f"[yellow]↔[/yellow] {os.path.basename(f)} (Skipped)")
                    else:
                        errors += 1
                        console.log(f"[red]✗[/red] {os.path.basename(f)}: {res}")
                except Exception as exc:
                    errors += 1
                    console.log(f"[red]✗[/red] {os.path.basename(f)} generated exception: {exc}")
                
                progress.advance(task_id)

    # Summary Table
    table = Table(title="Processing Summary", show_header=True, header_style="bold magenta")
    table.add_column("Result", style="dim")
    table.add_column("Count")
    
    table.add_row("[green]Success[/green]", str(success))
    table.add_row("[yellow]Skipped[/yellow]", str(skipped))
    table.add_row("[red]Failed[/red]", str(errors))
    
    console.print(table)
    if not in_place:
        console.print(f"\nFiles saved to: [bold underline]{out_root}[/bold underline]")

def interactive_wizard():
    console.print(Panel.fit("[bold white on blue] BSI WAV Fixer Wizard [/bold white on blue]\n\nThis tool will fix WAV files for BSI radio automation.\nIt converts them to 24-bit PCM and injects required chunks."))
    
    # 1. Select Path
    path_input = Prompt.ask("Enter file glob or directory (e.g. 'Music/*.wav')")
    
    # Expand path if dir
    if os.path.isdir(path_input):
        files = glob.glob(os.path.join(path_input, "*.wav"))
    else:
        files = glob.glob(path_input)
        
    if not files:
        console.print("[bold red]No WAV files found matching that pattern![/bold red]")
        sys.exit(1)
        
    console.print(f"Found [bold]{len(files)}[/bold] WAV files.")
    
    # 2. In-Place or Copy
    in_place = Confirm.ask("Do you want to fix files [bold red]IN-PLACE[/bold red] (overwrite originals)?", default=False)
    
    # 3. Confirm
    if not Confirm.ask("Ready to start?"):
        sys.exit(0)
        
    run_batch(files, in_place)

def main():
    parser = argparse.ArgumentParser(description="Fix WAVs for BSI compatibility.")
    parser.add_argument("inputs", nargs="*", help="Input files or globs (leave empty for wizard)")
    parser.add_argument("--in-place", action="store_true", help="Overwrite original files instead of creating a copy")
    parser.add_argument("--parallel", type=int, default=None, help="Number of parallel workers")
    args = parser.parse_args()
    
    if not args.inputs:
        interactive_wizard()
    else:
        files = []
        for pattern in args.inputs:
             files.extend(glob.glob(pattern))
        files = sorted(list(set(files)))
        
        run_batch(files, args.in_place, args.parallel)

if __name__ == "__main__":
    main()
