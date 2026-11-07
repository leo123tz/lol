"""Minimal reader for Roblox binary model files (.rbxm) - enough for KeyframeSequences.
Supports LZ4/ZSTD/raw chunks, INST/PROP/PRNT, and the property types used by animations
(String, Bool, Float, Token/Enum, CFrame)."""
import struct
import numpy as np

NORMALS = [(1, 0, 0), (0, 1, 0), (0, 0, 1), (-1, 0, 0), (0, -1, 0), (0, 0, -1)]


def _decompress(comp, ulen, data):
    if comp == 0:
        return data[:ulen]
    if data[:4] == b"\x28\xb5\x2f\xfd":
        import zstandard
        return zstandard.ZstdDecompressor().decompress(data, max_output_size=ulen)
    import lz4.block
    return lz4.block.decompress(data, uncompressed_size=ulen)


def _interleaved(buf, n, width=4):
    a = np.frombuffer(buf[:n * width], np.uint8).reshape(width, n).T  # byte planes -> rows
    return a.copy()


def _u32_be(buf, n):
    a = _interleaved(buf, n)
    return (a[:, 0].astype(np.uint64) << 24 | a[:, 1].astype(np.uint64) << 16 | a[:, 2].astype(np.uint64) << 8 | a[:, 3]).astype(np.uint32)


def _i32(buf, n):
    u = _u32_be(buf, n).astype(np.int64)
    return ((u >> 1) ^ -(u & 1)).astype(np.int64)


def _floats(buf, n):
    u = _u32_be(buf, n)
    r = ((u >> 1) | ((u & 1) << 31)).astype(np.uint32)  # rotate right by one
    return r.view(np.float32).astype(np.float64)


class Instance:
    def __init__(self, cls, ref):
        self.ClassName, self.ref, self.props, self.children, self.parent = cls, ref, {}, [], None

    @property
    def Name(self):
        return self.props.get("Name", "")

    def descendants(self):
        for c in self.children:
            yield c
            yield from c.descendants()

    def __repr__(self):
        return f"<{self.ClassName} {self.Name!r}>"


def read(path):
    raw = open(path, "rb").read()
    assert raw[:8] == b"<roblox!", "not a binary Roblox file"
    pos = 32
    classes, insts = {}, {}
    while pos < len(raw):
        name = raw[pos:pos + 4]; comp, ulen = struct.unpack_from("<II", raw, pos + 4)
        size = comp if comp else ulen
        data = _decompress(comp, ulen, raw[pos + 16:pos + 16 + size]); pos += 16 + size
        if name == b"INST":
            cid, = struct.unpack_from("<i", data, 0); ln, = struct.unpack_from("<I", data, 4)
            cname = data[8:8 + ln].decode(); o = 8 + ln + 1
            cnt, = struct.unpack_from("<i", data, o); o += 4
            refs = np.cumsum(_i32(data[o:], cnt))
            classes[cid] = (cname, list(refs))
            for r in refs:
                insts[int(r)] = Instance(cname, int(r))
        elif name == b"PROP":
            cid, = struct.unpack_from("<i", data, 0); ln, = struct.unpack_from("<I", data, 4)
            pname = data[8:8 + ln].decode(); o = 8 + ln
            t = data[o]; o += 1
            refs = classes[cid][1]; n = len(refs)
            vals = None
            if t == 0x01:
                vals = []
                for _ in range(n):
                    l, = struct.unpack_from("<I", data, o); vals.append(data[o + 4:o + 4 + l].decode("utf-8", "replace")); o += 4 + l
            elif t == 0x02:
                vals = [bool(b) for b in data[o:o + n]]
            elif t == 0x04:
                vals = list(_floats(data[o:], n))
            elif t == 0x12:
                vals = [int(v) for v in _u32_be(data[o:], n)]
            elif t == 0x10:
                rots = []
                for _ in range(n):
                    rid = data[o]; o += 1
                    if rid == 0:
                        m = np.array(struct.unpack_from("<9f", data, o), float).reshape(3, 3); o += 36
                    else:
                        x = np.array(NORMALS[(rid - 1) // 6], float); y = np.array(NORMALS[(rid - 1) % 6], float)
                        m = np.stack([x, y, np.cross(x, y)])  # rows
                    rots.append(m)
                X = _floats(data[o:], n); Y = _floats(data[o + 4 * n:], n); Z = _floats(data[o + 8 * n:], n)
                vals = []
                for i in range(n):
                    M = np.eye(4); M[:3, :3] = rots[i]; M[:3, 3] = (X[i], Y[i], Z[i]); vals.append(M)
            if vals is not None:
                for r, v in zip(refs, vals):
                    insts[int(r)].props[pname] = v
        elif name == b"PRNT":
            cnt, = struct.unpack_from("<i", data, 1)
            ch = np.cumsum(_i32(data[5:], cnt)); pa = np.cumsum(_i32(data[5 + 4 * cnt:], cnt))
            for c, p in zip(ch, pa):
                if p >= 0:
                    insts[int(c)].parent = insts[int(p)]; insts[int(p)].children.append(insts[int(c)])
        elif name == b"END\x00":
            break
    return [i for i in insts.values() if i.parent is None]
