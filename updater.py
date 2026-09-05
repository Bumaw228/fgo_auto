"""
GitHub Release 自動更新模組
===========================
功能分三段：
  1. check_for_update_async()  — 背景查詢是否有新版
  2. download_asset()          — 下載新版壓縮檔（含進度回報）
  3. apply_update()            — 解壓、產生批次檔、關閉主程式並自動覆蓋重啟

只用標準庫，不需額外安裝任何套件。
"""

import os
import sys
import json
import shutil
import zipfile
import tempfile
import threading
import subprocess
import urllib.request
import urllib.error

# ==========================================
# 🔧 設定區：發新版前務必檢查這三個值
# ==========================================
GITHUB_OWNER = "Bumaw228"
GITHUB_REPO = "fgo_auto"

# 🚀 每次發版都要改這裡，並讓 GitHub 上的 tag 一致（tag 打 v1.0.1，這裡寫 1.0.1）
CURRENT_VERSION = "0.9.2"

API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

CREATE_NEW_CONSOLE = 0x00000010

# ==========================================
# 🛡️ 更新時要保護的使用者資料
# ==========================================
# 這些目錄／檔案屬於使用者自己的東西，更新時一律不覆蓋。
# 新使用者直接下載 zip 時仍會拿到完整內容，只有「就地更新」才會跳過。
PROTECTED_DIRS = ["assets_saves", "assets_friends"]
PROTECTED_FILES = ["config.json"]


def get_base_dir():
    """程式所在目錄。打包後是 exe 那一層，也就是要被更新覆蓋的目標。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def is_frozen():
    """是否為打包後的 exe。用原始碼跑的時候不允許自動更新。"""
    return getattr(sys, 'frozen', False)


# ==========================================
# 1️⃣ 版本查詢
# ==========================================
def parse_version(v):
    """把 'v1.2.3' / '1.2.3-beta' 轉成 (1, 2, 3) 方便比大小。"""
    if not v:
        return (0, 0, 0)
    v = str(v).strip().lstrip("vV")
    parts = []
    for chunk in v.split(".")[:4]:
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def fetch_latest_release(timeout=10):
    """查詢最新 Release。失敗直接拋例外，由呼叫端決定怎麼處理。"""
    req = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{GITHUB_REPO}-updater",   # GitHub 沒帶這個會回 403
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)

    assets = [
        {"name": a.get("name", ""),
         "url": a.get("browser_download_url", ""),
         "size": a.get("size", 0)}
        for a in data.get("assets", [])
    ]
    # 只取 zip，並挑最大的那個（通常就是完整程式包）
    zips = [a for a in assets if a["name"].lower().endswith(".zip")]
    zips.sort(key=lambda a: a["size"], reverse=True)

    return {
        "version": data.get("tag_name", ""),
        "notes": (data.get("body") or "").strip(),
        "page": data.get("html_url", ""),
        "zip": zips[0] if zips else None,
    }


def check_for_update_async(on_update_available, on_error=None):
    """背景檢查更新。

    ⚠️ callback 是在子執行緒被呼叫的，裡面要動 UI 請用 root.after(0, ...)。
    """
    def worker():
        try:
            info = fetch_latest_release()
            if parse_version(info["version"]) > parse_version(CURRENT_VERSION):
                on_update_available(info)
        except urllib.error.HTTPError as e:
            # 404 通常代表這個 repo 還沒發過 Release，屬正常情況
            if on_error:
                on_error(f"HTTP {e.code}")
        except Exception as e:
            # 沒網路、防火牆、GitHub 掛掉都不該影響主程式
            if on_error:
                on_error(str(e))

    threading.Thread(target=worker, daemon=True).start()


# ==========================================
# 2️⃣ 下載
# ==========================================
def download_asset(url, dest_path, progress_cb=None, timeout=30):
    """下載檔案，每收到一塊就回報進度百分比。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": f"{GITHUB_REPO}-updater",
        "Accept": "application/octet-stream",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress_cb and total:
                    progress_cb(done * 100 // total)
    return dest_path


# ==========================================
# 3️⃣ 安裝
# ==========================================
def _find_payload_root(extract_dir, exe_name):
    """找出解壓後真正的程式根目錄。

    壓縮檔通常會多包一層資料夾（例如 FGOAutoGPT/），這裡自動往下找到有 exe 的那層。
    """
    if os.path.exists(os.path.join(extract_dir, exe_name)):
        return extract_dir

    for root, dirs, files in os.walk(extract_dir):
        if exe_name in files:
            return root

    # 找不到 exe，退而求其次：如果只有一個子資料夾就用它
    entries = [os.path.join(extract_dir, d) for d in os.listdir(extract_dir)]
    subdirs = [d for d in entries if os.path.isdir(d)]
    if len(subdirs) == 1:
        return subdirs[0]
    return extract_dir


# 批次檔內容：等主程式關閉 → 覆蓋檔案 → 重新啟動 → 自我清理
_UPDATE_BAT = r"""@echo off
chcp 65001 > nul
title 正在更新 {repo}
echo.
echo   正在更新，請勿關閉此視窗...
echo.

:waitloop
tasklist /FI "IMAGENAME eq {exe}" 2>nul | find /I "{exe}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto waitloop
)

echo   正在複製新版檔案...
echo   (使用者的存檔與助戰圖片將保留不動)
robocopy "{src}" "{dst}" /E /IS {excludes} /NFL /NDL /NJH /NJS /R:3 /W:2
if errorlevel 8 (
    echo.
    echo   [失敗] 檔案複製發生錯誤，可能是權限不足。
    echo   請手動到 GitHub 下載新版，或以系統管理員身分重試。
    echo.
    pause
    goto cleanup
)

echo   更新完成，正在重新啟動...
start "" "{dst}\{exe}"

:cleanup
rmdir /S /Q "{tmp}" 2>nul
del "%~f0"
"""


def apply_update(zip_path, on_error=None):
    """解壓新版並啟動更新批次檔。成功回傳 True，此時呼叫端應立即關閉程式。

    覆蓋採用 robocopy 且不加 /PURGE，所以使用者自己的存檔、助戰圖片、
    config.json 都不會被刪除，只有同名檔案會被新版覆蓋。
    """
    if not is_frozen():
        if on_error:
            on_error("以原始碼執行時不支援自動更新，請直接 git pull")
        return False

    install_dir = get_base_dir()
    exe_name = os.path.basename(sys.executable)

    try:
        tmp_dir = tempfile.mkdtemp(prefix="fgo_update_")
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp_dir)

        src_dir = _find_payload_root(tmp_dir, exe_name)

        # 基本健檢：新版包裡至少要看得到 exe，避免壓縮檔內容不對就亂覆蓋
        if not os.path.exists(os.path.join(src_dir, exe_name)):
            shutil.rmtree(tmp_dir, ignore_errors=True)
            if on_error:
                on_error(f"更新包內找不到 {exe_name}，已取消更新")
            return False

        # /XD 排除目錄、/XF 排除檔案，讓使用者資料完全不被更新碰到
        excludes = ""
        if PROTECTED_DIRS:
            excludes += " /XD " + " ".join(f'"{d}"' for d in PROTECTED_DIRS)
        if PROTECTED_FILES:
            excludes += " /XF " + " ".join(f'"{f}"' for f in PROTECTED_FILES)

        bat_path = os.path.join(tempfile.gettempdir(), "fgo_apply_update.bat")
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(_UPDATE_BAT.format(
                repo=GITHUB_REPO, exe=exe_name,
                src=src_dir, dst=install_dir, tmp=tmp_dir,
                excludes=excludes.strip(),
            ))

        # 開新視窗執行，讓使用者看得到進度；主程式接著自己關閉
        subprocess.Popen([bat_path], creationflags=CREATE_NEW_CONSOLE, close_fds=True)
        return True

    except Exception as e:
        if on_error:
            on_error(f"套用更新失敗: {e}")
        return False


def download_and_apply_async(info, on_progress=None, on_ready=None, on_error=None):
    """一條龍：下載 → 解壓 → 啟動更新批次檔。

    on_ready 被呼叫時代表批次檔已啟動，呼叫端要「立刻關閉主程式」，
    否則批次檔會一直卡在等待迴圈。
    """
    def worker():
        try:
            asset = info.get("zip")
            if not asset or not asset["url"]:
                if on_error:
                    on_error("這個版本沒有附上 zip 檔，請手動下載")
                return

            tmp_zip = os.path.join(tempfile.gettempdir(), asset["name"])
            download_asset(asset["url"], tmp_zip, progress_cb=on_progress)

            if apply_update(tmp_zip, on_error=on_error) and on_ready:
                on_ready()
        except Exception as e:
            if on_error:
                on_error(str(e))

    threading.Thread(target=worker, daemon=True).start()


# ==========================================
# 直接執行此檔可測試 API 是否正常
# ==========================================
if __name__ == "__main__":
    print(f"本機版本: {CURRENT_VERSION}")
    try:
        info = fetch_latest_release()
        print(f"線上版本: {info['version']}")
        print(f"下載頁面: {info['page']}")
        if info["zip"]:
            print(f"更新包  : {info['zip']['name']} ({info['zip']['size'] / 1024 / 1024:.1f} MB)")
        else:
            print("更新包  : 無（這個 Release 沒有附 zip）")
        need = parse_version(info["version"]) > parse_version(CURRENT_VERSION)
        print("→ 需要更新" if need else "→ 已是最新版")
    except Exception as e:
        print(f"查詢失敗: {e}")