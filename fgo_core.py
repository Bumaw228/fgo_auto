import os
import sys
import time
import subprocess
import re
import socket
import struct
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict

import cv2
import numpy as np

from coords import TEMPLATE_ROI, ROI_VERIFY_EVERY, LONG_PRESS_MS

# ==========================================
# 🔧 全域設定
# ==========================================

# Windows 專用旗標：讓 subprocess 不要閃出黑色命令視窗
CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

# 🐞 除錯開關：正式發布時改成 False，可大幅減少主控台 I/O、加快主迴圈
DEBUG = False

# 只有列在這裡的圖片，在 DEBUG 模式下才會印出相似度
DEBUG_TEMPLATES = {
    'ap_recovery_check.png', 'attack.png', 'battle_start.png', 'blue_apple.png',
    'bond_ce_close.png', 'bond_screen.png', 'bronze_apple.png', 'close_btn.png',
    'close_x.png', 'continue_battle.png', 'decide_btn.png', 'drop_screen.png',
    'exp_screen.png', 'friend_request.png', 'gold_apple.png', 'menu_button.png',
    'network_retry.png', 'next_btn.png', 'quest_start.png', 'refresh_btn.png',
    'refresh_yes.png', 'reject_friend.png', 'silver_apple.png', 'sp_no_star.png',
    'sp_use_star.png', 'sp_use_star_disabled.png', 'support_check.png',
    'support_update.png', 'team_confirm.png', 'turn_1.png', 'turn_2.png', 'turn_3.png',
    'select_target_text.png', 'order_change_btn.png', 'order_change_confirm_btn.png',
    'retreat_btn.png', 'retreat_decide_btn.png', 'servant_detail_close_x.png',
    'mission_start.png', 'inventory_full_close.png', 'back_btn.png', 'fgo_icon.png',
    'class_all.png', 'class_saber.png', 'class_archer.png', 'class_lancer.png',
    'class_rider.png', 'class_caster.png', 'class_assassin.png', 'class_berserker.png',
    'class_extra.png', 'class_mix.png',
    'auto_form_btn1.png', 'auto_form_btn2.png', 'auto_form_btn3.png',
    'skip_confirm.png', 'go_to_story_stage.png', 'interlude_active.png',
    'go_to_interlude_list.png', 'formation_limit.png', 'mandatory_slot.png',
    'select_from_support.png',
}

# 邏輯運算用的基準畫布（所有座標都以此為準）
CANVAS_W = 1920
CANVAS_H = 1080

# 影像快取上限（張數）
TEMPLATE_CACHE_SIZE = 60

# 🔬 開發用：記錄每張模板實際被找到的位置，寫入 roi_log.csv
#    收集完資料後請改回 False，否則每次命中都會寫檔
ROI_RECORD = False

# ⏱️ 開發用：統計 ADB 各類指令的耗時，用來判斷是否值得改成常駐連線。
#    正式發布時請改回 False。
ADB_PROFILE = False


# ⏱️ ADB 耗時統計：{類別: [耗時(ms), ...]}
_adb_timings = {}


def _record_adb_time(kind, ms):
    _adb_timings.setdefault(kind, []).append(ms)


def print_adb_profile():
    """印出 ADB 耗時統計。可在腳本停止時呼叫。"""
    if not _adb_timings:
        return
    print("=" * 62)
    print("⏱️  ADB 指令耗時統計")
    print(f"{'類別':<12}{'次數':>7}{'平均':>10}{'最小':>10}{'最大':>10}{'總計':>11}")
    print("-" * 62)
    grand = 0.0
    for kind in sorted(_adb_timings, key=lambda k: -sum(_adb_timings[k])):
        v = _adb_timings[kind]
        total = sum(v)
        grand += total
        print(f"{kind:<12}{len(v):>7}{total/len(v):>9.0f}ms{min(v):>9.0f}ms{max(v):>9.0f}ms{total/1000:>10.1f}s")
    print("-" * 62)
    print(f"{'合計':<12}{sum(len(v) for v in _adb_timings.values()):>7}{'':>29}{grand/1000:>10.1f}s")

    # 常駐連線只能改善「送指令」的固定開銷，截圖因為是二進位通常無法納入
    tap = _adb_timings.get("input_tap", []) or _adb_timings.get("input_swipe", [])
    if tap:
        avg = sum(tap) / len(tap)
        print(f"\n💡 點擊/滑動共 {len(tap)} 次，平均 {avg:.0f}ms、總計 {sum(tap)/1000:.1f}s")
        print(f"   若改成常駐連線（假設可降到 10ms），約可省下 {(sum(tap) - len(tap)*10)/1000:.1f}s")
    print("=" * 62)


def get_base_dir():
    """取得程式所在目錄，PyInstaller 打包後也能正確指向 exe 外層。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _resolve_adb():
    """優先使用專案內建的 adb，找不到才退回系統 PATH。

    這樣使用者不需要自己安裝 Android SDK 或設定環境變數。
    注意 adb.exe 旁邊必須有 AdbWinApi.dll 與 AdbWinUsbApi.dll，缺一不可。
    """
    base = get_base_dir()
    candidates = [
        os.path.join(base, "platform-tools", "adb.exe"),
        os.path.join(base, "adb.exe"),
    ]
    for p in candidates:
        if os.path.exists(p):
            print(f"[INIT] 使用內建 ADB: {p}")
            return p
    print("[INIT] 未找到內建 ADB，改用系統 PATH")
    return "adb"


# 全專案共用同一個 adb 路徑，main_ui.py 也要 import 這個常數
ADB_EXE = _resolve_adb()

# 常見模擬器的 ADB 連接埠，自動偵測失敗時會逐一嘗試連線
COMMON_ADB_PORTS = [
    "127.0.0.1:5555",    # 通用 / MuMu
    "127.0.0.1:7555",    # MuMu 舊版
    "127.0.0.1:16384",   # MuMu 12
    "127.0.0.1:62001",   # 夜神 Nox
    "127.0.0.1:21503",   # 逍遙 Memu
    "127.0.0.1:16416",   # MuMu 12 多開第 2 台
    "127.0.0.1:16448",   # MuMu 12 多開第 3 台
    "127.0.0.1:62025",   # 夜神多開第 2 台
]


# 只給 socket 探測用的候選埠清單。
#
# 探測一個埠只要 11~13ms（有東西在聽）或吃滿逾時（沒有），比 adb connect 到空埠的
# 2430ms 便宜兩個數量級，所以這份清單可以列得比 COMMON_ADB_PORTS 更廣。
# COMMON_ADB_PORTS 維持原樣不要擴充 —— 那份是給 adb connect 逐一嘗試用的，
# 每多一個埠就多 2.4 秒。
PROBE_PORTS = [
    16384, 16416, 16448, 16480, 16512,   # MuMu 12，多開每個實例 +32
    7555,                                # MuMu 6 / 舊版
    5555, 5557, 5559, 5561,              # 通用 / 雷電 / BlueStacks
    62001, 62025, 62026, 62027,          # 夜神 Nox
    21503, 21513,                        # 逍遙 MEmu
]

# 已學到是「別名」的埠：同一台模擬器的第二、第三個連接埠。
# 連上它們只會拿到重複的裝置，學會之後就不必再連 —— 否則每次偵測都要重連一次
# 再斷開，實測白花約 1.5 秒。
#
# 別名的歸屬**不是固定的**（實測 MuMu 重開後 7555 會換成屬於另一個實例），
# 所以只要偵測到的裝置組合有變動，就把整份快取丟掉重新學，
# 避免「某個別名埠後來變成別台模擬器的主要埠」時漏掉那台。
_alias_ports = set()
_alias_basis = None      # 學到這份快取時，偵測結果是哪一組裝置

# socket 探測逾時。實測有在聽的埠 11~13ms 就連上，設 50ms 留約 4 倍餘裕。
# 就算真的漏掉，後面的路徑 2／3 仍會用 adb connect 補救。
PROBE_TIMEOUT = 0.05


def _port_is_open(port, timeout=PROBE_TIMEOUT):
    """本機這個埠有沒有東西在聽。連上就立刻關閉，不送出任何資料。"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _connect_listening_ports(already):
    """對「有在聽、但 adb 還不知道」的埠做 adb connect，回傳新連上的裝置清單。

    回傳清單而非數量，是為了讓呼叫端能在事後把「確認是重複別名」的那些斷開 ——
    我們製造的連線要由我們自己收乾淨。

    多開的第二、三台模擬器**不會自己註冊到 adb**，必須有人主動 connect 才看得到。
    原本只在裝置清單全空時才掃埠，所以第一台佔住清單之後就再也找不到其他台 ——
    使用者只能自己把埠號填進欄位。

    先用 socket 篩一遍是關鍵：adb connect 到沒東西聽的埠要 2430ms，
    掃完整份 PROBE_PORTS 要 19 秒以上；改成先探測後只連活的，整體降到約 0.3~0.8 秒。
    """
    known = {d.rsplit(":", 1)[-1] for d in already if ":" in d}
    candidates = [p for p in PROBE_PORTS
                  if str(p) not in known and p not in _alias_ports]
    if not candidates:
        return 0

    # 探測彼此完全獨立，並行跑掉整份清單的等待時間：
    # 逐一探測全部 16 個埠實測 1044ms，並行後只剩單一逾時的時間（約 70ms）。
    with ThreadPoolExecutor(max_workers=len(candidates)) as pool:
        listening = [p for p, ok in
                     zip(candidates, pool.map(_port_is_open, candidates)) if ok]

    added = []
    for port in listening:
        # connect 會改動 adb 伺服器狀態，維持逐一執行不要並行。
        # 逾時給 6 秒：剛 kill-server 之後伺服器要重新啟動，4 秒實測不夠。
        dev = f"127.0.0.1:{port}"
        r = _run_adb(["connect", dev], timeout=6)
        out = (r.stdout or "").lower()
        # "already connected" 代表 adb 本來就知道，不算新發現
        if "connected to" in out and "already" not in out:
            print(f"[偵測] 新連上 {dev}")
            added.append(dev)
    return added


def _disconnect_aliases(added, kept):
    """把我們自己連上、但事後確認是重複別名的連線斷開。

    每次 adb connect 成功，adb 伺服器就會永久記住那條連線。模擬器常同時在多個埠上聽
    （實測 MuMu 的 5555 / 5557 / 7555 都是別名），全部留著的話裝置清單會隨每次偵測
    越積越多 —— 不只汙染機器上其他工具看到的清單，也讓往後每一次驗證都要多問好幾台。

    只斷開這一輪自己新連上的。原本就在清單裡的（`known` 會跳過，不會進 added）
    一律不碰，因為那可能是使用者或其他工具建立的。
    """
    global _alias_basis

    # 裝置組合變了就重新學：先前記下的別名歸屬可能已經不成立
    basis = frozenset(kept)
    if basis != _alias_basis:
        _alias_ports.clear()
        _alias_basis = basis

    extra = [d for d in added if d not in kept]
    if not extra:
        return
    for d in extra:
        _run_adb(["disconnect", d], timeout=4)
        port = d.rsplit(":", 1)[-1]
        if port.isdigit():
            _alias_ports.add(int(port))     # 記住，下次不必再連
    print(f"[偵測] 已斷開 {len(extra)} 個重複的別名連接埠：{', '.join(extra)}")


def kill_adb_server():
    """關閉常駐的 adb 伺服器。

    ⚠️ kill-server 是全域的，會影響其他正在使用 adb 的程式
       （scrcpy、Android Studio 等），而且模擬器通常會自己再叫起來，
       所以預設不呼叫，由使用者在設定中決定。

    值得關掉的兩個理由：
      1. 常駐的 adb.exe 會鎖住 platform-tools 裡的檔案，讓自動更新覆蓋失敗
      2. 使用者常反映「程式關了 adb.exe 還在」
    """
    try:
        subprocess.run([ADB_EXE, "kill-server"], capture_output=True,
                       timeout=10, creationflags=CREATE_NO_WINDOW)
        print("🔌 [ADB] 伺服器已關閉")
        return True
    except Exception as e:
        print(f"⚠️ [ADB] 關閉伺服器失敗: {e}")
        return False


def _run_adb(args, timeout=15):
    """執行不指定裝置的 adb 指令（devices / connect / kill-server 等）。"""
    try:
        return subprocess.run(
            [ADB_EXE] + args, capture_output=True, text=True,
            # 🚀 必須指定 utf-8：繁中 Windows 預設用 cp950 解碼，
            #    遇到 adb 回傳的中文或特殊字元會拋 UnicodeDecodeError
            encoding='utf-8', errors='ignore',
            timeout=timeout, creationflags=CREATE_NO_WINDOW
        )
    except Exception as e:
        print(f"⚠️ [ADB] {' '.join(args)} 失敗: {e}")
        return subprocess.CompletedProcess(args, 1, '', '')


def list_devices():
    """回傳目前已連線且狀態正常的裝置清單。"""
    out = _run_adb(["devices"]).stdout or ""
    devices = []
    for line in out.strip().splitlines()[1:]:      # 第一行是標題，略過
        parts = line.split('\t')
        # 只收 state 為 device 的，排除 offline / unauthorized
        if len(parts) == 2 and parts[1].strip() == "device":
            devices.append(parts[0].strip())
    return devices


def list_devices_unique():
    """列出裝置，並把同一台模擬器的多個連接埠合併成一筆。

    給 UI 的啟動檢查用。它跟 list_devices() 一樣不主動 connect，
    但必須跟「自動偵測」報出一致的台數 —— 否則會出現啟動時說 4 台、
    按下自動偵測卻說 2 台的矛盾。單台時 _verify 會短路，成本為零。
    """
    return _verify(list_devices())


def detect_devices(status_cb=None):
    """自動偵測模擬器，供 UI 的「自動偵測」按鈕使用。

    依序嘗試：直接列舉 → 主動連線常見埠 → 重啟 adb 伺服器後再試。
    status_cb 是選用的回呼，用來即時更新 UI 文字。

    三條路徑的出口都會過 _verify()。呼叫端（UI 的「自動偵測」）是直接取 devices[0]
    填進欄位並顯示「已連線」，所以清單第一筆若是殘留的死連線，使用者會看到綠字卻
    怎麼跑都失敗；而同一台模擬器佔多個埠時，不合併會讓 UI 謊報台數。
    """
    def report(msg):
        print(f"[偵測] {msg}")
        if status_cb:
            status_cb(msg)

    added = []      # 這一輪由我們主動連上的，事後要把多餘的收掉

    def verified(found):
        # 單筆不需要驗證（見 _verify 的說明），所以也不用告知使用者在等什麼
        if len(found) > 1:
            report(f"偵測到 {len(found)} 筆連線，正在確認...")
        result = _verify(found)
        _disconnect_aliases(added, result)
        return result

    devices = list_devices()

    # 不論清單是否已有裝置，都先掃一次沒連上的埠。
    # 多開的第二、三台不會自己註冊到 adb，而原本只在清單全空時才掃，
    # 等於第一台一出現就再也找不到其他台。靠 socket 預篩，這一步約 0.3~0.8 秒。
    report("搜尋模擬器...")
    added = _connect_listening_ports(devices)
    if added:
        devices = list_devices()

    if devices:
        return verified(devices)

    # 後備：socket 探測不到、但 adb connect 得到的情況（例如非 PROBE_PORTS 的埠）
    report("嘗試連線常見模擬器連接埠...")
    for port in COMMON_ADB_PORTS:
        # 連得上的埠通常 1 秒內就回應，逾時設短一點避免累積等待
        _run_adb(["connect", port], timeout=4)
    devices = list_devices()
    if devices:
        return verified(devices)

    # 最後手段：重啟伺服器（版本衝突時通常能救回來）
    report("重置 ADB 伺服器中...")
    _run_adb(["kill-server"], timeout=10)
    _run_adb(["start-server"], timeout=20)
    for port in COMMON_ADB_PORTS:
        _run_adb(["connect", port], timeout=4)
    return verified(list_devices())

# android_id 是 16 個十六進位字元，自成一行。用它辨識「這兩個連接埠是不是同一台」。
# 取不到時（回 null 或空）就不合併，寧可多列一筆，也不要把兩台真的模擬器併掉。
_ANDROID_ID_RE = re.compile(r'^[0-9a-f]{16}$')
# wm size 的正常輸出是 "Physical size: 1080x1920"，用這個樣式判斷裝置有沒有回應。
# 不能只檢查字串裡有沒有 "x" —— 同一次呼叫還會帶回 android_id，太容易誤判。
_WM_SIZE_RE = re.compile(r'[0-9]+x[0-9]+')


def _verify(devices):
    """驗證每個連線是否真的通，並把同一台模擬器的多個連接埠合併成一筆。

    **為什麼要驗證**：`adb devices` 的狀態是 adb 伺服器自己的記帳，不是即時探測 ——
    模擬器被關掉後，連線可能仍被列為 device。實際送一次指令才分得出來。

    **為什麼要合併**：模擬器常同時在多個埠上聽同一個實例。實測一台 MuMu 會同時出現在
    16384 / 5555 / 7555 三個埠，三者的 android_id 完全相同；而第二台 MuMu 在 16416，
    android_id 不同。不合併的話 UI 會顯示「偵測到 3 台」，但其實只有一台。

    兩件事共用同一次 shell 呼叫（wm size 與 android_id 一起取回），所以合併是免費的。

    只有兩筆以上才真的驗證：單筆時就算驗不過，結尾的 `alive or devices` 也會把它原封不動
    還回去，結果完全一樣，等於白等一次逾時。絕大多數使用者是單台模擬器，這條短路讓他們
    完全不必付這個成本，也保證單台永遠不會被誤判剔除。

    逾時維持 6 秒不縮短：這兩個指令雖然很輕，但模擬器正在跑動畫、滿載時未必來得及回應，
    縮短只會換來新的誤判。
    """
    if len(devices) <= 1:
        return devices

    alive = []
    seen = {}      # android_id -> 已經留下來的那個連接埠
    for d in devices:
        r = _run_adb(["-s", d, "shell", "wm size; settings get secure android_id"], timeout=6)
        # splitlines 同時處理 CRLF 與 LF，不必自己清換行字元
        lines = [ln.strip() for ln in (r.stdout or "").splitlines()]

        if not any(_WM_SIZE_RE.search(ln) for ln in lines):
            print(f"[偵測] {d} 無回應，已排除")
            continue

        aid = next((ln for ln in lines if _ANDROID_ID_RE.match(ln)), None)
        if aid is not None and aid in seen:
            print(f"[偵測] {d} 與 {seen[aid]} 是同一台模擬器的不同連接埠，已合併")
            continue
        if aid is not None:
            seen[aid] = d
        alive.append(d)

    return alive or devices   # 全部都不通的話還是回傳原清單，讓使用者自己試


class FGOBot:
    """負責與模擬器溝通的底層：截圖、點擊、影像比對。"""

    def __init__(self, device_id="127.0.0.1:5555", use_roi=True, use_raw_capture=True, use_tap=True):
        self.device_id = device_id
        self.use_roi = use_roi              # 是否啟用 ROI 加速
        self.use_tap = use_tap              # 點擊改用 input tap（較快）或 input swipe（較穩）
        self._roi_miss = {}                 # 各模板連續未命中次數
        self._roi_disabled = set()          # 已確認位置不符、自動停用 ROI 的模板
        self.base_dir = get_base_dir()
        self.sys_path = os.path.join(self.base_dir, "assets_system")
        self.friend_path = os.path.join(self.base_dir, "assets_friends")

        self.current_screen = None
        self.current_screen_gray = None

        # 用 OrderedDict 實作 LRU，滿了只踢掉最久沒用的一張，不再整批清空
        self.template_cache = OrderedDict()
        self._missing_warned = set()   # 已經警告過的缺圖，避免洗版

        # 座標系：截圖解析度 (raw) 與裝置觸控解析度 (tap)
        self.raw_w = CANVAS_W
        self.raw_h = CANVAS_H
        self.tap_w = CANVAS_W
        self.tap_h = CANVAS_H

        # 截圖模式：raw 最快 → png_exec → png_shell，失敗會自動往後退且不再回頭
        self._capture_mode = 'raw' if use_raw_capture else 'png_exec'
        self._raw_verified = not use_raw_capture   # 首次成功截圖後會做一次正確性驗證

        os.makedirs(self.sys_path, exist_ok=True)
        os.makedirs(os.path.join(self.friend_path, "servants"), exist_ok=True)
        os.makedirs(os.path.join(self.friend_path, "craft_essences"), exist_ok=True)

        self.init_device()

    # ==========================================
    # 🔌 ADB 底層
    # ==========================================
    def adb_shell(self, command, timeout=15):
        """執行 adb 指令。

        不使用 shell=True：少一層 cmd.exe、不會閃黑窗、也比較快。
        逾時會強制殺掉卡住的 adb 客戶端行程，避免 adb.exe 越積越多。
        """
        cmd = [ADB_EXE, "-s", self.device_id] + command.split()
        t0 = time.perf_counter() if ADB_PROFILE else None
        try:
            return subprocess.run(
                cmd, capture_output=True, timeout=timeout,
                creationflags=CREATE_NO_WINDOW
            )
        except subprocess.TimeoutExpired:
            print(f"⚠️ [ADB] 指令逾時已強制中斷: {command}")
        except FileNotFoundError:
            print("❌ [ADB] 找不到 adb 執行檔，請確認已加入系統 PATH")
        except Exception as e:
            print(f"⚠️ [ADB] 執行失敗: {e}")
        finally:
            if t0 is not None:
                ms = (time.perf_counter() - t0) * 1000
                # 依指令類型分類：input=點擊/滑動、screencap=截圖、其他
                head = command.split()
                kind = "other"
                if "input" in head:
                    kind = "input_tap" if "tap" in head else "input_swipe"
                elif "screencap" in head:
                    kind = "screencap_png" if "-p" in head else "screencap_raw"
                elif "wm" in head:
                    kind = "wm size"
                _record_adb_time(kind, ms)
        # 統一回傳一個「失敗但結構完整」的物件，呼叫端不用額外判 None
        return subprocess.CompletedProcess(cmd, 1, b'', b'')

    def init_device(self):
        """讀取裝置真實觸控解析度，防禦模擬器顯示與觸控不一致的問題。"""
        result = self.adb_shell("shell wm size", timeout=10)
        out = result.stdout.decode(errors='ignore')

        # 有 Override size 時要以它為準，input 事件吃的是覆寫後的解析度
        matches = re.findall(r'(\d+)x(\d+)', out)
        if matches:
            w, h = int(matches[-1][0]), int(matches[-1][1])
            if h > w:
                w, h = h, w   # 強制轉成橫向
            self.tap_w, self.tap_h = w, h
            print(f"[INIT] 觸控解析度: {self.tap_w}x{self.tap_h}")
        else:
            print(f"[INIT] 無法讀取解析度，沿用預設 {self.tap_w}x{self.tap_h}")

    def shutdown(self):
        """關閉 adb 伺服器（保留給既有呼叫端，實作在模組層級）"""
        kill_adb_server()

    # ==========================================
    # 📸 截圖
    # ==========================================
    def _decode_raw_screencap(self, data):
        """解析 `adb exec-out screencap` 的原始輸出。

        格式為：width(4) height(4) format(4) [colorSpace(4), Android 13+ 才有]
        之後接著 w*h*bpp 的像素資料。省掉裝置端的 PNG 壓縮與本機解壓，
        是這條路徑比 `screencap -p` 快的主因。
        """
        if data is None or len(data) < 16:
            return None
        try:
            w, h, fmt = struct.unpack('<III', data[:12])
        except Exception:
            return None
        if not (0 < w <= 10000 and 0 < h <= 10000):
            return None

        px = w * h
        # 標頭長度依 Android 版本而異，兩種都試
        for header in (12, 16):
            body = len(data) - header
            try:
                if fmt in (1, 2) and body == px * 4:        # RGBA_8888 / RGBX_8888
                    arr = np.frombuffer(data, dtype=np.uint8, count=px * 4, offset=header)
                    return cv2.cvtColor(arr.reshape(h, w, 4), cv2.COLOR_RGBA2BGR)
                if fmt == 3 and body == px * 3:             # RGB_888
                    arr = np.frombuffer(data, dtype=np.uint8, count=px * 3, offset=header)
                    return cv2.cvtColor(arr.reshape(h, w, 3), cv2.COLOR_RGB2BGR)
            except Exception:
                continue
        return None

    def _verify_raw_mode(self, raw_img):
        """驗證 raw 解析結果是否正確（只在第一次成功截圖後執行一次）。

        raw 最危險的失敗模式不是報錯，而是「解析成功但色彩通道順序錯誤」——
        程式不會發現，只會讓所有模板比對失敗，症狀是腳本什麼都不做。
        這裡立刻再抓一張 PNG 來對照，確認兩者一致才繼續使用 raw。
        """
        self._raw_verified = True
        print("🔬 [截圖] 正在驗證 raw 模式正確性...")

        result = self.adb_shell("exec-out screencap -p", timeout=15)
        if not result.stdout:
            print("⚠️ [截圖] 驗證用的 PNG 抓取失敗，暫且信任 raw 模式")
            return True

        png_img = cv2.imdecode(np.frombuffer(result.stdout, np.uint8), cv2.IMREAD_COLOR)
        if png_img is None or png_img.shape != raw_img.shape:
            print("⚠️ [截圖] 兩者尺寸不一致，停用 raw 模式")
            self._capture_mode = 'png_exec'
            return False

        # 縮小再比對：降低運算量，也讓畫面動畫造成的細微差異不致放大
        small = (480, 270)
        a = cv2.resize(raw_img, small).astype(np.int16)
        b = cv2.resize(png_img, small).astype(np.int16)

        d_normal = float(np.mean(np.abs(a - b)))
        d_swapped = float(np.mean(np.abs(a[:, :, ::-1] - b)))   # 通道順序顛倒的情況

        print(f"🔬 [截圖] 色差比對 → 正常順序 {d_normal:.1f} / 顛倒順序 {d_swapped:.1f}")

        if d_swapped < d_normal * 0.5:
            print("⚠️ [截圖] 偵測到色彩通道順序相反，已停用 raw 模式改用 PNG")
            print("   → 請將此訊息回報給開發者，以便支援你的模擬器")
            self._capture_mode = 'png_exec'
            return False

        # 兩張圖之間隔了幾百毫秒，動畫會造成一定差異，門檻放寬到 40
        if d_normal > 40:
            print(f"⚠️ [截圖] raw 與 PNG 差異過大 ({d_normal:.1f})，保守起見停用 raw 模式")
            self._capture_mode = 'png_exec'
            return False

        print("✅ [截圖] raw 模式驗證通過，將使用高速截圖")
        return True

    def capture_screen(self):
        """擷取畫面並正規化成 1920x1080 供邏輯判斷。"""
        raw_img = None

        # 1) raw：不做 PNG 壓縮，最快
        if self._capture_mode == 'raw':
            result = self.adb_shell("exec-out screencap", timeout=15)
            raw_img = self._decode_raw_screencap(result.stdout)
            if raw_img is None:
                print("⚠️ [截圖] raw 模式無法解析，改用 PNG 模式")
                self._capture_mode = 'png_exec'
            elif not self._raw_verified:
                # 第一次成功解析時做一次正確性驗證，不通過就永久退回 PNG
                if not self._verify_raw_mode(raw_img):
                    raw_img = None

        # 2) PNG over exec-out：binary 通道，不會有換行被轉譯的問題
        if raw_img is None and self._capture_mode == 'png_exec':
            result = self.adb_shell("exec-out screencap -p", timeout=15)
            if result.stdout:
                raw_img = cv2.imdecode(np.frombuffer(result.stdout, np.uint8), cv2.IMREAD_COLOR)
            if raw_img is None:
                print("⚠️ [截圖] exec-out 失敗，改用 shell screencap")
                self._capture_mode = 'png_shell'

        # 3) 舊式 shell：需手動修補被轉譯的換行（有些裝置是 \r\r\n）
        if raw_img is None and self._capture_mode == 'png_shell':
            result = self.adb_shell("shell screencap -p", timeout=15)
            if result.stdout:
                fixed = result.stdout.replace(b'\r\r\n', b'\n').replace(b'\r\n', b'\n')
                raw_img = cv2.imdecode(np.frombuffer(fixed, np.uint8), cv2.IMREAD_COLOR)

        if raw_img is None:
            self.current_screen = None
            self.current_screen_gray = None
            return False

        self.raw_h, self.raw_w = raw_img.shape[:2]

        if (self.raw_w, self.raw_h) != (CANVAS_W, CANVAS_H):
            interp = cv2.INTER_AREA if self.raw_w > CANVAS_W else cv2.INTER_LINEAR
            self.current_screen = cv2.resize(raw_img, (CANVAS_W, CANVAS_H), interpolation=interp)
        else:
            self.current_screen = raw_img

        self.current_screen_gray = cv2.cvtColor(self.current_screen, cv2.COLOR_BGR2GRAY)
        return True

    # ==========================================
    # 👆 座標轉譯與操作
    # ==========================================
    def _to_tap(self, x, y):
        """把 1920x1080 基準座標換算成裝置實際觸控座標。"""
        tx = round(x / float(CANVAS_W) * self.tap_w)
        ty = round(y / float(CANVAS_H) * self.tap_h)
        # 夾在畫面範圍內，避免傳出無效座標
        tx = max(0, min(self.tap_w - 1, tx))
        ty = max(0, min(self.tap_h - 1, ty))
        return tx, ty

    def smart_click(self, x, y, duration=150):
        tx, ty = self._to_tap(x, y)

        # input tap 不需要等待按壓時間，比 swipe 快 50~150ms。
        # 但按壓極短，若遊戲偶爾收不到，把 coords.USE_TAP 改回 False 即可。
        # 真正需要長按的情況（duration 夠大）一律走 swipe。
        if self.use_tap and duration < LONG_PRESS_MS:
            self.adb_shell(f"shell input tap {tx} {ty}", timeout=5)
        else:
            self.adb_shell(f"shell input swipe {tx} {ty} {tx} {ty} {duration}", timeout=5)

    def smart_swipe(self, x1, y1, x2, y2, duration=400):
        tx1, ty1 = self._to_tap(x1, y1)
        tx2, ty2 = self._to_tap(x2, y2)
        self.adb_shell(f"shell input swipe {tx1} {ty1} {tx2} {ty2} {duration}", timeout=10)

    # ==========================================
    # 🔍 影像比對
    # ==========================================
    def _get_template_gray(self, full_path):
        """讀取模板灰階圖，附 LRU 快取（支援中文路徑）。"""
        if full_path in self.template_cache:
            self.template_cache.move_to_end(full_path)   # 標記為最近使用
            return self.template_cache[full_path]

        try:
            template_color = cv2.imdecode(
                np.fromfile(full_path, dtype=np.uint8), cv2.IMREAD_COLOR
            )
        except Exception as e:
            print(f"⚠️ [影像] 讀取失敗: {full_path} ({e})")
            return None

        if template_color is None:
            return None

        gray = cv2.cvtColor(template_color, cv2.COLOR_BGR2GRAY)
        self.template_cache[full_path] = gray
        if len(self.template_cache) > TEMPLATE_CACHE_SIZE:
            self.template_cache.popitem(last=False)   # 只踢掉最久沒用的一張
        return gray

    def find_in_folder(self, folder_type, filename, threshold=0.8, click_it=False):
        """在 assets 資料夾裡找圖。

        🚀 click_it 預設為 False：這個 API 同時能「找」和「點」，
           預設不點比較安全 —— 忘記寫參數時只是少點一下（看得出來），
           而不是多點一下（不會報錯，但會誤觸畫面）。
           要點擊請明確寫 click_it=True。
        """
        if not filename:
            return False
        base_dir = self.sys_path if folder_type == 'system' else self.friend_path
        full_path = os.path.join(base_dir, filename)

        if not os.path.exists(full_path):
            # 缺圖只警告一次，避免每輪迴圈洗版
            if full_path not in self._missing_warned:
                self._missing_warned.add(full_path)
                print(f"⚠️ [素材] 找不到圖片，此判斷將永遠失敗: {filename}")
            return False

        return self.find_by_abspath(full_path, threshold, click_it)

    def _match(self, template_gray, region=None):
        """在指定範圍內做模板比對，回傳 (左上角座標, 相似度)。

        region=None 代表搜尋整個畫面。回傳的座標已換算回全畫面基準。
        """
        img = self.current_screen_gray
        ox = oy = 0

        if region:
            x1, y1, x2, y2 = region
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
            sub = img[y1:y2, x1:x2]
            if sub.shape[0] < template_gray.shape[0] or sub.shape[1] < template_gray.shape[1]:
                return None, -1.0
            img, ox, oy = sub, x1, y1

        res = cv2.matchTemplate(img, template_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        return (max_loc[0] + ox, max_loc[1] + oy), max_val

    def _record_roi_hit(self, filename, loc, size, score):
        """開發用：把命中位置寫入 roi_log.csv，供之後產生 ROI 表"""
        try:
            path = os.path.join(self.base_dir, "roi_log.csv")
            new = not os.path.exists(path)
            with open(path, "a", encoding="utf-8") as f:
                if new:
                    f.write("filename,x,y,w,h,score\n")
                f.write(f"{filename},{loc[0]},{loc[1]},{size[1]},{size[0]},{score:.3f}\n")
        except Exception as e:
            print(f"⚠️ [ROI] 寫入紀錄失敗: {e}")

    def find_by_abspath(self, full_path, threshold=0.8, click_it=False):
        """回傳中心點座標 (x, y)，找不到回傳 None。要點擊請明確寫 click_it=True。"""
        if self.current_screen_gray is None:
            return None
        template_gray = self._get_template_gray(full_path)
        if template_gray is None:
            return None

        th, tw = template_gray.shape[:2]
        sh, sw = self.current_screen_gray.shape[:2]
        if th > sh or tw > sw:
            print(f"⚠️ [影像] 模板比畫面還大，已跳過: {os.path.basename(full_path)}")
            return None

        filename = os.path.basename(full_path)

        region = None
        if self.use_roi and filename not in self._roi_disabled:
            region = TEMPLATE_ROI.get(filename)

        loc, max_val = self._match(template_gray, region)

        # ROI 內沒找到時，每累積 N 次才做一次全畫面複查。
        # 這樣既能偵測改版造成的位置變動，又不會讓每次未命中都退回全畫面掃描。
        if region and max_val < threshold:
            self._roi_miss[filename] = self._roi_miss.get(filename, 0) + 1
            if self._roi_miss[filename] >= ROI_VERIFY_EVERY:
                self._roi_miss[filename] = 0
                full_loc, full_val = self._match(template_gray, None)
                if full_val >= threshold:
                    print(f"⚠️ [ROI] {filename} 不在設定範圍內，卻於全畫面 "
                          f"({full_loc[0]}, {full_loc[1]}) 找到（相似度 {full_val:.3f}）。")
                    print(f"   → 遊戲介面位置可能已變動，已自動停用此圖的 ROI 並改用全畫面。")
                    print(f"   → 請更新 coords.py 的 TEMPLATE_ROI['{filename}']。")
                    self._roi_disabled.add(filename)
                    loc, max_val = full_loc, full_val
        elif region:
            self._roi_miss[filename] = 0   # 命中就重置計數

        if DEBUG and filename in DEBUG_TEMPLATES:
            scope = "ROI" if region else "全畫面"
            print(f"🔍 掃描 [{filename}] 相似度: {max_val:.3f} (門檻: {threshold}, 範圍: {scope})")

        if max_val >= threshold and loc is not None:
            cx = loc[0] + tw // 2
            cy = loc[1] + th // 2
            if ROI_RECORD:
                self._record_roi_hit(filename, loc, (th, tw), max_val)
            if click_it:
                self.smart_click(cx, cy)
            return (cx, cy)
        return None

    def find_all_by_abspath(self, full_path, threshold=0.8, max_results=50):
        """找出畫面上所有符合的位置（助戰 3x3 陣列會用到）。"""
        if self.current_screen_gray is None:
            return []
        template_gray = self._get_template_gray(full_path)
        if template_gray is None:
            return []

        th, tw = template_gray.shape[:2]
        sh, sw = self.current_screen_gray.shape[:2]
        if th > sh or tw > sw:
            return []

        res = cv2.matchTemplate(self.current_screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(res >= threshold)
        if len(xs) == 0:
            return []

        # 先按分數由高到低排序，再做去重，確保留下的是每一群裡最準的那一點
        scores = res[ys, xs]
        order = np.argsort(-scores)[:2000]   # 限制候選數量，避免低門檻時爆量

        points = []
        for i in order:
            cx = int(xs[i]) + tw // 2
            cy = int(ys[i]) + th // 2
            if any(abs(cx - px) < tw // 2 and abs(cy - py) < th // 2 for px, py in points):
                continue
            points.append((cx, cy))
            if len(points) >= max_results:
                break
        return points