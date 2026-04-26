import binascii
import copy
import glob
import importlib.util
import io
import json
import os
import shutil
import sys
import tkinter as tk
import zlib
from tkinter import filedialog, messagebox, ttk


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
MPYQ_DIR = os.path.join(ROOT_DIR, "mpyq-master")
S2PROTOCOL_DIR = os.path.join(ROOT_DIR, "s2protocol-master")

sys.path.insert(0, MPYQ_DIR)
sys.path.insert(0, S2PROTOCOL_DIR)

from mpyq import MPQArchive, MPQ_FILE_COMPRESS, MPQ_FILE_SINGLE_UNIT  # noqa: E402
from s2protocol.encoders import VersionedEncoder  # noqa: E402


METADATA_FILE = "replay.gamemetadata.json"
USER_DATA_CONTENT_OFFSET = 16


def load_latest_protocol():
    versions_dir = os.path.join(S2PROTOCOL_DIR, "s2protocol", "versions")
    protocol_files = glob.glob(os.path.join(versions_dir, "protocol*.py"))
    if not protocol_files:
        raise RuntimeError("没有找到 s2protocol 的 protocol*.py 文件")

    def protocol_number(path):
        name = os.path.splitext(os.path.basename(path))[0]
        return int(name.replace("protocol", ""))

    latest = max(protocol_files, key=protocol_number)
    module_name = os.path.splitext(os.path.basename(latest))[0]
    spec = importlib.util.spec_from_file_location(module_name, latest)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROTOCOL = load_latest_protocol()


def to_encoder_value(value):
    if isinstance(value, bytes):
        return value.decode("latin1")
    if isinstance(value, dict):
        return {key: to_encoder_value(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [to_encoder_value(inner) for inner in value]
    return value


def encode_replay_header(header):
    output = io.StringIO()
    encoder = VersionedEncoder(output, PROTOCOL.typeinfos)
    encoder.instance(to_encoder_value(header), PROTOCOL.replay_header_typeid)
    return output.getvalue().encode("latin1")


def hex_to_16_bytes(text, field_name):
    cleaned = text.strip().replace(" ", "")
    if len(cleaned) != 32:
        raise ValueError(f"{field_name} 必须是 16 字节 / 32 位十六进制字符串")
    try:
        return binascii.unhexlify(cleaned)
    except binascii.Error as exc:
        raise ValueError(f"{field_name} 不是有效十六进制字符串") from exc


def parse_replay(path):
    archive = MPQArchive(path)
    user_data = archive.header.get("user_data_header")
    if not user_data:
        raise RuntimeError("该文件没有 MPQ UserData header，可能不是 SC2Replay")

    header_bytes = user_data["content"]
    header = PROTOCOL.decode_replay_header(header_bytes)

    metadata = {}
    metadata_bytes = archive.read_file(METADATA_FILE)
    if metadata_bytes:
        metadata = json.loads(metadata_bytes.decode("utf-8"))

    return {
        "archive": archive,
        "header": header,
        "header_bytes": header_bytes,
        "metadata": metadata,
        "metadata_bytes": metadata_bytes,
    }


def patch_metadata_in_place(path, metadata):
    archive = MPQArchive(path)
    hash_entry = archive.get_hash_table_entry(METADATA_FILE)
    if hash_entry is None:
        return "未找到 replay.gamemetadata.json，已跳过 metadata"

    block_entry = archive.block_table[hash_entry.block_table_index]
    old_raw = archive.read_file(METADATA_FILE)
    if old_raw is None:
        return "无法读取 replay.gamemetadata.json，已跳过 metadata"

    new_raw = json.dumps(metadata, indent=4).encode("utf-8")
    if len(new_raw) > len(old_raw):
        raise RuntimeError(
            "新的 metadata 未压缩内容比原始内容更长，当前脚本不重建 MPQ，"
            f"无法安全写入：{len(new_raw)} > {len(old_raw)}"
        )

    # MPQ block table 记录了未压缩大小；补空白让未压缩大小保持不变。
    new_raw = new_raw + b" " * (len(old_raw) - len(new_raw))

    if not (block_entry.flags & MPQ_FILE_SINGLE_UNIT):
        raise RuntimeError("metadata 不是 single-unit MPQ 文件，当前脚本不支持安全写入")

    if block_entry.flags & MPQ_FILE_COMPRESS:
        new_archived = bytes([2]) + zlib.compress(new_raw)
    else:
        new_archived = new_raw

    if len(new_archived) > block_entry.archived_size:
        raise RuntimeError(
            "新的 metadata 压缩后比原始 archived block 更长，当前脚本不重建 MPQ，"
            f"无法安全写入：{len(new_archived)} > {block_entry.archived_size}"
        )

    absolute_offset = archive.header["offset"] + block_entry.offset
    with open(path, "r+b") as output:
        output.seek(absolute_offset)
        output.write(new_archived)
        output.write(bytes(block_entry.archived_size - len(new_archived)))

    return f"metadata 已写入：raw={len(new_raw)}, archived={len(new_archived)}/{block_entry.archived_size}"


class ReplayVersionGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SC2Replay 版本字段修改工具")
        self.geometry("760x520")

        self.source_path = None
        self.parsed = None
        self.vars = {}

        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill=tk.X)

        ttk.Button(top, text="打开 SC2Replay", command=self.open_replay).pack(side=tk.LEFT)
        ttk.Button(top, text="另存为新文件", command=self.save_as).pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="套用 96516 样本", command=self.apply_96516_sample).pack(side=tk.LEFT)

        self.path_label = ttk.Label(top, text="未打开文件")
        self.path_label.pack(side=tk.LEFT, padx=12)

        body = ttk.Frame(self, padding=10)
        body.pack(fill=tk.BOTH, expand=True)

        header_box = ttk.LabelFrame(body, text="MPQ UserData / Replay Header", padding=10)
        header_box.pack(fill=tk.X)
        self._add_field(header_box, "m_build", "m_build", 0)
        self._add_field(header_box, "m_baseBuild", "m_baseBuild", 1)
        self._add_field(header_box, "m_dataBuildNum", "m_dataBuildNum", 2)
        self._add_field(header_box, "m_ngdpRootKey / DataVersion", "m_ngdpRootKey", 3, width=44)
        self._add_field(header_box, "m_replayCompatibilityHash", "m_replayCompatibilityHash", 4, width=44)

        metadata_box = ttk.LabelFrame(body, text="replay.gamemetadata.json", padding=10)
        metadata_box.pack(fill=tk.X, pady=10)
        self.update_metadata_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            metadata_box,
            text="保存时同步 metadata",
            variable=self.update_metadata_var,
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))
        self._add_field(metadata_box, "GameVersion", "GameVersion", 1, width=30)
        self._add_field(metadata_box, "DataBuild", "DataBuild", 2, width=30)
        self._add_field(metadata_box, "DataVersion", "DataVersion", 3, width=44)
        self._add_field(metadata_box, "BaseBuild", "BaseBuild", 4, width=30)

        self.status = tk.Text(body, height=8, wrap=tk.WORD)
        self.status.pack(fill=tk.BOTH, expand=True)
        self.log("用法：打开回放，修改字段，然后另存为新文件。原始文件不会被修改。")

    def _add_field(self, parent, label, key, row, width=18):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, padx=(0, 8), pady=3)
        var = tk.StringVar()
        entry = ttk.Entry(parent, textvariable=var, width=width)
        entry.grid(row=row, column=1, sticky=tk.W, pady=3)
        self.vars[key] = var

    def log(self, message):
        self.status.insert(tk.END, message + "\n")
        self.status.see(tk.END)

    def open_replay(self):
        path = filedialog.askopenfilename(
            title="选择 SC2Replay",
            filetypes=[("SC2Replay", "*.SC2Replay"), ("所有文件", "*.*")],
            initialdir=ROOT_DIR,
        )
        if not path:
            return
        try:
            self.source_path = path
            self.parsed = parse_replay(path)
            self._fill_fields()
            self.path_label.config(text=os.path.basename(path))
            self.log(f"已打开：{path}")
        except Exception as exc:
            messagebox.showerror("读取失败", str(exc))

    def _fill_fields(self):
        header = self.parsed["header"]
        version = header["m_version"]
        metadata = self.parsed["metadata"]

        self.vars["m_build"].set(str(version.get("m_build", "")))
        self.vars["m_baseBuild"].set(str(version.get("m_baseBuild", "")))
        self.vars["m_dataBuildNum"].set(str(header.get("m_dataBuildNum", "")))
        self.vars["m_ngdpRootKey"].set(
            binascii.hexlify(header.get("m_ngdpRootKey", {}).get("m_data", b"")).decode().upper()
        )
        self.vars["m_replayCompatibilityHash"].set(
            binascii.hexlify(header.get("m_replayCompatibilityHash", {}).get("m_data", b"")).decode().upper()
        )

        for key in ("GameVersion", "DataBuild", "DataVersion", "BaseBuild"):
            self.vars[key].set(str(metadata.get(key, "")))

    def apply_96516_sample(self):
        sample_path = os.path.join(ROOT_DIR, "96516.SC2Replay")
        if not self.parsed:
            messagebox.showinfo("提示", "请先打开要修改的回放")
            return
        if not os.path.exists(sample_path):
            messagebox.showerror("找不到样本", f"未找到：{sample_path}")
            return
        try:
            sample = parse_replay(sample_path)
            sample_header = sample["header"]
            sample_root = binascii.hexlify(sample_header["m_ngdpRootKey"]["m_data"]).decode().upper()
            self.vars["m_baseBuild"].set("96516")
            self.vars["m_dataBuildNum"].set("96516")
            self.vars["m_ngdpRootKey"].set(sample_root)
            self.vars["DataBuild"].set("96516")
            self.vars["DataVersion"].set(sample_root)
            self.vars["BaseBuild"].set("Base96516")
            self.log("已从 96516.SC2Replay 套用 baseBuild/dataBuild/rootKey/DataVersion。")
        except Exception as exc:
            messagebox.showerror("套用失败", str(exc))

    def _collect_header(self):
        header = copy.deepcopy(self.parsed["header"])
        version = header["m_version"]
        version["m_build"] = int(self.vars["m_build"].get().strip())
        version["m_baseBuild"] = int(self.vars["m_baseBuild"].get().strip())
        header["m_dataBuildNum"] = int(self.vars["m_dataBuildNum"].get().strip())
        header["m_ngdpRootKey"]["m_data"] = hex_to_16_bytes(self.vars["m_ngdpRootKey"].get(), "m_ngdpRootKey")
        header["m_replayCompatibilityHash"]["m_data"] = hex_to_16_bytes(
            self.vars["m_replayCompatibilityHash"].get(),
            "m_replayCompatibilityHash",
        )
        return header

    def _collect_metadata(self):
        metadata = copy.deepcopy(self.parsed["metadata"])
        for key in ("GameVersion", "DataBuild", "DataVersion", "BaseBuild"):
            value = self.vars[key].get()
            if value:
                metadata[key] = value
        return metadata

    def save_as(self):
        if not self.source_path or not self.parsed:
            messagebox.showinfo("提示", "请先打开一个 SC2Replay 文件")
            return

        default_name = os.path.splitext(os.path.basename(self.source_path))[0] + "_patched.SC2Replay"
        target_path = filedialog.asksaveasfilename(
            title="另存为",
            initialdir=os.path.dirname(self.source_path),
            initialfile=default_name,
            defaultextension=".SC2Replay",
            filetypes=[("SC2Replay", "*.SC2Replay"), ("所有文件", "*.*")],
        )
        if not target_path:
            return

        try:
            new_header = encode_replay_header(self._collect_header())
            old_header = self.parsed["header_bytes"]
            if len(new_header) != len(old_header):
                raise RuntimeError(
                    "新的 replay header 长度发生变化，当前脚本不重建 MPQ，"
                    f"无法安全写入：{len(new_header)} != {len(old_header)}"
                )

            shutil.copyfile(self.source_path, target_path)
            with open(target_path, "r+b") as output:
                output.seek(USER_DATA_CONTENT_OFFSET)
                output.write(new_header)

            metadata_status = "metadata 未同步"
            if self.update_metadata_var.get():
                metadata_status = patch_metadata_in_place(target_path, self._collect_metadata())

            verify = parse_replay(target_path)
            version = verify["header"]["m_version"]
            root_hex = binascii.hexlify(verify["header"]["m_ngdpRootKey"]["m_data"]).decode().upper()
            self.log(f"已保存：{target_path}")
            self.log(
                "验证："
                f"m_build={version['m_build']}, "
                f"m_baseBuild={version['m_baseBuild']}, "
                f"m_dataBuildNum={verify['header']['m_dataBuildNum']}, "
                f"root={root_hex}"
            )
            self.log(metadata_status)
            messagebox.showinfo("保存完成", f"已另存为：\n{target_path}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))


if __name__ == "__main__":
    ReplayVersionGui().mainloop()
