# 星际争霸 II 国服 5.0.15 回放修复可行性研究报告

## 1. 背景

近期国服《星际争霸 II》出现一次错误更新：录像显示版本为 `5.0.15.96828`，但该版本缺少可用云端数据；同时网易将可执行程序放置到了 `Base95841` 目录，而我们判断更合理的兼容目标是 `Base96516`。

我们最初提供的问题样本是 `test.SC2Replay`。后续为了做交叉对比，我们又加入了两个参考样本：

- `96516.SC2Replay`：错误更新前的正常回放。
- `96921.SC2Replay`：错误更新后重新补丁的新版本回放。

本报告记录我们到目前为止对回放结构、版本字段、Mod 校验、MPQ 写回行为的分析，以及多轮文件修复实验的结果。

## 2. 使用的仓库与脚本

我们使用了两个现有仓库：

- `mpyq-master`：用于读取 MPQ / MoPaQ 归档结构。
- `s2protocol-master`：用于解码 replay header、details、initData 等协议结构。

我们额外编写了三个 Python 脚本：

- `replay_version_gui.py`：GUI 工具，用于读取和另存为修改后的 replay header / metadata。
- `mpq_patch_experiments.py`：用于重写 MPQ 内部文件并更新 block table 的实验脚本。
- `zlib_equal_size_experiments.py`：用于构造等长合法 zlib 流的实验脚本。

三份源码已完整附在本文末尾。

## 3. SC2Replay 文件结构

`.SC2Replay` 本质是一个 MPQ 归档。StarCraft II 的回放文件通常以 `MPQ\x1b` UserData header 开始，而不是直接以普通 MPQ header `MPQ\x1a` 开始。

本次样本的结构可以概括为：

```text
文件起始
├─ MPQ UserData Header
│  ├─ magic = MPQ\x1b
│  ├─ user_data_size = 512
│  ├─ mpq_header_offset = 1024
│  ├─ user_data_header_size = 114 或 115
│  └─ content = NNet.Replay.SHeader 位流
│
└─ 偏移 1024
   ├─ MPQ Archive Header
   ├─ hash table
   ├─ block table
   └─ compressed file blocks
```

MPQ 内部文件列表基本一致：

```text
replay.attributes.events
replay.details
replay.details.backup
replay.game.events
replay.gamemetadata.json
replay.initData
replay.initData.backup
replay.load.info
replay.message.events
replay.resumable.events
replay.server.battlelobby
replay.smartcam.events
replay.sync.events
replay.sync.history
replay.tracker.events
```

本次研究重点关注：

- MPQ UserData `content`：存放 replay header，决定版本、base build、data build、root key。
- `replay.gamemetadata.json`：存放 `GameVersion`、`DataBuild`、`DataVersion`、`BaseBuild` 等 metadata。
- `replay.details` / `replay.details.backup`：包含地图、玩家和 cache handles。
- `replay.initData` / `replay.initData.backup`：包含 lobby / game description、map/mod sync checksum、cache handles。

## 4. 关键版本字段

我们用 `s2protocol-master` 中最新的 `protocol95299.py` 解码 UserData replay header。关键字段如下：

| 字段 | 作用推测 |
| --- | --- |
| `m_version.m_build` | 显示层面的构建号，通常对应 `GameVersion` 最后一段。 |
| `m_version.m_baseBuild` | 基础构建号，客户端可能据此选择 `BaseXXXXX`。 |
| `m_dataBuildNum` | 数据构建号，配合 root key / DataVersion 定位数据。 |
| `m_ngdpRootKey.m_data` | NGDP root key，对应 metadata 中的 `DataVersion`。 |
| `m_replayCompatibilityHash` | 兼容性 hash，本批样本均为全 0。 |

`s2protocol` 选择协议模块时也使用 `m_baseBuild`：

```text
baseBuild = header['m_version']['m_baseBuild']
protocol = build(baseBuild)
```

这说明 `m_baseBuild` 不是普通展示字段，而是回放解析和客户端加载路径中的关键字段。

## 5. 样本对比

三个样本的关键字段如下：

| 样本 | `m_build` | `m_baseBuild` | `m_dataBuildNum` | `m_ngdpRootKey` / `DataVersion` | metadata `BaseBuild` |
| --- | ---: | ---: | ---: | --- | --- |
| `test.SC2Replay` | 96828 | 95841 | 96828 | `15A93BC970AE1E127953345F89BCC14F` | `Base95841` |
| `96516.SC2Replay` | 96516 | 96516 | 96516 | `B5A551ED8B1A137FFFCC2BA50EC63173` | `Base96516` |
| `96921.SC2Replay` | 96921 | 96921 | 96921 | `C83ECFF50A077219461434CF97BB5497` | `Base96921` |

正常样本有明显规律：

```text
m_build == m_baseBuild == m_dataBuildNum
metadata GameVersion / DataBuild / DataVersion / BaseBuild 与 header 一致
```

问题样本 `test.SC2Replay` 则是：

```text
m_build = 96828
m_dataBuildNum = 96828
m_baseBuild = 95841
metadata BaseBuild = Base95841
```

因此，我们判断第一层异常不是“显示版本号错误”，而是 replay header 中的基础构建号和可用数据/客户端版本关系不一致。

## 6. 第一轮实验：只修改 Header 与 Metadata

我们先只修改 MPQ UserData 中的 replay header，并同步 `replay.gamemetadata.json`。这一类修改没有触碰 `replay.initData`、`replay.details` 等内部业务数据。

生成的副本：

| 文件 | 修改内容 |
| --- | --- |
| `test_fix_A_base_only.SC2Replay` | 只把 `m_baseBuild` 和 metadata `BaseBuild` 改为 `96516`。 |
| `test_fix_B_base_data_root_keep_display_96828.SC2Replay` | 保留显示版本 `96828`，但把 `m_baseBuild`、`m_dataBuildNum`、root key / `DataVersion` 切到 `96516`。 |
| `test_fix_C_full_96516.SC2Replay` | 完全伪装成 `96516`，包括 `m_build` 和 metadata `GameVersion`。 |

我们验证了 UserData replay header 可以被 `VersionedEncoder` 完整重编码：

```text
原始 header 长度: 115 字节
重编码原始 header: 字节完全一致
修改后 header 长度: 仍为 115 字节
```

载入后游戏反馈：

- `B` 和 `C` 可以成功进入读条。
- 读条快结束后，游戏弹出：

```text
已加载的Mod数据同此前游戏使用过的Mod数据不匹配。
```

第一轮结论：

- 修改 UserData replay header 是有效的。
- 版本定位已经从最早期错误进入到更深的地图 / Mod 加载阶段。
- 单纯修 header 与 metadata 不足以完整播放。

## 7. 第二轮分析：Mod Cache Handles

我们继续比较 `replay.initData` 和 `replay.details` 中的 Mod 相关字段。

关键观察：

| 样本 | `m_mapFileSyncChecksum` | `m_modFileSyncChecksum` | 后两个 Mod cache handles |
| --- | ---: | ---: | --- |
| `test.SC2Replay` | `612821817` | `636949408` | 与 `96516/96921` 不同 |
| `96516.SC2Replay` | `2726570838` | `4281607787` | 与 `96921` 相同 |
| `96921.SC2Replay` | `2726570838` | `636949408` | 与 `96516` 相同 |

`test` 的后两个 Mod cache handles：

```text
73326D610000434E7F41411AA597F4B46440D42A563348BF53822D2A68112F0104F9B891F6F05AE1
73326D610000434E01AE5D139A5256093A9FC6086E66F2841D7D08BDBFE5905350202C1C5D133796
```

`96516/96921` 的后两个 Mod cache handles：

```text
73326D610000434E658E520AA5DEB48866DC2B21B023DAA9A291BE4CF22FD9D785CA67F178132A87
73326D610000434ECE2868D95F359FDC3157F003EEFBB9FC12D651BC63486162EF92713E9C268B8B
```

我们推测读条末尾的 Mod 数据不匹配，可能与 `initData/details` 中记录的 Mod cache handles 或相关 checksum 有关。

## 8. 第二轮实验：替换 Mod Handles

我们尝试把 `test` 中后两个 Mod cache handles 替换为 `96516/96921` 的值。

生成的副本：

| 文件 | 修改内容 |
| --- | --- |
| `test_fix_D_B_plus_96516_mod_handles.SC2Replay` | 基于 B，替换 `details/details.backup/initData/initData.backup` 中的后两个 Mod handles。 |
| `test_fix_E_C_plus_96516_mod_handles.SC2Replay` | 基于 C，同样替换后两个 Mod handles。 |

第一次写回方式比较粗糙：

```text
解压内部文件
替换等长 40 字节 cache handle
重新 zlib 压缩
若新压缩块更短，用 0x00 补齐原 archived_size
不更新 block table
```

载入后游戏反馈：

```text
直接提示游戏数据损坏。
```

阶段判断：

- 这次失败可能不是 Mod handles 语义错误，而是 MPQ 内部压缩块写回方式不被客户端接受。
- `mpyq` 能读，不代表 SC2 客户端接受。

## 9. 第三轮实验：更新 MPQ Block Table

为了避免“压缩流补零”问题，我们实现了 `mpq_patch_experiments.py`：

- 重新压缩修改后的内部文件。
- 写入真实压缩数据长度。
- 更新 MPQ block table 中对应文件的 `archived_size`。
- 重新加密并写回 block table。

生成的副本：

| 文件 | 修改内容 |
| --- | --- |
| `test_fix_F_B_handles_blocktable.SC2Replay` | 基于 B，替换 `details + initData` 的后两个 Mod handles，并更新 block table。 |
| `test_fix_G_C_handles_blocktable.SC2Replay` | 基于 C，同上。 |
| `test_fix_H_B_initdata_handles_only.SC2Replay` | 基于 B，只替换 `initData/initData.backup`，并更新 block table。 |
| `test_fix_I_C_initdata_handles_only.SC2Replay` | 基于 C，只替换 `initData/initData.backup`，并更新 block table。 |

本地验证：

- `mpyq` 可以重新打开。
- `s2protocol` 可以解码 `replay.initData`。
- 替换后的 Mod handles 能被正确读出。

载入后游戏反馈：

```text
全部直接提示游戏数据损坏。
```

阶段判断：

- 问题不只是尾随 `0x00`。
- 即使 block table 与新压缩块长度一致，SC2 仍不接受。

## 10. 第四轮控制实验：内容不变，仅重压缩

为了区分“语义修改导致损坏”与“重写 MPQ 内部压缩块导致损坏”，我们生成了内容不变的控制组。

生成的副本：

| 文件 | 修改内容 |
| --- | --- |
| `test_fix_J_B_recompress_initdata_same.SC2Replay` | 基于 B，`initData/initData.backup` 解压内容完全不变，只重新压缩并更新 block table。 |
| `test_fix_K_B_recompress_details_initdata_same.SC2Replay` | 基于 B，`details/details.backup/initData/initData.backup` 解压内容完全不变，只重新压缩并更新 block table。 |

载入后游戏反馈：

```text
依旧提示游戏数据损坏。
```

这是非常关键的控制实验。因为解压后的内容完全没有变化，游戏仍然报损坏，说明 SC2 不只是验证解压后的 replay 语义数据，还可能验证：

- MPQ 内部压缩块字节；
- block table 或归档布局；
- sector / CRC / 压缩流物理表示；
- 某种 `mpyq` 未解析的 replay 完整性信息。

## 11. 第五轮控制实验：等长合法 Zlib 流

我们继续排除 block table 变化的影响。`zlib_equal_size_experiments.py` 构造了合法且等长的 zlib 流：

- 不更新 block table。
- 不改变 `archived_size`。
- zlib 解压结果正确。
- 通过追加合法的空 fixed-Huffman deflate block，让压缩流长度精确等于原始长度。

生成的副本：

| 文件 | 修改内容 |
| --- | --- |
| `test_fix_L_B_equal_zlib_same_initdata.SC2Replay` | 控制组：基于 B，`initData/initData.backup` 解压内容完全不变，只替换为等长合法 zlib 流。 |
| `test_fix_M_B_equal_zlib_handles_initdata.SC2Replay` | 基于 B，只改 `initData/initData.backup` 中后两个 Mod handles，等长 zlib。 |
| `test_fix_N_B_equal_zlib_handles_details_initdata.SC2Replay` | 基于 B，改 `details/details.backup/initData/initData.backup` 中后两个 Mod handles，等长 zlib。 |

载入后游戏反馈：

```text
L 依旧提示游戏数据损坏。
```

由于 `L` 的解压内容完全不变、block table 完全不变、archived size 完全不变，仍然损坏，因此 `M/N` 的语义测试意义已经降低。我们已经证明：只要改变内部压缩块字节，即使解压内容不变，SC2 也可能拒绝该 replay。

## 12. 当前结论

我们目前可以确认：

1. `test.SC2Replay` 的第一层问题是 `m_baseBuild = 95841`，而不是单纯显示版本 `96828`。
2. 修改 MPQ UserData replay header 与 metadata 可以让游戏进入读条阶段。
3. `B/C` 的读条末尾报错说明版本定位已通过，但 Mod 数据一致性校验未通过。
4. 修改 `replay.initData` / `replay.details` 可能是解决 Mod 数据不匹配的必要步骤。
5. 但当前所有重写 MPQ 内部压缩块的实验，包括“解压内容完全不变”的控制组，都会让游戏直接报数据损坏。
6. 因此，仅依靠当前 `mpyq + s2protocol` 的读写方式，尚不能完成完整修复。

当前可行性判断：

```text
部分修复可行：修改 header / metadata 可以推进到读条阶段。
完整修复尚未证明可行：内部 MPQ 文件块的修改会触发更早的损坏检查。
```

## 13. 后续建议

我们建议下一阶段优先研究“游戏数据损坏”的触发条件，而不是继续盲目替换 `initData/details` 字段。

可选方向：

1. 研究 SC2 replay MPQ 是否存在未解析的完整性校验。
2. 检查 MPQ sector CRC、压缩 flags、block table flags、archive size、sector table 等字段。
3. 尝试使用更完整的 MPQ 重包工具生成客户端可接受的 replay。
4. 逆向客户端中两个错误字符串的引用：
   - `已加载的Mod数据同此前游戏使用过的Mod数据不匹配。`
   - `游戏数据损坏`
5. 确认客户端究竟比较的是 cache handles、checksum、压缩块字节、还是更高层签名。

## 14. 附录 A：`replay_version_gui.py`

```python
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
```

## 15. 附录 B：`mpq_patch_experiments.py`

```python
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
```

## 16. 附录 C：`zlib_equal_size_experiments.py`

```python
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
```
# 星际争霸 II 国服 5.0.15 回放修复可行性研究报告

## 1. 背景

近期国服《星际争霸 II》出现一次错误更新：录像显示版本为 `5.0.15.96828`，但该版本缺少可用云端数据；同时网易将可执行程序放置到了 `Base95841` 目录，而理论上可兼容播放的版本应使用 `Base96516`。

用户提供的问题回放为：

- `test.SC2Replay`

后续又提供两个参考样本：

- `96516.SC2Replay`：错误更新前的正常回放。
- `96921.SC2Replay`：错误更新后重新补丁的新版本回放。

研究目标：

1. 分析 `SC2Replay` 文件结构。
2. 找出影响客户端选择版本、基础构建、数据构建和 Mod 数据的关键字段。
3. 评估是否能仅通过修改回放文件完成修复。
4. 记录多轮实验结果，为后续是否需要逆向客户端提供依据。

## 2. 使用的参考代码

本次分析主要依赖两个开源项目：

- `mpyq-master`
  - 用于读取 MPQ 归档结构。
  - 关键文件：`mpyq-master/mpyq.py`

- `s2protocol-master`
  - 用于解码 `SC2Replay` 内部协议数据。
  - 关键文件：
    - `s2protocol-master/s2protocol/s2_cli.py`
    - `s2protocol-master/s2protocol/versions/*.py`
    - `s2protocol-master/s2protocol/encoders.py`

本次新增的 Python 脚本源码：

- `replay_version_gui.py`
  - 简单 GUI 工具。
  - 用于读取和另存为修改后的 replay header / metadata。

- `mpq_patch_experiments.py`
  - MPQ 内部文件块修改实验。
  - 支持修改压缩块并更新 block table。

- `zlib_equal_size_experiments.py`
  - 等长 zlib 压缩流实验。
  - 尝试在不修改 block table 和 archived size 的情况下重写压缩块。

完整源码文件已随本报告一起放在当前工作目录中。

## 3. SC2Replay 基础文件结构

`.SC2Replay` 本质是一个 MPQ 归档。其头部通常不是直接以 `MPQ\x1a` 开始，而是带有 `MPQ\x1b` UserData header。

结构大致如下：

```text
文件起始
├─ MPQ UserData Header
│  ├─ magic = MPQ\x1b
│  ├─ user_data_size
│  ├─ mpq_header_offset
│  ├─ user_data_header_size
│  └─ content = Replay Header 位流
│
├─ padding / user data 区域
│
└─ MPQ Archive Header
   ├─ hash table
   ├─ block table
   └─ compressed file blocks
```

在本次样本中：

```text
mpq_header_offset = 1024
user_data_size = 512
user_data_header_size = 115 或 114
```

MPQ 内部常见文件：

```text
replay.attributes.events
replay.details
replay.details.backup
replay.game.events
replay.gamemetadata.json
replay.initData
replay.initData.backup
replay.load.info
replay.message.events
replay.resumable.events
replay.server.battlelobby
replay.smartcam.events
replay.sync.events
replay.sync.history
replay.tracker.events
```

其中本研究关注：

- MPQ UserData `content`
  - 存放 `NNet.Replay.SHeader`
  - 决定 replay header 中的版本、baseBuild、dataBuild、root key 等字段。

- `replay.gamemetadata.json`
  - 存放展示用或辅助索引用的 JSON 元数据。

- `replay.details` / `replay.details.backup`
  - 存放地图、玩家、cache handles 等数据。

- `replay.initData` / `replay.initData.backup`
  - 存放 lobby / game description / map-mod sync checksum / cache handles。

## 4. Replay Header 关键字段

使用 `s2protocol` 的最新协议文件解析 UserData header，可以得到如下结构：

```text
m_signature
m_version
  m_flags
  m_major
  m_minor
  m_revision
  m_build
  m_baseBuild
m_type
m_elapsedGameLoops
m_useScaledTime
m_ngdpRootKey
m_dataBuildNum
m_replayCompatibilityHash
m_ngdpRootKeyIsDevData
```

关键字段含义推测：

| 字段 | 作用 |
|---|---|
| `m_build` | 显示层面的构建号，通常与 `GameVersion` 对应。 |
| `m_baseBuild` | 基础构建号，可能决定客户端加载哪个 `BaseXXXXX`。 |
| `m_dataBuildNum` | 数据构建号，配合 root key / DataVersion 定位游戏数据。 |
| `m_ngdpRootKey` | NGDP 数据 root key，对应 metadata 的 `DataVersion`。 |
| `m_replayCompatibilityHash` | 兼容性哈希。本批样本均为全 0。 |

`s2protocol` 本身也通过 `m_baseBuild` 选择协议模块：

```text
baseBuild = header['m_version']['m_baseBuild']
protocol = build(baseBuild)
```

这说明 `m_baseBuild` 不是单纯展示字段，而是 replay 协议和基础数据选择的重要字段。

## 5. 三个样本的关键字段对比

### 5.1 `test.SC2Replay`

问题回放：

```text
GameVersion: 5.0.15.96828
m_build: 96828
m_baseBuild: 95841
m_dataBuildNum: 96828
m_ngdpRootKey / DataVersion: 15A93BC970AE1E127953345F89BCC14F
metadata BaseBuild: Base95841
```

`replay.gamemetadata.json`：

```json
{
    "GameVersion": "5.0.15.96828",
    "DataBuild": "96828",
    "DataVersion": "15A93BC970AE1E127953345F89BCC14F",
    "BaseBuild": "Base95841"
}
```

观察：

- 显示版本是 `96828`。
- 数据构建也是 `96828`。
- 但基础构建是 `95841`。
- 这与用户描述的“可执行程序被放在 Base95841，而正确 Base96516 缺执行文件”现象吻合。

### 5.2 `96516.SC2Replay`

错误更新前正常样本：

```text
GameVersion: 5.0.15.96516
m_build: 96516
m_baseBuild: 96516
m_dataBuildNum: 96516
m_ngdpRootKey / DataVersion: B5A551ED8B1A137FFFCC2BA50EC63173
metadata BaseBuild: Base96516
```

观察：

- `m_build == m_baseBuild == m_dataBuildNum == 96516`
- metadata 中的 `GameVersion`、`DataBuild`、`DataVersion`、`BaseBuild` 与 header 一致。

### 5.3 `96921.SC2Replay`

错误更新后重新补丁的新版本回放：

```text
GameVersion: 5.0.15.96921
m_build: 96921
m_baseBuild: 96921
m_dataBuildNum: 96921
m_ngdpRootKey / DataVersion: C83ECFF50A077219461434CF97BB5497
metadata BaseBuild: Base96921
```

观察：

- 新版本同样保持 `m_build == m_baseBuild == m_dataBuildNum`。
- 表明正常 replay 通常不会出现 `m_build/dataBuild` 与 `m_baseBuild` 分裂的情况。

## 6. 初步判断

`test.SC2Replay` 的异常不是简单显示版本错误，而是：

```text
m_build = 96828
m_dataBuildNum = 96828
m_baseBuild = 95841
metadata BaseBuild = Base95841
```

这会导致客户端可能按 `Base95841` 或 `96828` 数据路径尝试载入，但实际可用数据应落到 `96516` 兼容范围。

因此初步修复思路是：

1. 把 `m_baseBuild` 改成 `96516`。
2. 视情况把 `m_dataBuildNum` 和 `m_ngdpRootKey` 改成 `96516` 样本对应值。
3. 同步 `replay.gamemetadata.json`。
4. 如果仍失败，再检查 `replay.initData` / `replay.details` 中的 Mod cache handles 和 sync checksum。

## 7. 第一轮实验：只修改 UserData header 和 metadata

### 7.1 生成的文件

生成了三种副本：

```text
test_fix_A_base_only.SC2Replay
test_fix_B_base_data_root_keep_display_96828.SC2Replay
test_fix_C_full_96516.SC2Replay
```

### 7.2 A：只改 baseBuild

修改内容：

```text
m_baseBuild: 95841 -> 96516
metadata BaseBuild: Base95841 -> Base96516
```

保留：

```text
m_build = 96828
m_dataBuildNum = 96828
m_ngdpRootKey = 15A93BC970AE1E127953345F89BCC14F
GameVersion = 5.0.15.96828
DataBuild = 96828
DataVersion = 15A93BC970AE1E127953345F89BCC14F
```

### 7.3 B：保留显示 96828，但实际数据切到 96516

修改内容：

```text
m_baseBuild: 95841 -> 96516
m_dataBuildNum: 96828 -> 96516
m_ngdpRootKey: 15A93BC970AE1E127953345F89BCC14F -> B5A551ED8B1A137FFFCC2BA50EC63173
metadata DataBuild: 96828 -> 96516
metadata DataVersion: 15A93BC970AE1E127953345F89BCC14F -> B5A551ED8B1A137FFFCC2BA50EC63173
metadata BaseBuild: Base95841 -> Base96516
```

保留：

```text
m_build = 96828
GameVersion = 5.0.15.96828
```

### 7.4 C：完全伪装成 96516

修改内容：

```text
m_build: 96828 -> 96516
m_baseBuild: 95841 -> 96516
m_dataBuildNum: 96828 -> 96516
m_ngdpRootKey: 15A93BC970AE1E127953345F89BCC14F -> B5A551ED8B1A137FFFCC2BA50EC63173
metadata GameVersion: 5.0.15.96828 -> 5.0.15.96516
metadata DataBuild: 96828 -> 96516
metadata DataVersion: 15A93BC970AE1E127953345F89BCC14F -> B5A551ED8B1A137FFFCC2BA50EC63173
metadata BaseBuild: Base95841 -> Base96516
```

### 7.5 第一轮结果

用户反馈：

```text
B 和 C 修复后可以成功读条，
但是在读条快结束后弹出：
“已加载的Mod数据同此前游戏使用过的Mod数据不匹配。”
```

结论：

- 修改 UserData header / metadata 是有效的。
- 客户端已经通过了最初的版本和数据定位阶段。
- 后续失败发生在实际加载地图 / Mod 数据时。
- `B/C` 比原始文件更进一步，说明文件层面修复并非完全不可行。

## 8. 第二轮分析：Mod cache handles 与 checksum

对比 `test`、`96516`、`96921` 的 `replay.initData` 和 `replay.details`。

### 8.1 `m_modFileSyncChecksum`

对比结果：

```text
test.SC2Replay:
  m_modFileSyncChecksum = 636949408

96516.SC2Replay:
  m_modFileSyncChecksum = 4281607787

96921.SC2Replay:
  m_modFileSyncChecksum = 636949408
```

观察：

- `test` 与 `96921` 的 `m_modFileSyncChecksum` 一致。
- `test` 与 `96516` 的 `m_modFileSyncChecksum` 不一致。

这说明 `test` 的 Mod 同步校验更接近 `96921`，不是简单完全等于 `96516`。

### 8.2 cache handles

`test` 的前 5 个 cache handles 与 `96516/96921` 一致，但后两个不同。

`test` 后两个：

```text
73326D610000434E7F41411AA597F4B46440D42A563348BF53822D2A68112F0104F9B891F6F05AE1
73326D610000434E01AE5D139A5256093A9FC6086E66F2841D7D08BDBFE5905350202C1C5D133796
```

`96516/96921` 后两个：

```text
73326D610000434E658E520AA5DEB48866DC2B21B023DAA9A291BE4CF22FD9D785CA67F178132A87
73326D610000434ECE2868D95F359FDC3157F003EEFBB9FC12D651BC63486162EF92713E9C268B8B
```

推测：

- 读条末尾的 Mod 数据不匹配可能与这两个 Mod cache handles 有关。
- 但仅替换 handles 是否足够仍不确定。

## 9. 第二轮实验：替换 Mod cache handles

### 9.1 D/E：直接替换并补零

生成文件：

```text
test_fix_D_B_plus_96516_mod_handles.SC2Replay
test_fix_E_C_plus_96516_mod_handles.SC2Replay
```

修改内容：

- 基于 B / C。
- 替换以下文件中的后两个 Mod cache handles：
  - `replay.details`
  - `replay.details.backup`
  - `replay.initData`
  - `replay.initData.backup`

写回方式：

- 解压原始 MPQ 文件块。
- 字节替换 40 字节 cache handle。
- 重新 zlib 压缩。
- 如果压缩后比原 archived block 短，则用 `0x00` 补齐。
- 不更新 block table。

结果：

```text
打开直接报“游戏数据损坏”。
```

初步判断：

- 这种写回方式物理上不被 SC2 接受。
- `mpyq` 能读，不代表 SC2 的 MPQ / zlib 实现接受。
- 尾随 `0x00` 或压缩流长度不匹配可能触发客户端更严格检查。

## 10. 第三轮实验：更新 block table

### 10.1 F/G：替换 handles，同时更新 block table

生成文件：

```text
test_fix_F_B_handles_blocktable.SC2Replay
test_fix_G_C_handles_blocktable.SC2Replay
```

做法：

- 重新压缩修改后的内部文件。
- 把新的真实压缩长度写入 MPQ block table 的 `archived_size`。
- 按 MPQ 算法重新加密 block table。
- 写回归档。

验证：

- `mpyq` 可以重新打开。
- `replay.initData` 可以解码。
- 替换后的 handles 确实存在。

结果：

```text
用户反馈：依旧显示“游戏数据损坏”。
```

结论：

- 问题不只是“压缩流补零”。
- 即便 block table 更新后结构对 `mpyq` 可读，SC2 仍不接受。

### 10.2 H/I：只修改 initData，不动 details

生成文件：

```text
test_fix_H_B_initdata_handles_only.SC2Replay
test_fix_I_C_initdata_handles_only.SC2Replay
```

做法：

- 只修改：
  - `replay.initData`
  - `replay.initData.backup`
- 不修改：
  - `replay.details`
  - `replay.details.backup`
- 同样更新 block table。

结果：

```text
用户反馈：依旧显示“游戏数据损坏”。
```

结论：

- 只要重写 `replay.initData` 这类内部压缩块，SC2 就可能认为文件损坏。

## 11. 第四轮实验：内容不变，仅重压缩

为区分“语义修改导致损坏”还是“物理写回导致损坏”，生成控制组。

### 11.1 J/K

生成文件：

```text
test_fix_J_B_recompress_initdata_same.SC2Replay
test_fix_K_B_recompress_details_initdata_same.SC2Replay
```

做法：

- 基于 B。
- 解压内部文件。
- 不修改任何解压后的内容。
- 仅重新 zlib 压缩。
- 更新 block table。

J 修改：

```text
replay.initData
replay.initData.backup
```

K 修改：

```text
replay.details
replay.details.backup
replay.initData
replay.initData.backup
```

结果：

```text
用户反馈：也是损坏。
```

关键结论：

- 即使解压内容完全不变，只要重写内部压缩块并更新 block table，SC2 也会报损坏。
- 这说明 SC2 的校验不只是 replay 语义校验，也包含某种对 MPQ 内部物理块、压缩流或表结构的严格要求。

## 12. 第五轮实验：等长 zlib 压缩流

为排除 block table 变化带来的影响，尝试构造：

```text
解压内容相同或按需修改
压缩流是合法 zlib
archived_size 完全不变
block table 完全不变
```

做法：

- 使用 raw deflate + 人工追加空 fixed-Huffman deflate block。
- 保持 zlib 解压结果正确。
- 让最终 zlib stream 长度精确等于原始 archived size。

生成文件：

```text
test_fix_L_B_equal_zlib_same_initdata.SC2Replay
test_fix_M_B_equal_zlib_handles_initdata.SC2Replay
test_fix_N_B_equal_zlib_handles_details_initdata.SC2Replay
```

### 12.1 L：内容不变，等长 zlib

做法：

- 基于 B。
- `replay.initData` / `replay.initData.backup` 解压内容完全不变。
- 只替换为等长合法 zlib stream。
- 不更新 block table。

结果：

```text
用户反馈：依旧损坏。
```

### 12.2 M/N

M：

- 基于 B。
- 只修改 `initData/initData.backup` 中的后两个 handles。
- 使用等长 zlib。
- 不更新 block table。

N：

- 基于 B。
- 修改 `details/details.backup/initData/initData.backup` 中的后两个 handles。
- 使用等长 zlib。
- 不更新 block table。

由于 L 这个“内容不变控制组”已经损坏，M/N 的意义降低。它们即使损坏，也不能证明 handles 语义错误；因为物理压缩流重写本身已经足以触发损坏。

## 13. 当前核心结论

### 13.1 可以安全修改的部分

目前确认可安全修改：

```text
MPQ UserData 中的 replay header
replay.gamemetadata.json
```

表现：

- B/C 能进入读条。
- 说明 header / metadata 修改没有立即破坏文件。
- 说明版本定位确实被改变。

### 13.2 不可直接修改的部分

目前确认不能以现有方式安全修改：

```text
replay.initData
replay.initData.backup
replay.details
replay.details.backup
```

表现：

- 解压内容不变，仅重压缩，也会损坏。
- 等长合法 zlib 替换，也会损坏。
- 更新 block table 也会损坏。

这强烈暗示 SC2 客户端对 MPQ 内部压缩块或归档内容有额外完整性检查。

## 14. 对“是否需要逆向”的判断

从现阶段结果看：

```text
仅靠 s2protocol/mpyq 级别的字段修改，尚不能完整修复 replay。
```

但这不等于“文件层面绝对无法修复”。更准确的判断是：

1. 外层 UserData header 可以改。
2. metadata 可以改。
3. 内部 MPQ 文件块不能用普通解压-重压缩方式改。
4. 客户端可能依赖：
   - 原始压缩块字节；
   - MPQ block table 中未被 `mpyq` 暴露的校验；
   - 某种 replay manifest / sync / hash；
   - 客户端内部的 MPQ 读取差异；
   - 或更高层 replay 完整性校验。

因此，后续若要继续推进，有两个方向：

### 14.1 文件格式方向

继续研究 MPQ / SC2Replay 是否存在未解析字段或隐式校验：

- MPQ sector CRC。
- 压缩块 checksum。
- archive size / table offset / high offset 相关字段。
- 是否存在隐藏 listfile 外的校验文件。
- 是否有 replay 内部事件或 sync history 引用 initData/details 的 hash。

优点：

- 如果找到完整格式规则，仍可以纯文件修复。

缺点：

- 需要比 `mpyq` 更完整的 MPQ 写入器和 SC2Replay 专用知识。

### 14.2 客户端逆向方向

逆向 SC2 处理 replay 的路径：

- 找到报错字符串：
  - `已加载的Mod数据同此前游戏使用过的Mod数据不匹配。`
  - `游戏数据损坏`
- 定位触发条件。
- 分析客户端到底比较了哪些字段。
- 判断是否存在内部 hash、cache handle 校验、MPQ block 校验。

优点：

- 可以直接确定失败条件。
- 避免继续盲目猜字段。

缺点：

- 工作量更大。
- 可能涉及符号缺失、混淆、反调试等问题。

## 15. 当前最可能的失败链路

综合所有实验，当前推测的失败链路如下：

```text
原始 test.SC2Replay
  -> header 指向 Base95841 / DataBuild96828
  -> 客户端无法找到或加载正确数据
  -> 无法正常播放

B/C 修复
  -> header / metadata 指向 96516
  -> 版本和数据定位通过
  -> 读条开始
  -> 载入 Mod 阶段
  -> replay 中记录的 Mod 数据与当前加载数据不一致
  -> 弹出 Mod 数据不匹配

尝试修改 initData/details
  -> 只要重写 MPQ 内部压缩块
  -> 即使解压内容不变
  -> 客户端直接认为游戏数据损坏
```

这说明目前存在两个不同层级的问题：

1. 语义层问题：
   - B/C 的 Mod 数据不匹配。

2. 物理/完整性层问题：
   - 内部压缩块不能被现有方式重写。

## 16. 实验文件清单

### 16.1 原始与参考样本

```text
test.SC2Replay
96516.SC2Replay
96921.SC2Replay
```

### 16.2 第一轮：header / metadata

```text
test_fix_A_base_only.SC2Replay
test_fix_B_base_data_root_keep_display_96828.SC2Replay
test_fix_C_full_96516.SC2Replay
```

结果：

```text
B/C 可读条，但最终 Mod 数据不匹配。
```

### 16.3 第二轮：直接替换 Mod handles

```text
test_fix_D_B_plus_96516_mod_handles.SC2Replay
test_fix_E_C_plus_96516_mod_handles.SC2Replay
```

结果：

```text
直接显示游戏数据损坏。
```

### 16.4 第三轮：更新 block table

```text
test_fix_F_B_handles_blocktable.SC2Replay
test_fix_G_C_handles_blocktable.SC2Replay
test_fix_H_B_initdata_handles_only.SC2Replay
test_fix_I_C_initdata_handles_only.SC2Replay
```

结果：

```text
直接显示游戏数据损坏。
```

### 16.5 第四轮：内容不变，仅重压缩

```text
test_fix_J_B_recompress_initdata_same.SC2Replay
test_fix_K_B_recompress_details_initdata_same.SC2Replay
```

结果：

```text
直接显示游戏数据损坏。
```

### 16.6 第五轮：等长 zlib

```text
test_fix_L_B_equal_zlib_same_initdata.SC2Replay
test_fix_M_B_equal_zlib_handles_initdata.SC2Replay
test_fix_N_B_equal_zlib_handles_details_initdata.SC2Replay
```

结果：

```text
L 内容不变也损坏。
M/N 因 L 已失败，不能证明语义修改是否正确。
```

## 17. 附录：Python 源码说明

### 17.1 `replay_version_gui.py`

用途：

- Tkinter GUI 工具。
- 打开 `.SC2Replay`。
- 读取 replay header 与 metadata。
- 支持编辑：
  - `m_build`
  - `m_baseBuild`
  - `m_dataBuildNum`
  - `m_ngdpRootKey`
  - `m_replayCompatibilityHash`
  - `GameVersion`
  - `DataBuild`
  - `DataVersion`
  - `BaseBuild`
- 保存时另存为新文件，不修改原文件。
- 提供“套用 96516 样本”按钮。

运行：

```powershell
python replay_version_gui.py
```

### 17.2 `mpq_patch_experiments.py`

用途：

- 用于第二、三、四轮 MPQ 内部文件块实验。
- 支持：
  - 替换 replay 内部文件中的 Mod cache handles。
  - 重新 zlib 压缩。
  - 更新 MPQ block table 的 `archived_size`。
  - 重新加密并写回 block table。

运行：

```powershell
python mpq_patch_experiments.py
```

### 17.3 `zlib_equal_size_experiments.py`

用途：

- 用于第五轮等长 zlib 实验。
- 目标是在：
  - 不更新 block table；
  - 不改变 archived size；
  - zlib 解压内容正确；
  - 压缩流合法；
  
  的条件下重写内部压缩块。

运行：

```powershell
python zlib_equal_size_experiments.py
```

## 18. 最终阶段性结论

截至目前，最可靠的结论是：

```text
通过修改 replay header / metadata，可以让问题回放进入读条；
但要彻底解决 Mod 数据不匹配，需要修改 replay.initData/details；
而当前所有对 MPQ 内部压缩块的重写方式都会触发“游戏数据损坏”。
```

因此，现阶段纯文件修复的可行性是：

```text
部分可行：可以修复版本定位，让回放进入读条。
完全修复：尚未证明可行。
```

后续若继续研究，建议优先：

1. 逆向或动态调试 SC2 客户端中“游戏数据损坏”的触发路径。
2. 查明是否存在内部 MPQ 块级 hash / replay 内容 hash。
3. 如果确认没有不可伪造签名，再实现完整、客户端兼容的 MPQ 重包。
4. 最后再回到 Mod handles / checksum 的语义修正。

# 星际争霸 II 国服 5.0.15 回放修复可行性研究报告

## 1. 背景

近期国服客户端出现一次错误更新：目标游戏版本显示应为 `5.0.15.96828`，但网易将可执行程序放置到了 `Base95841` 文件夹，而正确可用的 `Base96516` 目录没有放置对应可执行文件。结果是部分回放在启动或播放时会被客户端判定为游戏损坏、数据缺失或 Mod 数据不匹配。

本次研究围绕以下目标展开：

- 分析 `SC2Replay` 文件结构与关键版本字段。
- 对比更新前正常样本 `96516.SC2Replay`、错误更新期间样本 `test.SC2Replay`、重新补丁后的新版本样本 `96921.SC2Replay`。
- 尝试从文件层面修复 `test.SC2Replay`，使其能够使用 `Base96516` 播放。
- 评估继续从文件层面修复的可行性，以及是否需要进入 StarCraft II 客户端录像加载逻辑逆向分析。

## 2. 使用的样本与工具

### 2.1 样本文件

| 文件 | 说明 |
| --- | --- |
| `test.SC2Replay` | 目标问题回放，显示版本为 `5.0.15.96828`，但存在错误的 base build 指向 |
| `96516.SC2Replay` | 更新前正常回放样本，用于提取 `96516` 的 root key / DataVersion 与 Mod 引用 |
| `96921.SC2Replay` | 错误更新后重新补丁产生的新版本正常样本，用于对照后续版本行为 |

### 2.2 代码仓库

| 仓库 | 用途 |
| --- | --- |
| `mpyq-master` | 读取 MPQ / MoPaQ 归档结构，提取 replay 内部文件 |
| `s2protocol-master` | 解码 SC2 replay header、details、initData 等协议结构 |

### 2.3 额外编写的辅助脚本

| 文件 | 用途 |
| --- | --- |
| `replay_version_gui.py` | 简单 GUI 工具，读取/修改 replay header 与 metadata 的关键版本字段，另存为新文件 |
| `mpq_patch_experiments.py` | 尝试修改 MPQ 内部文件，并同步更新 block table |
| `zlib_equal_size_experiments.py` | 尝试构造等长合法 zlib 流，在不改 block table 的情况下替换内部压缩块 |

## 3. SC2Replay 文件结构基础

### 3.1 总体结构

`.SC2Replay` 文件本质上是一个 MPQ 归档。StarCraft II 的 replay 通常不是直接以 `MPQ\x1a` 开头，而是以 `MPQ\x1b` 的 MPQ UserData 形式开头。

本次样本中的关键布局如下：

```text
文件开头:
  MPQ UserData Header
    magic = MPQ\x1b
    user_data_size = 512
    mpq_header_offset = 1024
    user_data_header_size = 114 或 115
    content = NNet.Replay.SHeader 位流

偏移 1024:
  MPQ Header
  Hash Table
  Block Table
  MPQ 内部文件数据块
```

其中 `MPQ UserData Header` 中的 `content` 是 replay header，不是普通 MPQ 内部文件。它对客户端选择版本、base build、data build 有直接影响。

### 3.2 MPQ 内部文件

三个样本均包含类似的内部文件列表：

```text
replay.attributes.events
replay.details
replay.details.backup
replay.game.events
replay.gamemetadata.json
replay.initData
replay.initData.backup
replay.load.info
replay.message.events
replay.resumable.events
replay.server.battlelobby
replay.smartcam.events
replay.sync.events
replay.sync.history
replay.tracker.events
```

其中与本次修复关系最密切的是：

| 文件/区域 | 作用 |
| --- | --- |
| MPQ UserData `SHeader` | 决定显示版本、base build、data build、root key |
| `replay.gamemetadata.json` | 供客户端/UI/外部工具读取的 metadata，包含 GameVersion、DataBuild、DataVersion、BaseBuild |
| `replay.details` / backup | 地图、玩家、cache handles 等信息 |
| `replay.initData` / backup | lobby/game description、map/mod checksum、cache handles 等载入校验相关信息 |

## 4. Replay Header 关键字段

使用 `s2protocol` 最新协议文件 `protocol95299.py` 可以成功解码三个样本的 UserData replay header。

Replay header 的关键字段包括：

| 字段 | 说明 |
| --- | --- |
| `m_version.m_build` | 构建号，通常对应显示版本最后一段 |
| `m_version.m_baseBuild` | base build，决定客户端可能使用哪个 `BaseXXXXX` |
| `m_dataBuildNum` | 数据构建号，决定数据版本定位 |
| `m_ngdpRootKey.m_data` | DataVersion / NGDP root key，定位数据内容 |
| `m_replayCompatibilityHash` | 兼容性 hash，本次样本均为全 0 |

对 `test.SC2Replay` 的解析结果：

```text
m_version:
  m_major = 5
  m_minor = 0
  m_revision = 15
  m_build = 96828
  m_baseBuild = 95841

m_dataBuildNum = 96828
m_ngdpRootKey = 15A93BC970AE1E127953345F89BCC14F
m_replayCompatibilityHash = 00000000000000000000000000000000
```

这个结果说明：问题回放并不是单纯“显示版本为 96828”，而是存在更关键的不一致：

```text
显示/数据版本: 96828
base build: 95841
```

如果客户端根据 `m_baseBuild` 寻找 `Base95841`，就会落入本次错误更新制造的问题路径。

## 5. 样本对比

### 5.1 Header 与 metadata 对比

| 样本 | `m_build` | `m_baseBuild` | `m_dataBuildNum` | `m_ngdpRootKey` / DataVersion | metadata `BaseBuild` |
| --- | ---: | ---: | ---: | --- | --- |
| `test.SC2Replay` | 96828 | 95841 | 96828 | `15A93BC970AE1E127953345F89BCC14F` | `Base95841` |
| `96516.SC2Replay` | 96516 | 96516 | 96516 | `B5A551ED8B1A137FFFCC2BA50EC63173` | `Base96516` |
| `96921.SC2Replay` | 96921 | 96921 | 96921 | `C83ECFF50A077219461434CF97BB5497` | `Base96921` |

正常样本有一个明显规律：

```text
m_build == m_baseBuild == m_dataBuildNum
metadata GameVersion/DataBuild/DataVersion/BaseBuild 与 header 一致
```

而问题样本：

```text
m_build = 96828
m_dataBuildNum = 96828
m_baseBuild = 95841
metadata BaseBuild = Base95841
```

### 5.2 Mod 相关字段对比

对 `replay.initData` 中的 `m_syncLobbyState.m_gameDescription` 做对比：

| 样本 | `m_mapFileSyncChecksum` | `m_modFileSyncChecksum` | 后两个 Mod cache handles |
| --- | ---: | ---: | --- |
| `test.SC2Replay` | `612821817` | `636949408` | 与 `96516/96921` 不同 |
| `96516.SC2Replay` | `2726570838` | `4281607787` | 与 `96921` 相同 |
| `96921.SC2Replay` | `2726570838` | `636949408` | 与 `96516` 相同 |

关键观察：

- `test` 和 `96921` 的 `m_modFileSyncChecksum` 相同，均为 `636949408`。
- `96516` 和 `96921` 的后两个 Mod cache handles 相同。
- `test` 的后两个 Mod cache handles 与 `96516/96921` 不同。
- `test` 和 `96516/96921` 的 `m_mapFileSyncChecksum` 不同，但这可能与地图本身有关，不一定是本次 Mod 错误的直接原因。

这提示：`B/C` 版本能进入读条但末尾报 Mod 数据不匹配，可能与 `initData/details` 中记录的 Mod cache handles 或其它 Mod 数据指纹有关。

## 6. 录像加载与校验过程推测

基于样本行为和文件字段，当前推测客户端至少经过以下阶段：

```text
1. 打开 SC2Replay
2. 读取 MPQ UserData replay header
3. 根据 m_baseBuild / m_dataBuildNum / m_ngdpRootKey 定位客户端与数据版本
4. 读取 replay.gamemetadata.json / replay.details / replay.initData
5. 加载地图与 Mod 数据
6. 对比 replay 中记录的 map/mod checksum、cache handles 或其它数据指纹
7. 开始播放事件流
```

本次测试中出现了两类错误：

| 错误表现 | 推测发生阶段 | 说明 |
| --- | --- | --- |
| 能读条，读条末尾报“已加载的 Mod 数据同此前游戏使用过的 Mod 数据不匹配” | 第 5-6 阶段 | header/data 定位已通过，但 replay 内记录的 Mod 数据指纹与实际加载数据不一致 |
| 打开后直接报“游戏数据损坏” | 更早阶段，可能是 MPQ 内部文件完整性/压缩块校验 | 修改 MPQ 内部压缩文件后，客户端拒绝该 replay |

## 7. 第一轮修复：只修改 Header 与 Metadata

### 7.1 修改方式

对 `test.SC2Replay` 生成了三种副本：

| 文件 | 修改内容 |
| --- | --- |
| `test_fix_A_base_only.SC2Replay` | 只改 `m_baseBuild: 95841 -> 96516`，metadata `BaseBuild` 同步为 `Base96516` |
| `test_fix_B_base_data_root_keep_display_96828.SC2Replay` | 保留显示版本 `96828`，但改 `m_baseBuild/m_dataBuildNum/rootKey/DataVersion/BaseBuild` 到 `96516` |
| `test_fix_C_full_96516.SC2Replay` | 完全改成 `96516`：`m_build/m_baseBuild/m_dataBuildNum/rootKey/metadata` 均同步到 `96516` |

### 7.2 技术细节

UserData replay header 使用 `VersionedEncoder` 重编码。验证结果：

```text
原始 header 长度: 115 字节
重编码原始 header: 字节完全一致
修改后的 header 长度: 仍为 115 字节
```

因此这一类修改可以直接在文件偏移 `16` 处替换 UserData content，不需要重建 MPQ。

`replay.gamemetadata.json` 也进行了同步写入。该文件虽然位于 MPQ 内部，但本次 metadata 修改后仍可被工具解码，且用户测试没有因 metadata 修改本身触发“游戏数据损坏”。

### 7.3 用户验证结果

| 文件 | 用户验证结果 |
| --- | --- |
| `B` | 能成功进入读条，但读条快结束时报“已加载的 Mod 数据同此前游戏使用过的 Mod 数据不匹配” |
| `C` | 同上 |

### 7.4 阶段结论

这一轮说明：

- 修改 UserData replay header 是有效的。
- `m_baseBuild` / `m_dataBuildNum` / `m_ngdpRootKey` 的修改能让客户端越过最早期版本选择阶段。
- 仅修复 header 与 metadata 不足以完成播放。
- 下一阻塞点是 Mod 数据一致性校验。

## 8. 第二轮修复：尝试修改 Mod Cache Handles

### 8.1 修改依据

对比发现：

- `96516` 与 `96921` 的最后两个 Mod cache handles 一致。
- `test` 的最后两个 Mod cache handles 不同。

因此尝试将 `test` 中 `replay.details`、`replay.details.backup`、`replay.initData`、`replay.initData.backup` 的后两个 Mod cache handles 替换为 `96516/96921` 的值。

### 8.2 生成文件

| 文件 | 修改方式 |
| --- | --- |
| `test_fix_D_B_plus_96516_mod_handles.SC2Replay` | 基于 B，替换 details + initData 中后两个 Mod handles，压缩后补 0 保持 block size |
| `test_fix_E_C_plus_96516_mod_handles.SC2Replay` | 基于 C，同上 |

### 8.3 用户验证结果

| 文件 | 用户验证结果 |
| --- | --- |
| `D` | 直接报“游戏数据损坏” |
| `E` | 直接报“游戏数据损坏” |

### 8.4 阶段结论

此时尚不能判断是“Mod handles 改错了”，还是“MPQ 内部文件写回方式不被客户端接受”。

因为 D/E 使用了较粗糙的 MPQ 内部压缩块替换方式：

```text
新压缩流长度 < 原 archived_size
写入新压缩流
尾部用 0x00 补齐
不更新 block table
```

`mpyq` 能读取这种文件，但 SC2 客户端可能不接受尾随垃圾数据或压缩流严格性不同。

## 9. 第三轮修复：更新 MPQ Block Table

### 9.1 修改方式

为了避免“压缩流补 0”问题，编写 `mpq_patch_experiments.py`：

- 重新压缩修改后的内部文件。
- 写入真实新压缩数据。
- 修改 MPQ `block table` 中对应文件的 `archived_size`。
- 重新加密并写回 `block table`。

### 9.2 生成文件

| 文件 | 修改方式 |
| --- | --- |
| `test_fix_F_B_handles_blocktable.SC2Replay` | 基于 B，替换 details + initData handles，并更新 block table |
| `test_fix_G_C_handles_blocktable.SC2Replay` | 基于 C，同上 |
| `test_fix_H_B_initdata_handles_only.SC2Replay` | 基于 B，只替换 initData handles，并更新 block table |
| `test_fix_I_C_initdata_handles_only.SC2Replay` | 基于 C，只替换 initData handles，并更新 block table |

### 9.3 本地解析验证

这些文件均可被 `mpyq` 重新打开，且替换后的 handles 能从 `replay.initData` 解码出来。

示例：

```text
replay.initData archived_size: 2478 -> 2029
replay.initData.backup archived_size: 2184 -> 1806
```

### 9.4 用户验证结果

| 文件 | 用户验证结果 |
| --- | --- |
| `F` | 直接报“游戏数据损坏” |
| `G` | 直接报“游戏数据损坏” |
| `H` | 直接报“游戏数据损坏” |
| `I` | 直接报“游戏数据损坏” |

### 9.5 阶段结论

更新 block table 后依旧损坏，说明问题不只是“压缩流后面补 0”。

可能原因包括：

- SC2 对 MPQ 内部压缩块有额外完整性校验。
- SC2 对 block table、hash table 或 archive size 有比 `mpyq` 更严格的要求。
- Replay 内部另有索引、校验或签名覆盖了内部文件压缩数据。
- 我们的 MPQ 写回虽然对 `mpyq` 可读，但仍不完全符合 SC2 使用的 MPQ 实现预期。

## 10. 第四轮控制实验：内容不变，仅重压缩

### 10.1 实验目的

为了区分：

```text
是 Mod handles 语义改错导致损坏
还是只要改写 MPQ 内部压缩块就会损坏
```

生成内容不变、仅重新压缩写回的控制组。

### 10.2 生成文件

| 文件 | 修改方式 |
| --- | --- |
| `test_fix_J_B_recompress_initdata_same.SC2Replay` | 基于 B，`initData/initData.backup` 解压内容完全不变，仅重压缩并更新 block table |
| `test_fix_K_B_recompress_details_initdata_same.SC2Replay` | 基于 B，`details/details.backup/initData/initData.backup` 解压内容完全不变，仅重压缩并更新 block table |

### 10.3 用户验证结果

| 文件 | 用户验证结果 |
| --- | --- |
| `J` | 直接报“游戏数据损坏” |
| `K` | 直接报“游戏数据损坏” |

### 10.4 阶段结论

这是非常关键的结果。

因为 J/K 的解压后内容没有变化，理论上 replay 语义完全等同于 B。但客户端仍然直接报“游戏数据损坏”。

这说明：

```text
SC2 客户端不仅关心 replay 内部文件解压后的语义内容，
还关心 MPQ 内部压缩块的物理表示、block table、或某种覆盖压缩数据的完整性信息。
```

也就是说，当前损坏不是 Mod handles 语义导致，而是 MPQ 内部文件被重写本身触发了更早的完整性校验。

## 11. 第五轮控制实验：等长合法 zlib 流

### 11.1 实验目的

J/K 改变了 block table 中的 `archived_size`。为了排除 block table 变化影响，继续尝试：

- 不修改 block table。
- 不改变 archived_size。
- 构造合法、等长的 zlib 流。
- 对于控制组，解压内容完全不变。

### 11.2 实现方式

编写 `zlib_equal_size_experiments.py`：

- 使用 raw deflate 流。
- 在 deflate 数据后追加合法的空 fixed-Huffman block。
- 最后写入正确 Adler32。
- 确保整体 zlib stream 长度精确等于原始 archived block 长度。

这种方式避免了：

```text
尾部 0x00 非法填充
block table archived_size 变化
```

### 11.3 生成文件

| 文件 | 修改方式 |
| --- | --- |
| `test_fix_L_B_equal_zlib_same_initdata.SC2Replay` | 控制组：基于 B，initData 解压内容不变，zlib 流等长替换 |
| `test_fix_M_B_equal_zlib_handles_initdata.SC2Replay` | 基于 B，只改 initData handles，zlib 流等长 |
| `test_fix_N_B_equal_zlib_handles_details_initdata.SC2Replay` | 基于 B，改 details + initData handles，zlib 流等长 |

### 11.4 用户验证结果

| 文件 | 用户验证结果 |
| --- | --- |
| `L` | 依旧直接报“游戏数据损坏” |
| `M/N` | 同类实验预期也无法绕过，因为 L 的解压内容完全未变仍损坏 |

### 11.5 阶段结论

L 是最强的控制组：

```text
解压内容不变
archived_size 不变
block table 不变
zlib 流合法
但 SC2 仍报游戏数据损坏
```

这基本排除了普通 MPQ block table 或 zlib 流长度问题。

更合理的解释是：

```text
SC2Replay 内部存在某种覆盖 MPQ 内部压缩数据字节的完整性校验，
或者 SC2 使用了比 zlib 解压结果更严格的 MPQ 压缩块验证策略。
```

由于 `mpyq` 不验证这些信息，所以它能读；SC2 客户端会拒绝。

## 12. 当前结论

### 12.1 已确认可行的修改

以下修改目前被客户端接受到“进入读条”阶段：

- 修改 MPQ UserData replay header。
- 修改 `m_baseBuild`。
- 修改 `m_dataBuildNum`。
- 修改 `m_ngdpRootKey` / `DataVersion`。
- 同步修改 `replay.gamemetadata.json`。

对应成功进入读条的代表文件：

```text
test_fix_B_base_data_root_keep_display_96828.SC2Replay
test_fix_C_full_96516.SC2Replay
```

### 12.2 已确认不足的修改

只修 header / metadata 不足以完成播放。

表现：

```text
读条快结束后：
“已加载的Mod数据同此前游戏使用过的Mod数据不匹配。”
```

说明进入了更深层的地图/Mod 数据一致性校验。

### 12.3 当前文件层面修复的主要障碍

一旦尝试修改 MPQ 内部文件，甚至只是重写 `replay.initData` 的压缩流而不改变解压内容，客户端就直接报：

```text
游戏数据损坏
```

这说明当前不能简单地通过 `mpyq` 级别的读写逻辑修改 MPQ 内部文件。

### 12.4 是否已经必须逆向客户端

当前结论是：

```text
如果目标只是修 header，让客户端走到读条阶段，文件层面已经可行。
如果目标是完整播放，需要修改 initData/details 或绕过 Mod 数据一致性校验。
而目前修改 MPQ 内部压缩块会触发“游戏数据损坏”。
因此，继续推进需要分析 SC2 对 replay MPQ 内部文件的完整性校验机制。
```

这不一定意味着必须立即做完整客户端逆向，但至少需要研究以下之一：

1. StarCraft II replay MPQ 内部文件是否有隐藏 hash / 签名 / 校验表。
2. SC2 使用的 MPQ 解压/校验实现是否要求压缩块字节级保持原样。
3. 是否有官方或更完整的 MPQ 写入/重包工具能生成 SC2 接受的 replay MPQ。
4. 客户端在报“游戏数据损坏”前具体检查了哪些字段或数据块。

## 13. 后续研究方向

### 13.1 完整 MPQ 重包

当前尝试都是原地 patch。后续可尝试完整重建 MPQ：

- 重新生成 hash table。
- 重新生成 block table。
- 重新布局所有内部文件。
- 使用 SC2/暴雪兼容的压缩方式。
- 保留或重建 UserData header。

但风险是：

- SC2 replay 可能要求内部文件顺序、压缩方式、sector 布局完全符合特定模式。
- 如果存在覆盖整个归档或内部文件压缩块的签名，完整重包仍会失败。

### 13.2 查找隐藏校验来源

需要重点调查：

| 可能位置 | 说明 |
| --- | --- |
| MPQ sector CRC | `mpyq` 读取时不校验，但 SC2 可能校验 |
| `replay.load.info` | 文件较小，可能包含加载/校验辅助信息 |
| `replay.sync.history` | 样本中读取为 `None`，但仍需确认 block 语义 |
| `replay.server.battlelobby` | 可能包含服务端 lobby / 数据版本信息 |
| MPQ block table flags | 是否有 SC2 特定压缩、CRC、sector table 规则 |
| 客户端内 replay loader | 最终需要确定“游戏数据损坏”的触发条件 |

### 13.3 继续做差分样本分析

建议收集更多样本：

- 同一地图、同一 Mod、不同版本的正常 replay。
- `96516` 与 `96921` 的同地图样本。
- 错误更新期间的多个 `96828` replay。

目标是区分：

```text
哪些字段随地图变化
哪些字段随 Mod 版本变化
哪些字段随客户端 data build 变化
哪些字段是 replay 文件完整性相关
```

### 13.4 逆向分析切入点

如果进入客户端逆向，建议从错误文本入手：

```text
“已加载的Mod数据同此前游戏使用过的Mod数据不匹配。”
“游戏数据损坏。”
```

逆向目标：

- 定位错误字符串引用。
- 回溯触发条件。
- 确认是哪个文件、字段、hash 或校验函数失败。
- 判断是否能在 replay 文件中补齐对应校验。

## 14. 总体判断

现阶段最可靠的结论如下：

1. `test.SC2Replay` 的第一层问题是 header 中 `m_baseBuild = 95841`，而不是单纯显示版本 `96828`。
2. 将 header / metadata 对齐到 `96516` 可以让客户端进入读条，说明版本定位问题可从文件层面部分修复。
3. 读条末尾的 Mod 数据不匹配说明 replay 内部仍记录着与当前可加载 Mod 数据不一致的信息。
4. 尝试修改 `initData/details` 相关 Mod 信息会触发更早的“游戏数据损坏”。
5. 即使 `initData` 解压内容完全不变，只替换为等长合法 zlib 流，SC2 仍报损坏，说明 replay 内部压缩块可能存在字节级完整性校验或 SC2 特定 MPQ 校验。
6. 因此，仅依靠当前 `mpyq + s2protocol` 的读写能力，尚不足以完成完整修复。
7. 下一步应优先研究 SC2 对 replay MPQ 内部文件的完整性校验；如果无法从公开格式中确认，则需要对客户端 replay loader 进行逆向分析。

## 15. 当前推荐保留的可用中间产物

| 文件 | 价值 |
| --- | --- |
| `test_fix_B_base_data_root_keep_display_96828.SC2Replay` | 当前最有价值的半修复样本：能读条，但 Mod 校验失败 |
| `test_fix_C_full_96516.SC2Replay` | 完全伪装为 96516 的对照样本 |
| `test_fix_L_B_equal_zlib_same_initdata.SC2Replay` | 关键控制组：内容不变但压缩流变化，仍损坏，用于证明存在更深层校验 |
| `replay_version_gui.py` | 可继续用于安全修改 UserData header 与 metadata |
| `mpq_patch_experiments.py` | 用于复现实验：更新 block table 后仍损坏 |
| `zlib_equal_size_experiments.py` | 用于复现实验：等长合法 zlib 流仍损坏 |

