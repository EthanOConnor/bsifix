import struct
import sys

def inspect_fmt(path):
    with open(path, 'rb') as f:
        f.read(12)
        while True:
            h = f.read(8)
            if not h: break
            cid, size = struct.unpack('<4sI', h)
            if cid == b'fmt ':
                data = f.read(size)
                # Parse standard PCM fields
                # wFormatTag, nChannels, nSamplesPerSec, nAvgBytesPerSec, nBlockAlign, wBitsPerSample
                fmt = struct.unpack('<HHIIHH', data[:16])
                print(f"FormatTag:      {hex(fmt[0])}")
                print(f"Channels:       {fmt[1]}")
                print(f"SamplesPerSec:  {fmt[2]}")
                print(f"AvgBytesPerSec: {fmt[3]}")
                print(f"BlockAlign:     {fmt[4]}")
                print(f"BitsPerSample:  {fmt[5]}")
                
                # Check for validity
                expected_align = fmt[1] * (fmt[5] // 8)
                print(f"Expected Align: {expected_align}")
                
                if size > 16:
                   print(f"Extension Size: {struct.unpack('<H', data[16:18])[0]}")
                break
            else:
                f.seek(size + (size%2), 1)

if __name__ == '__main__':
    inspect_fmt(sys.argv[1])
