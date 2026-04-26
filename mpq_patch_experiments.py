import binascii
import importlib.util
import shutil
import struct
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


def encrypt_mpq_table(archive, data, key):
    seed1 = key
    seed2 = 0xEEEEEEEE
    result = bytearray()

    for i in range(len(data) // 4):
        seed2 = (seed2 + archive.encryption_table[0x400 + (seed1 & 0xFF)]) & 0xFFFFFFFF
        value = struct.unpack("<I", data[i * 4 : i * 4 + 4])[0]
        encrypted = (value ^ (seed1 + seed2)) & 0xFFFFFFFF

        seed1 = (((~seed1 << 0x15) + 0x11111111) | (seed1 >> 0x0B)) & 0xFFFFFFFF
        seed2 = (value + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
        result.extend(struct.pack("<I", encrypted))

    return bytes(result)


def write_block_table(path):
    archive = MPQArchive(path)
    plain = b"".join(struct.pack("<4I", *entry) for entry in archive.block_table)
    key = archive._hash("(block table)", "TABLE")
    encrypted = encrypt_mpq_table(archive, plain, key)

    table_offset = archive.header["offset"] + archive.header["block_table_offset"]
    with open(path, "r+b") as output:
        output.seek(table_offset)
        output.write(encrypted)


def replace_single_unit_file(path, filename, replacements):
    archive = MPQArchive(path)
    hash_entry = archive.get_hash_table_entry(filename)
    if hash_entry is None:
        return f"{filename}: missing"

    block_index = hash_entry.block_table_index
    block_entry = archive.block_table[block_index]
    raw = archive.read_file(filename)
    patched = raw
    replacement_count = 0

    for old, new in replacements:
        found = patched.count(old)
        replacement_count += found
        patched = patched.replace(old, new)

    if len(patched) != len(raw):
        raise RuntimeError(f"{filename}: raw length changed")
    if not (block_entry.flags & MPQ_FILE_SINGLE_UNIT):
        raise RuntimeError(f"{filename}: not a single-unit MPQ file")

    if block_entry.flags & MPQ_FILE_COMPRESS:
        archived = bytes([2]) + zlib.compress(patched)
    else:
        archived = patched

    if len(archived) > block_entry.archived_size:
        raise RuntimeError(
            f"{filename}: new archived data is larger "
            f"({len(archived)} > {block_entry.archived_size})"
        )

    absolute_offset = archive.header["offset"] + block_entry.offset
    with open(path, "r+b") as output:
        output.seek(absolute_offset)
        output.write(archived)

    archive.block_table[block_index] = block_entry._replace(archived_size=len(archived))
    plain = b"".join(struct.pack("<4I", *entry) for entry in archive.block_table)
    key = archive._hash("(block table)", "TABLE")
    encrypted = encrypt_mpq_table(archive, plain, key)
    table_offset = archive.header["offset"] + archive.header["block_table_offset"]
    with open(path, "r+b") as output:
        output.seek(table_offset)
        output.write(encrypted)

    return (
        f"{filename}: replacements={replacement_count}, "
        f"archived_size {block_entry.archived_size}->{len(archived)}"
    )


def get_last_two_mod_handles(path):
    archive = MPQArchive(path)
    initdata = PROTOCOL.decode_replay_initdata(archive.read_file("replay.initData"))
    handles = initdata["m_syncLobbyState"]["m_gameDescription"]["m_cacheHandles"]
    return handles[-2:]


def hex_list(values):
    return [binascii.hexlify(value).decode().upper() for value in values]


def main():
    old_handles = get_last_two_mod_handles("test.SC2Replay")
    new_handles = get_last_two_mod_handles("96516.SC2Replay")
    replacements = list(zip(old_handles, new_handles))

    print("old:", hex_list(old_handles))
    print("new:", hex_list(new_handles))

    variants = [
        (
            "test_fix_F_B_handles_blocktable.SC2Replay",
            "test_fix_B_base_data_root_keep_display_96828.SC2Replay",
        ),
        (
            "test_fix_G_C_handles_blocktable.SC2Replay",
            "test_fix_C_full_96516.SC2Replay",
        ),
    ]
    files = [
        "replay.details",
        "replay.details.backup",
        "replay.initData",
        "replay.initData.backup",
    ]

    for output, source in variants:
        shutil.copyfile(source, output)
        print("===", output, "===")
        for filename in files:
            print(replace_single_unit_file(output, filename, replacements))

        verify_archive = MPQArchive(output)
        verify_init = PROTOCOL.decode_replay_initdata(verify_archive.read_file("replay.initData"))
        verify_handles = verify_init["m_syncLobbyState"]["m_gameDescription"]["m_cacheHandles"][-2:]
        print("verify:", hex_list(verify_handles))


if __name__ == "__main__":
    main()
