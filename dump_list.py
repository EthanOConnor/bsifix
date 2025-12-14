import struct
import sys

def dump_list(path):
    with open(path, 'rb') as f:
        f.read(12)
        while True:
            h = f.read(8)
            if not h: break
            cid, size = struct.unpack('<4sI', h)
            if cid == b'LIST':
                ftype = f.read(4)
                print(f"--- LIST ({ftype}) ---")
                rem = size - 4
                while rem > 0:
                    sh = f.read(8)
                    if len(sh) < 8: break
                    sid, ssize = struct.unpack('<4sI', sh)
                    val = f.read(ssize)
                    val_str = val.decode('utf-8', 'ignore').strip('\x00')
                    print(f"{sid}: {val_str}")
                    rem -= (8 + ssize)
                    if ssize % 2 == 1:
                        f.read(1)
                        rem -= 1
            else:
                f.seek(size + (size%2), 1)

if __name__ == '__main__':
    dump_list(sys.argv[1])
