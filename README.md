# 星际争霸 II 国服 5.0.15 回放修复可行性研究报告

研究相关样本：https://github.com/ProbiusOfficial/sc2replayfixpan



近期国服《星际争霸 II》出现一次错误更新：录像显示版本为 `5.0.15.96828`，但该版本缺少可用云端数据；同时网易将可执行程序放置到了 `Base95841` 目录，而我们判断更合理的兼容目标是 `Base96516`。

我们最初提供的问题样本是 `test.SC2Replay`。后续为了做交叉对比，我们又加入了两个参考样本：

- `96516.SC2Replay`：错误更新前的正常回放。
- `96921.SC2Replay`：错误更新后重新补丁的新版本回放。

本报告记录我们到目前为止对回放结构、版本字段、Mod 校验、MPQ 写回行为的分析，以及多轮文件修复实验的结果。

## 使用的仓库与脚本

我们使用了两个现有仓库：

- `mpyq-master`：用于读取 MPQ / MoPaQ 归档结构。
- `s2protocol-master`：用于解码 replay header、details、initData 等协议结构。

我们额外编写了三个 Python 脚本：

- `replay_version_gui.py`：GUI 工具，用于读取和另存为修改后的 replay header / metadata。
- `mpq_patch_experiments.py`：用于重写 MPQ 内部文件并更新 block table 的实验脚本。
- `zlib_equal_size_experiments.py`：用于构造等长合法 zlib 流的实验脚本。

三份源码已完整附在本文末尾。

## SC2Replay 文件结构

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

## 关键版本字段

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

## 样本对比

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

## 第一轮实验：只修改 Header 与 Metadata

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

## 第二轮分析：Mod Cache Handles

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

## 第二轮实验：替换 Mod Handles

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

## 第三轮实验：更新 MPQ Block Table

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

## 第四轮控制实验：内容不变，仅重压缩

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

## 第五轮控制实验：等长合法 Zlib 流

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

## 当前结论

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

## 后续建议

我们建议下一阶段优先研究“游戏数据损坏”的触发条件，而不是继续盲目替换 `initData/details` 字段。

可选方向：

1. 研究 SC2 replay MPQ 是否存在未解析的完整性校验。
2. 检查 MPQ sector CRC、压缩 flags、block table flags、archive size、sector table 等字段。
3. 尝试使用更完整的 MPQ 重包工具生成客户端可接受的 replay。
4. 逆向客户端中两个错误字符串的引用：
   - `已加载的Mod数据同此前游戏使用过的Mod数据不匹配。`
   - `游戏数据损坏`
5. 确认客户端究竟比较的是 cache handles、checksum、压缩块字节、还是更高层签名。

## 附录 A：`replay_version_gui.py`

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

## 附录 B：`mpq_patch_experiments.py`

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

## 附录 C：`zlib_equal_size_experiments.py`

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
