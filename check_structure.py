import struct
import sys

def check(path):
    with open(path, 'rb') as f:
        f.read(12)
        while True:
            h = f.read(8)
            if not h: break
            cid, size = struct.unpack('<4sI', h)
            print(f"Chunk: {cid} Size: {size}")
            f.seek(size + (size%2), 1)
            
if __name__ == '__main__':
    check(sys.argv[1])
