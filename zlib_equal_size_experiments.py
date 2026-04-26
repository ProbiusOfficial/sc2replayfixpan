import binascii
import importlib.util
import shutil
import sys
import zlib

sys.path.insert(0, "mpyq-master")
sys.path.insert(0, "s2protocol-master")

from mpyq import MPQArchive, MPQ_FILE_COMPRESS, MPQ_FILE_SINGLE_UNIT  # noqa: E402


def load_protocol():
    spec = importlib.util.spec_from_file_location(
        "protocol95299",
        "s2protocol-master/s2protocol/versions/protocol95299.py",
    )
    protocol = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(protocol)
    return protocol


PROTOCOL = load_protocol()


class BitWriter:
    def __init__(self):
        self.data = bytearray()
        self.current = 0
        self.used = 0

    def write_bit(self, bit):
        self.current |= (bit & 1) << self.used
        self.used += 1
        if self.used == 8:
            self.data.append(self.current)
            self.current = 0
            self.used = 0

    def write_empty_fixed_block(self, final):
        # Deflate bits are LSB-first. BTYPE=01 means fixed Huffman.
        self.write_bit(1 if final else 0)
        self.write_bit(1)
        self.write_bit(0)
        # Fixed-Huffman EOB symbol 256 is seven zero bits.
        for _ in range(7):
            self.write_bit(0)

    def finish(self):
        if self.used:
            self.data.append(self.current)
            self.current = 0
            self.used = 0
        return bytes(self.data)


def padded_zlib_stream(raw, target_length):
    strategies = [
        zlib.Z_DEFAULT_STRATEGY,
        zlib.Z_FILTERED,
        zlib.Z_FIXED,
        zlib.Z_HUFFMAN_ONLY,
        zlib.Z_RLE,
    ]
    levels = range(1, 10)

    for strategy in strategies:
        for level in levels:
            compressor = zlib.compressobj(level, zlib.DEFLATED, -15, 9, strategy)
            deflate_prefix = compressor.compress(raw) + compressor.flush(zlib.Z_SYNC_FLUSH)
            header = bytes([0x78, 0x9C])
            checksum = zlib.adler32(raw).to_bytes(4, "big")

            for empty_blocks in range(0, 4000):
                writer = BitWriter()
                for _ in range(empty_blocks):
                    writer.write_empty_fixed_block(final=False)
                writer.write_empty_fixed_block(final=True)
                stream = header + deflate_prefix + writer.finish() + checksum
                if len(stream) == target_length:
                    if zlib.decompress(stream) != raw:
                        raise RuntimeError("internal zlib padding error")
                    return stream
                if len(stream) > target_length:
                    break

    raise RuntimeError(f"无法构造等长 zlib 流：target={target_length}")


def replace_file_equal_archived_size(path, filename, replacements):
    archive = MPQArchive(path)
    hash_entry = archive.get_hash_table_entry(filename)
    if hash_entry is None:
        return f"{filename}: missing"

    block_entry = archive.block_table[hash_entry.block_table_index]
    if not (block_entry.flags & MPQ_FILE_SINGLE_UNIT):
        raise RuntimeError(f"{filename}: not single-unit")
    if not (block_entry.flags & MPQ_FILE_COMPRESS):
        raise RuntimeError(f"{filename}: not compressed")

    raw = archive.read_file(filename)
    patched = raw
    count = 0
    for old, new in replacements:
        found = patched.count(old)
        count += found
        patched = patched.replace(old, new)

    if len(patched) != len(raw):
        raise RuntimeError(f"{filename}: raw size changed")

    target_stream_len = block_entry.archived_size - 1
    stream = padded_zlib_stream(patched, target_stream_len)
    archived = bytes([2]) + stream
    if len(archived) != block_entry.archived_size:
        raise RuntimeError(f"{filename}: archived size mismatch")

    with open(path, "r+b") as output:
        output.seek(archive.header["offset"] + block_entry.offset)
        output.write(archived)

    return f"{filename}: replacements={count}, archived_size={len(archived)} unchanged"


def get_last_two_mod_handles(path):
    archive = MPQArchive(path)
    initdata = PROTOCOL.decode_replay_initdata(archive.read_file("replay.initData"))
    return initdata["m_syncLobbyState"]["m_gameDescription"]["m_cacheHandles"][-2:]


def hex_list(values):
    return [binascii.hexlify(value).decode().upper() for value in values]


def main():
    old_handles = get_last_two_mod_handles("test.SC2Replay")
    new_handles = get_last_two_mod_handles("96516.SC2Replay")
    replacements = list(zip(old_handles, new_handles))
    no_replacements = []

    jobs = [
        (
            "test_fix_L_B_equal_zlib_same_initdata.SC2Replay",
            "test_fix_B_base_data_root_keep_display_96828.SC2Replay",
            ["replay.initData", "replay.initData.backup"],
            no_replacements,
        ),
        (
            "test_fix_M_B_equal_zlib_handles_initdata.SC2Replay",
            "test_fix_B_base_data_root_keep_display_96828.SC2Replay",
            ["replay.initData", "replay.initData.backup"],
            replacements,
        ),
        (
            "test_fix_N_B_equal_zlib_handles_details_initdata.SC2Replay",
            "test_fix_B_base_data_root_keep_display_96828.SC2Replay",
            ["replay.details", "replay.details.backup", "replay.initData", "replay.initData.backup"],
            replacements,
        ),
    ]

    print("old:", hex_list(old_handles))
    print("new:", hex_list(new_handles))
    for output, source, files, reps in jobs:
        shutil.copyfile(source, output)
        print("===", output, "===")
        for filename in files:
            print(replace_file_equal_archived_size(output, filename, reps))
        archive = MPQArchive(output)
        initdata = PROTOCOL.decode_replay_initdata(archive.read_file("replay.initData"))
        handles = initdata["m_syncLobbyState"]["m_gameDescription"]["m_cacheHandles"][-2:]
        print("verify:", hex_list(handles))


if __name__ == "__main__":
    main()
