"""
腳本乾跑檢查
============
不開遊戲、不碰畫面，純粹用邏輯檢查 3T 腳本設定是否合理。

設計原則：零設定成本。使用者不需要填任何資料（例如各技能的冷卻回合數），
打開就有效。代價是某些判斷只能給警告而無法斷定，這是刻意的取捨 ——
一個需要先填九個欄位才能用的檢查器，對新手是淨損失。

嚴重度分三級：
  error  🔴 結構上不可能成立，執行必定出錯
  warn   🟡 多數情況是錯的，但存在合理的例外
  info   🔵 純提醒，提示容易忽略的副作用

重要前提：一個 Wave 的指令 = 一個回合的操作
（execute_script_from_list 跑完所有指令 → 選卡 → 攻擊）。
"""

import re

ERROR = "error"
WARN = "warn"
INFO = "info"

LEVEL_ICON = {ERROR: "🔴", WARN: "🟡", INFO: "🔵"}
LEVEL_NAME = {ERROR: "錯誤", WARN: "警告", INFO: "提醒"}

# 場上位置與技能編號的對應：位置 1 → 技能 1~3、位置 2 → 4~6、位置 3 → 7~9
SKILLS_PER_SERVANT = 3
MAX_SERVANTS = 3
MAX_SKILLS = SKILLS_PER_SERVANT * MAX_SERVANTS      # 9
MAX_MASTER_SKILLS = 3
MAX_TARGETS = 3
MAX_ENEMIES = 3      # 註：少數關卡有 4~6 隻敵人，目前介面只支援 1~3

# 換人技能冷卻約 15 回合，3T 內不可能用第二次
MAX_ORDER_CHANGES = 1


def servant_of_skill(skill_idx):
    """技能編號 → 該技能屬於第幾個場上位置"""
    return (skill_idx - 1) // SKILLS_PER_SERVANT + 1


def skills_of_servant(pos):
    """場上位置 → 該位置的三個技能編號"""
    start = (pos - 1) * SKILLS_PER_SERVANT + 1
    return list(range(start, start + SKILLS_PER_SERVANT))


def parse_command(c):
    """把指令碼拆成結構化資料，無法解析回傳 None"""
    m = re.match(r'^S(\d+)(_star|_nostar)?(?:-(\d+))?$', c)
    if m:
        return {"type": "skill", "idx": int(m.group(1)),
                "modifier": m.group(2), "target": int(m.group(3)) if m.group(3) else None}

    m = re.match(r'^M(\d+)(?:-(\d+))?$', c)
    if m:
        return {"type": "master", "idx": int(m.group(1)),
                "target": int(m.group(2)) if m.group(2) else None}

    m = re.match(r'^N(\d+)$', c)
    if m:
        return {"type": "np", "idx": int(m.group(1))}

    m = re.match(r'^E(\d+)$', c)
    if m:
        return {"type": "enemy", "idx": int(m.group(1))}

    m = re.match(r'^O-(\d+)-(\d+)$', c)
    if m:
        return {"type": "order", "front": int(m.group(1)), "back": int(m.group(2))}

    return None


def check_script(script_data):
    """檢查整份腳本。

    回傳問題清單，每筆為
      {"wave": 波次(0起), "index": 該波第幾道指令(0起, None 表示整波), 
       "level": 嚴重度, "msg": 說明}
    """
    issues = []

    def add(wave, index, level, msg):
        issues.append({"wave": wave, "index": index, "level": level, "msg": msg})

    skill_history = {}          # 技能編號 -> 上次使用的波次
    order_changes = []          # [(wave, index, front, back)]
    used_back = {}              # 後排位置 -> 換上場的波次
    swapped_front = {}          # 場上位置 -> 被換人的 (wave, index)

    for w, cmds in enumerate(script_data[:3]):
        skills_this_wave = {}   # 技能編號 -> 該波第幾道
        nps_this_wave = {}      # 從者編號 -> 該波第幾道
        attack_opened_at = None # 第一道寶具指令的位置

        # 指令類型 -> 顯示名稱，用於錯誤訊息
        type_name = {"skill": "從者技能", "master": "御主技能",
                     "enemy": "切換敵人", "order": "換人"}

        for i, c in enumerate(cmds):
            p = parse_command(c)

            if p is None:
                add(w, i, ERROR, f"無法解析的指令「{c}」，可能是手動編輯設定檔時打錯")
                continue

            # 🚀 第一道寶具指令會按下 Attack 進入選卡畫面，
            #    此後技能欄與敵人列都不存在，任何非寶具指令都無法執行。
            if attack_opened_at is not None and p["type"] != "np":
                add(w, i, ERROR,
                    f"{type_name.get(p['type'], '此')}指令排在寶具之後。"
                    f"第 {attack_opened_at + 1} 道寶具已進入選卡畫面，"
                    f"之後無法再操作技能或敵人，請把它移到寶具前面")
                continue

            # ---------- 從者技能 ----------
            if p["type"] == "skill":
                idx = p["idx"]
                if not (1 <= idx <= MAX_SKILLS):
                    add(w, i, ERROR, f"技能編號 {idx} 超出範圍（可用 1~{MAX_SKILLS}）")
                    continue
                if p["target"] is not None and not (1 <= p["target"] <= MAX_TARGETS):
                    add(w, i, ERROR, f"對象編號 {p['target']} 超出範圍（可用 1~{MAX_TARGETS}）")

                # 🚀 技能重複使用只列為「提醒」而非警告。
                #    許多隊伍會刻意用降低冷卻的技能讓同一個技能再放一次，
                #    若列為警告，正常配置也會滿江黃燈，反而讓人忽略真正的問題。
                if idx in skills_this_wave:
                    add(w, i, INFO,
                        f"技能 {idx} 在本波第 {skills_this_wave[idx] + 1} 道已使用過，"
                        f"需要中間有降低冷卻的效果才會生效")
                elif idx in skill_history:
                    add(w, i, INFO,
                        f"技能 {idx} 在 Wave{skill_history[idx] + 1} 使用過，"
                        f"需要冷卻已轉回或有降低冷卻的效果")
                skills_this_wave[idx] = i
                skill_history[idx] = w

            # ---------- 御主技能 ----------
            elif p["type"] == "master":
                if not (1 <= p["idx"] <= MAX_MASTER_SKILLS):
                    add(w, i, ERROR, f"御主技能編號 {p['idx']} 超出範圍（可用 1~{MAX_MASTER_SKILLS}）")
                if p["target"] is not None and not (1 <= p["target"] <= MAX_TARGETS):
                    add(w, i, ERROR, f"對象編號 {p['target']} 超出範圍（可用 1~{MAX_TARGETS}）")

            # ---------- 寶具 ----------
            elif p["type"] == "np":
                idx = p["idx"]
                if not (1 <= idx <= MAX_SERVANTS):
                    add(w, i, ERROR, f"寶具編號 {idx} 超出範圍（可用 1~{MAX_SERVANTS}）")
                    continue
                if idx in nps_this_wave:
                    add(w, i, ERROR,
                        f"從者 {idx} 的寶具在本波第 {nps_this_wave[idx] + 1} 道已選取，"
                        f"再點一次會取消選取")
                nps_this_wave[idx] = i
                if attack_opened_at is None:
                    attack_opened_at = i

            # ---------- 切換敵人 ----------
            elif p["type"] == "enemy":
                if not (1 <= p["idx"] <= MAX_ENEMIES):
                    add(w, i, ERROR, f"敵方編號 {p['idx']} 超出範圍（可用 1~{MAX_ENEMIES}）")

            # ---------- 換人 ----------
            elif p["type"] == "order":
                f, b = p["front"], p["back"]
                bad = False
                if not (1 <= f <= MAX_SERVANTS):
                    add(w, i, ERROR, f"場上位置 {f} 超出範圍（可用 1~{MAX_SERVANTS}）"); bad = True
                if not (1 <= b <= MAX_SERVANTS):
                    add(w, i, ERROR, f"後備位置 {b} 超出範圍（可用 1~{MAX_SERVANTS}）"); bad = True
                if bad:
                    continue

                order_changes.append((w, i, f, b))
                if len(order_changes) > MAX_ORDER_CHANGES:
                    fw, fi, _, _ = order_changes[0]
                    add(w, i, ERROR,
                        f"換人已在 Wave{fw + 1} 使用過，換人技能冷卻約 15 回合，"
                        f"3T 內無法使用第二次")

                if b in used_back:
                    add(w, i, WARN,
                        f"後備位置 {b} 已於 Wave{used_back[b] + 1} 換上場，"
                        f"該位置現在站的是先前換下場的角色")
                used_back[b] = w
                swapped_front[f] = (w, i)

                # 🚀 換上場的是全新角色，技能冷卻是全新的 ——
                #    清掉該位置三個技能的使用紀錄，否則之後每次使用都會被誤報。
                for s in skills_of_servant(f):
                    skill_history.pop(s, None)
                    skills_this_wave.pop(s, None)

                add(w, i, INFO,
                    f"換人後位置 {f} 為新角色，技能 "
                    f"{'、'.join(str(s) for s in skills_of_servant(f))} 的冷卻將重新計算")

    if not any(script_data[:3]):
        issues.append({"wave": None, "index": None, "level": INFO,
                       "msg": "三個 Wave 都沒有指令，戰鬥時將直接選卡攻擊"})

    return issues


def summarize(issues):
    """把問題清單濃縮成一行摘要"""
    if not issues:
        return "✅ 檢查通過，未發現問題"
    n = {lv: sum(1 for x in issues if x["level"] == lv) for lv in (ERROR, WARN, INFO)}
    parts = [f"{LEVEL_ICON[lv]} {n[lv]} 個{LEVEL_NAME[lv]}" for lv in (ERROR, WARN, INFO) if n[lv]]
    return "　".join(parts)


def has_error(issues):
    return any(x["level"] == ERROR for x in issues)


def format_report(issues):
    """輸出多行文字報告，供彈窗或主控台顯示"""
    if not issues:
        return "檢查通過，未發現問題。"
    lines = []
    for x in issues:
        where = "整體" if x["wave"] is None else f"Wave{x['wave'] + 1}"
        if x["index"] is not None:
            where += f" 第 {x['index'] + 1} 道"
        lines.append(f"{LEVEL_ICON[x['level']]} {where}：{x['msg']}")
    return "\n".join(lines)