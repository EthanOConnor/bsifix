import struct
import sys
import os

COPY_BUF_SIZE = 1024 * 1024

def reorder(src, dest):
    with open(src, 'rb') as f_in, open(dest, 'wb') as f_out:
        f_out.write(b'RIFF\x00\x00\x00\x00WAVE')
        
        f_in.seek(12)
        
        chunks = []
        while True:
            h = f_in.read(8)
            if not h or len(h) < 8: break
            cid, size = struct.unpack('<4sI', h)
            offset = f_in.tell()
            chunks.append((cid, size, offset))
            f_in.seek(size + (size%2), 1)
            
        # Find fmt and data
        fmt = next((c for c in chunks if c[0] == b'fmt '), None)
        data = next((c for c in chunks if c[0] == b'data'), None)
        others = [c for c in chunks if c[0] not in (b'fmt ', b'data')]
        
        if not fmt or not data:
            print("Error: Missing fmt or data")
            return
            
        # Write fmt
        f_out.write(fmt[0])
        f_out.write(struct.pack('<I', fmt[1]))
        f_in.seek(fmt[2])
        f_out.write(f_in.read(fmt[1]))
        if fmt[1] % 2 == 1: f_out.write(b'\x00')
        
        # Write data
        f_out.write(data[0])
        f_out.write(struct.pack('<I', data[1]))
        f_in.seek(data[2])
        remaining = data[1]
        while remaining > 0:
            chunk = f_in.read(min(remaining, COPY_BUF_SIZE))
            f_out.write(chunk)
            remaining -= len(chunk)
        if data[1] % 2 == 1: f_out.write(b'\x00')
        
        # Write others
        for cid, size, offset in others:
            f_out.write(cid)
            f_out.write(struct.pack('<I', size))
            f_in.seek(offset)
            f_out.write(f_in.read(size))
            if size % 2 == 1: f_out.write(b'\x00')
            
        # Fix RIFF size
        total = f_out.tell()
        f_out.seek(4)
        f_out.write(struct.pack('<I', total - 8))
        
    print(f"Reordered: {dest}")

if __name__ == '__main__':
    reorder(sys.argv[1], sys.argv[2])
