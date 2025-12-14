import struct
import sys

def ascii_dump(data):
    return ''.join(chr(b) if 32 <= b <= 126 else '.' for b in data)

def inspect(path):
    with open(path, 'rb') as f:
        f.read(12)
        while True:
            h = f.read(8)
            if not h or len(h) < 8: break
            cid, size = struct.unpack('<4sI', h)
            print(f"Seeing Chunk: {cid} Size: {size}")
            
            if cid == b'bext':
                data = f.read(size)
                print(f"--- bext ({size}) ---")
                print(f"Desc: {ascii_dump(data[:256])}")
                print(f"Orig: {ascii_dump(data[256:288])}")
                print(f"Ref:  {ascii_dump(data[288:320])}")
            elif cid == b'cart':
                data = f.read(size)
                print(f"--- cart ({size}) ---")
                print(f"Version: {ascii_dump(data[0:4])}")
                print(f"Title:   {ascii_dump(data[4:68])}")
                print(f"Artist:  {ascii_dump(data[68:132])}")
                print(f"CutID:   {ascii_dump(data[132:196])}")
            else:
                f.seek(size, 1)
            
            if size % 2 == 1:
                f.read(1)

if __name__ == '__main__':
    inspect(sys.argv[1])
