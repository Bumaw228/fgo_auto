"""
打包腳本
========
把「跑 pyinstaller → 複製資源 → 清掉個人資料 → 壓縮」這串手動步驟收成一個指令。

手動複製最大的風險不是麻煩，而是**漏掉不會報錯**：
  少了 adb.exe   → 使用者機器上沒裝 adb 就完全不能用，但程式照樣啟動
  少了 assets_system → 所有畫面判斷永遠失敗，症狀是「腳本什麼都不做」
兩者都不會在打包當下給任何提示。所以這裡每一步都驗證，缺東西就中止。

用法：
    python build.py             完整打包並壓縮
    python build.py --no-zip    只產生 dist/FGOAuto 資料夾，不壓縮
"""

import os
import shutil
import subprocess
import sys
import zipfile

# Windows 主控台預設是 cp950，直接印中文會拋 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
APP = "FGOAuto"
DIST = os.path.join(ROOT, "dist", APP)

# 唯讀資源：整個複製過去
ASSET_DIRS = ["assets_system", "assets_ui"]

# 使用者資料夾：只建立空的結構。
# 不複製開發機上的內容 —— 那是自己的存檔與助戰圖，不該發布出去。
EMPTY_DIRS = [
    "assets_saves",
    os.path.join("assets_friends", "servants"),
    os.path.join("assets_friends", "craft_essences"),
]

# adb 三件套，缺一不可（少了 DLL，adb.exe 無法啟動）
ADB_FILES = ["adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll"]

# 打包完必須確定不存在的個人資料
JUNK_FILES = ["config.json", "roi_log.csv"]
JUNK_DIRS = ["logs", "cd_debug"]

# 發布前這五個診斷開關都必須是 False
SWITCHES = [
    ("fgo_core.py", "DEBUG"),
    ("fgo_core.py", "ROI_RECORD"),
    ("fgo_core.py", "ADB_PROFILE"),
    ("fgo_vision.py", "CD_DEBUG"),
    ("coords.py", "ORDER_DEBUG"),
]


def fail(msg):
    print("[X] " + msg)
    sys.exit(1)


def step(msg):
    print()
    print("=" * 58)
    print("  " + msg)
    print("=" * 58)


def read_lines(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read().splitlines()


def get_version():
    """從 updater.py 讀版號。用文字解析而不是 import，避免拉進整包相依。"""
    for line in read_lines("updater.py"):
        if line.startswith("CURRENT_VERSION"):
            return line.split('"')[1]
    fail("updater.py 裡找不到 CURRENT_VERSION")


def check_switches():
    """五個診斷開關忘記關掉，發出去會拖慢所有使用者且狂寫檔案。"""
    for fname, name in SWITCHES:
        prefix = name + " = "
        found = False
        for line in read_lines(fname):
            if line.startswith(prefix):
                value = line.split("=", 1)[1].split("#")[0].strip()
                if value != "False":
                    fail(f"{fname} 的 {name} 是 {value}，發布前必須改成 False")
                found = True
                break
        if not found:
            fail(f"{fname} 裡找不到 {name}，請確認開關名稱是否改過")
    print("[OK] 五個診斷開關都是 False")


def check_sources():
    """複製之前先確認來源都在，不要打包到一半才發現缺東西。"""
    missing = []
    for d in ASSET_DIRS:
        if not os.path.isdir(os.path.join(ROOT, d)):
            missing.append(d + "/")
    for f in ADB_FILES:
        if not os.path.exists(os.path.join(ROOT, f)):
            missing.append(f)
    if missing:
        fail("專案目錄缺少這些必要項目: " + ", ".join(missing))
    print("[OK] 資源與 adb 三件套都在")


def run_pyinstaller():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir", "--noconfirm",
        "--name", APP,
        "--collect-all", "customtkinter",
        "--noconsole",
        "--icon", os.path.join("assets_ui", "app_icon.ico"),
        "main_ui.py",
    ]
    print("  " + " ".join(cmd))
    print()
    if subprocess.run(cmd, cwd=ROOT).returncode != 0:
        fail("PyInstaller 失敗，請看上方訊息")


def copy_payload():
    for d in ASSET_DIRS:
        dst = os.path.join(DIST, d)
        shutil.copytree(os.path.join(ROOT, d), dst, dirs_exist_ok=True)
        n = sum(len(fs) for _, _, fs in os.walk(dst))
        print(f"  複製 {d}/  ({n} 個檔案)")

    for d in EMPTY_DIRS:
        os.makedirs(os.path.join(DIST, d), exist_ok=True)
        print(f"  建立空目錄 {d}/")

    for f in ADB_FILES:
        shutil.copy2(os.path.join(ROOT, f), os.path.join(DIST, f))
        print(f"  複製 {f}")


def clean_personal():
    for f in JUNK_FILES:
        p = os.path.join(DIST, f)
        if os.path.exists(p):
            os.remove(p)
            print(f"  移除 {f}")
    for d in JUNK_DIRS:
        p = os.path.join(DIST, d)
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
            print(f"  移除 {d}/")

    # 個人存檔是最容易誤發的東西：資料夾要在，內容必須是空的
    saves = os.path.join(DIST, "assets_saves")
    leftover = [f for f in os.listdir(saves)] if os.path.isdir(saves) else []
    if leftover:
        fail("assets_saves 裡還有檔案: " + ", ".join(leftover))
    print("  [OK] assets_saves 是空的，沒有夾帶個人存檔")


def verify():
    """最後一道關卡：確認產出真的能用。"""
    required = [APP + ".exe", "_internal"] + ADB_FILES + ASSET_DIRS
    missing = [r for r in required if not os.path.exists(os.path.join(DIST, r))]
    if missing:
        fail("產出缺少: " + ", ".join(missing))

    # assets_system 是所有畫面判斷的依據，空的等於整個程式失效
    n = len(os.listdir(os.path.join(DIST, "assets_system")))
    if n < 10:
        fail(f"assets_system 只有 {n} 個檔案，看起來不對")

    total = sum(os.path.getsize(os.path.join(r, f))
                for r, _, fs in os.walk(DIST) for f in fs)
    print(f"  [OK] 檔案齊全，assets_system {n} 張圖，總大小 {total / 1024 / 1024:.1f} MB")


def make_zip(version):
    name = f"{APP}-v{version}.zip"
    path = os.path.join(ROOT, "dist", name)
    if os.path.exists(path):
        os.remove(path)
    base = os.path.dirname(DIST)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(DIST):
            # 空目錄也要寫進去，否則使用者解壓後沒有 assets_saves 可放檔案
            for d in dirs:
                full = os.path.join(root, d)
                if not os.listdir(full):
                    z.write(full, os.path.relpath(full, base) + "/")
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, base))
    print(f"  {name}  ({os.path.getsize(path) / 1024 / 1024:.1f} MB)")
    return path


def main():
    version = get_version()
    step(f"打包 {APP} v{version}")

    check_switches()
    check_sources()

    step("清除舊的建置產物")
    for d in (os.path.join(ROOT, "build"), DIST):
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            print(f"  移除 {os.path.relpath(d, ROOT)}/")

    step("執行 PyInstaller")
    run_pyinstaller()

    step("複製資源")
    copy_payload()

    step("清除個人資料")
    clean_personal()

    step("驗證產出")
    verify()

    if "--no-zip" in sys.argv:
        print()
        print(f"完成（未壓縮）: {os.path.relpath(DIST, ROOT)}")
        return

    step("壓縮")
    path = make_zip(version)

    print()
    print("=" * 58)
    print(f"  完成！{os.path.relpath(path, ROOT)}")
    print("=" * 58)
    print()
    print("  發布前請先實際開啟 exe 確認：")
    print(f"    1. 版本顯示 v{version}")
    print("    2. log 開頭印「使用內建 ADB」而不是「改用系統 PATH」")
    print("    3. 自動偵測與截圖測試都正常")
    print()


if __name__ == "__main__":
    main()
