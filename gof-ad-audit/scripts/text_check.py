#!/usr/bin/env python3
"""无尽冬日国内买量素材的文字初筛：字幕、口播稿、脚本、文案、标题。

只抓字面，漏判误报都会有，结论要人对着 references/standard.md 再看一遍。
规则编号和 standard.md 一致，改标准时这里一起改。

用法：
  text_check.py 脚本.txt 字幕.srt ...      # 支持 txt/md/srt/ass/vtt/csv
  cat 文案.txt | text_check.py -           # 从 stdin 读
  text_check.py --json 字幕.srt            # 机器读的输出
"""
import argparse
import json
import re
import sys
from pathlib import Path

LEVELS = ["红线", "必改", "提醒"]
TIP = "广告创意仅供参考，广告素材宣传内容须达到一定关卡或触发相应模块后出现，实际以游戏内容为准"

# (编号, 级别, 正则, 说明)。正则命中即报，排除写在正则里。
RULES = [
    # A 红线
    ("A1", "红线", r"蔡徐坤|菜坤|坤坤|鸡你太美|只因你太美", "明星网红热梗"),
    ("A1", "提醒", r"抖音同款|热门BGM|网红|明星同款|影帝|影后", "可能用了明星网红或平台内容，确认版权"),
    ("A3", "红线", r"点点互动|世纪华通|青帝|[Qq]ingdi|[Cc]entury ?[Gg]ames|[Dd]ian ?[Dd]ian|有限公司|科技公司", "公司和主体名称"),
    ("A3", "红线", r"高级账号|高级号|内部服|内部号|内部账号|当托|托儿|游戏托", "高级账号、内部服、当托"),
    ("A3", "提醒", r"老板|策划|制作人|运营|客服|程序员", "涉及工作人员，不能丑化；星广素材干脆不涉及"),
    ("A3", "提醒", r"大R|土豪|氪佬|榜一", "不拿大R做文章、不丑化玩家"),
    ("A4", "红线", r"领导人|革命|贪官|自焚|六四|国旗|国徽|国家机关|中央|国务院|政府|专供|特供", "政治、国家名义、专供特供"),
    ("A4", "红线", r"日本|日式|日军|鬼子", "日本元素"),
    ("A4", "提醒", r"和服|武士|忍者|富士山|樱花|天皇|东京", "可能算日本元素"),
    ("A4", "提醒", r"(?<!\d)6\.?4(?!\d)|648|坦克", "64、648、坦克：敏感节点必须避开，平时尽量不用"),
    ("A4", "提醒", r"\d*64\d+|\d+64\d*", "数字里带 64（含战力数字）"),
    ("A5", "提醒", r"洗脚水|肚子搞大|上床|开房|睡了|性感|身材|胸|美女|小姐姐|老婆们|宝贝们|最美|颜值|女玩家", "可能擦边或物化女性，2026-07 起擦边一律不做"),
    ("A6", "红线", r"盘口|上分|下分|荷官|赔率|返水|通杀|角子|老虎机|捕鱼机|水果机|下注|押注|筹码", "赌博术语和器具"),
    ("A6", "必改", r"捕鱼|打鱼|赌", "「打孔捕鱼」被判中危；赌字看语境"),
    ("A6", "红线", r"抽烟|香烟|烟草|吸烟|喝酒|啤酒|白酒|红酒|劲酒|酒吧|醉了|干杯", "烟酒"),
    ("A7", "提醒", r"(?<![回满残吸热放失补])血(?![量条包])|尸体|肢解|爆头|砍头|杀人|屠杀|枪|子弹|炮弹|军队|军用|军事|士兵开火", "暴力血腥、枪炮军武，画面要不见红、不新加枪炮"),
    ("A7", "提醒", r"鬼怪|闹鬼|阴森|丧葬|葬礼|棺材|骷髅", "恐怖元素"),
    # B 字幕口播
    ("B4", "必改", r"国家级|世界级|史上|全网第一|宇宙第一|TOP|[Nn][Oo]\.?1|年度游戏", "极限词，换 T0、超、无敌、第一"),
    ("B4", "必改", r"最(?!后|近|终|初|早|晚|开始|大生命|低伤害|大值|小值|高等级|大容量)", "「最」算极限词，游戏里本来就有的「最大生命值」「最低伤害」可以"),
    ("B5", "必改", r"\d+(\.\d+)?\s*多?\s*(元|块钱|万元|[wW]元|RMB|rmb|美元|美金)|[一二两三四五六七八九十百千几]+\s*(块钱|元钱|元)|一分钱|[¥￥]", "带单位的金额和 ¥，只写数字不带单位"),
    ("B5", "必改", r"\d+\s*块(?=$|[，。,.!！?？\s]|礼包|买|充|的礼包)", "带单位的金额"),
    ("B5", "提醒", r"(?<![赚])钱", "「钱」字算敏感词"),
    ("B6", "必改", r"零氪|0氪|〇氪|不氪|零充|0充|不花钱|免费送|平民|白嫖|自动采集|自动建造|直接充|折充|\d+折", "付费只能说「不用氪金」"),
    ("B6", "提醒", r"(?<!不用)氪(?!金)|(?<!不用)氪金", "除了「不用氪金」，氪字都要看一眼"),
    ("B7", "必改", r"地球人都在|\d+%的人|百分之\S+的人|畅销榜|排行榜|榜首|排名第|下载量|好评率", "没法证明的数字和排名"),
    ("B7", "提醒", r"都在玩|人人都|所有人都", "泛指人数，字节要数据证明"),
    ("B8", "必改", r"仅限|截止|限时|只剩\d+|最后\d+(天|小时|分钟)|\d+岁的?都|\d+后都", "限时限地、「多少岁的都」"),
    ("B8", "提醒", r"(东北|西北|南方|北方|[一-鿿]{1,3}[省市县村])的?人都", "「某地的人都…」句式"),
    ("B9", "必改", r"熬夜|通宵|摆烂|玩不完|一玩玩一天|一玩就是一天|停不下来|上瘾|上头|根本停不", "防沉迷词"),
    ("B10", "必改", r"卧槽|我靠|我擦|尼玛|他妈|妈的|tmd|TMD|绿茶婊|矮矬穷|摸鱼|躺平|昏君|icu|ICU|高锰酸钾|赚米|故伎重施|力工|加油站|傻[逼比Bb]|sb|SB|[滚](?=开|出去|蛋|吧|$|[!！]+)", "敏感词和粗口"),
    ("B10", "提醒", r"犯罪|坐牢|监狱|战争|打仗|炸药|火药", "犯罪、战争相关"),
    ("B11", "提醒", r"救命|快跑|来不及了|[!！]{3,}", "吓人催人的字幕配箭头指向会判虚假紧迫"),
    ("B12", "必改", r"中毒|中奖|恭喜你|到账|红包|已领取|领取成功|系统提示|版本更新|青少年模式", "虚假提示、仿系统界面"),
    ("B13", "提醒", r"新闻|快讯|通报|通告|记者|报道|官方宣布|官宣|据悉", "仿新闻、仿官方通告"),
    # C 画面界面（文字能看到的部分）
    ("C1", "必改", r"出发相应模块", "提示语错字，应为「触发相应模块」"),
    ("C2", "必改", r"立即领取|立即下载|点击下载|点击领取|点击试玩|下载试玩|点我|戳这里|点这里|点下方|点击链接", "引导点击、虚假按钮"),
    ("C2", "提醒", r"关闭|跳过|返回|复活|滑动解锁|确定要", "画面上出现这类按钮要打码或模糊"),
    ("C5", "必改", r"寒霜启示录|Whiteout|whiteout", "国际服画面"),
    ("C6", "必改", r"预约|公测|内测|即将上线|首发", "预约类内容"),
    # D 和游戏对得上
    ("D2", "必改", r"上线就送|送\d+个|送[两三四五六七八九十]个|开局送", "福利只用四种说法，不加码"),
    # E 按类型
    ("E3", "提醒", r"啃老|未婚先孕|伪娘|男扮女装|任你选|下跪|锦旗|发誓|赌咒|撕钱|撒钱|砸钱|拜金|炫富|大胃王|不孝|卸载|投诉|维权|调解|假一赔|身份证|警察|医生说", "巨量的虚假情景演绎、违背主流价值观清单"),
]

STARS = {"Tim": "品牌推荐官", "范明": "明星推荐官", "姜超": "明星推荐官", "刘奕君": "明星推荐官",
         "小沈阳": "代言人", "李乃文": "代言人"}
WELFARE = {"茉莉": ("传说英雄", "签到"), "娜塔莉亚": ("首充",), "巴希提": ("史诗英雄", "登录"),
           "谢尔盖": ("史诗英雄", "抽卡")}
EN_HARD = {"SSR", "SR", "SP", "UR", "BOSS", "BUFF", "DEBUFF", "VIP", "PK", "MVP", "OK", "NPC", "LV", "CP"}
EN_OK = {"AI", "UE", "GOF", "GOFCN", "T", "TOP", "NO"}

UNPAID_DAYS = {3: (15, 3e6), 7: (18, 6e6), 10: (20, 8e6), 15: (22, 1e7), 30: (25, 2e7), 45: (28, 3e7), 57: (30, 5e7)}
PAID_DAYS = {3: (30, 6e7), 7: (30, 1e8), 10: (30, 1.3e8)}
LEVEL_ONLY = {15: 2.5e6, 20: 6e6, 25: 1.8e7, 30: 5e7}

CN_DIG = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNIT = {"十": 10, "百": 100, "千": 1000}
NUM = r"[\d.,]+|[零〇一二两三四五六七八九十百千]+"


def cn2num(s):
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        pass
    total, cur = 0, 0
    for ch in s:
        if ch in CN_DIG:
            cur = CN_DIG[ch]
        elif ch in CN_UNIT:
            total += (cur or 1) * CN_UNIT[ch]
            cur = 0
    return total + cur


def fmt(v):
    return f"{v / 1e8:g}亿" if v >= 1e8 else f"{v / 1e4:g}万"


def read_units(path):
    """返回 [(位置, 文本)]。字幕文件的位置是时间码，其他是行号。"""
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8-sig", errors="replace")
    name = "stdin" if path == "-" else Path(path).name
    suffix = "" if path == "-" else Path(path).suffix.lower()
    out = []
    if suffix in (".srt", ".vtt"):
        t = None
        for i, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            m = re.match(r"(\d+:\d+:\d+[,.]\d+)\s*-->", line)
            if m:
                t = m.group(1).replace(",", ".")
            elif line and not line.isdigit() and line != "WEBVTT":
                out.append((f"{name} {t or i}", re.sub(r"<[^>]+>", "", line)))
    elif suffix == ".ass":
        for line in raw.splitlines():
            if line.startswith("Dialogue:"):
                parts = line.split(",", 9)
                if len(parts) == 10:
                    out.append((f"{name} {parts[1]}", re.sub(r"\{[^}]*\}", "", parts[9]).replace("\\N", " ")))
    else:
        for i, line in enumerate(raw.splitlines(), 1):
            if line.strip():
                out.append((f"{name}:{i}", line.strip()))
    return out


def check_english(text):
    hits = []
    for m in re.finditer(r"[A-Za-z]+", text):
        tok, s, e = m.group(), m.start(), m.end()
        # 跳过空格看两边，「嗨 B」也算贴着汉字
        before = text[:s].rstrip(" \u3000")[-1:]
        after = text[e:].lstrip(" \u3000")[:1]
        cjk_b = bool(re.match(r"[一-鿿]", before))
        cjk_a = bool(re.match(r"[一-鿿]", after))
        if tok.upper() in EN_OK or (tok in ("A", "B") and after and after in "面段版"):
            continue
        if re.match(r"\d{3}", text[e:e + 3]):
            hits.append(("B2", "必改", tok + text[e:e + 3], "礼包码、人名用字母代替，改成中文加数字，如林子聪666"))
        elif tok.upper() in EN_HARD:
            hits.append(("B3", "必改", tok, "英文改中文：SSR 英雄写传说英雄，BOSS 写怪"))
        elif len(tok) == 1 and (cjk_b or cjk_a):
            hits.append(("B1", "必改", text[max(0, s - 2):e + 2], "单个字母代字（见G了、嗨B）"))
        elif tok.islower() and (cjk_b or cjk_a):
            hits.append(("B1", "必改", text[max(0, s - 2):e + 2], "拼音代字（读jia书、升级rongru）"))
        else:
            hits.append(("B3", "提醒", tok, "英文，能换中文就换"))
    return hits


def check_game(text):
    """熔炉、战力、天数、人数对表。text 是当前行加下一行。"""
    hits = []
    lv = [int(cn2num(x)) for x in re.findall(r"熔炉\s*(?:等级)?\s*(" + NUM + r")\s*级", text)]
    lv += [int(cn2num(x)) for x in re.findall(r"(" + NUM + r")\s*级\s*(?:的)?\s*(?:大)?熔炉", text)]
    power = []
    for n, u in re.findall(r"战力[^，。,；;\n]{0,6}?(" + NUM + r")\s*个?\s*(万|亿|[wW])", text):
        power.append(cn2num(n) * (1e8 if u == "亿" else 1e4))
    for n in re.findall(r"战力\s*([\d,]{7,})(?![\d万亿wW])", text):
        power.append(cn2num(n))
    days = [int(cn2num(x)) for x in re.findall(r"(" + NUM + r")\s*天", text) if cn2num(x) > 0]
    paid = bool(re.search(r"付费|充值|充了|氪金玩家|大R|氪佬|土豪", text)) and not re.search(r"零氪|0氪|不氪|不付费|平民|免费", text)

    for L in lv:
        if L > 30:
            hits.append(("D1", "必改", f"熔炉{L}级", "熔炉最高 30 级"))
    allowed = {}
    for L, p in LEVEL_ONLY.items():
        allowed.setdefault(L, set()).add(p)
    for d, (L, p) in UNPAID_DAYS.items():
        allowed.setdefault(L, set()).add(p)
    if paid:
        for d, (L, p) in PAID_DAYS.items():
            allowed[L].add(p)
    for p in power:
        if p >= 1e8 and not paid:
            hits.append(("D1", "必改", f"战力{fmt(p)}", "没说是付费玩家，战力不写过亿"))
        for L in lv:
            if L > 30:
                continue
            if L not in allowed:
                hits.append(("D1", "提醒", f"熔炉{L}级", "表里没有这个等级，别自己估，就近用表里的数"))
            elif not any(abs(p - a) / a < 0.01 for a in allowed[L]):
                ok = "、".join(fmt(a) for a in sorted(allowed[L]))
                hits.append(("D1", "必改", f"熔炉{L}级 战力{fmt(p)}", f"表里 {L} 级是 {ok}"))
        if not lv:
            for d in days:
                table = PAID_DAYS if paid else UNPAID_DAYS
                if d in table and abs(p - table[d][1]) / table[d][1] >= 0.01:
                    hits.append(("D1", "必改", f"{d}天 战力{fmt(p)}", f"表里{'付费' if paid else '不付费'} {d} 天是 {fmt(table[d][1])}"))
                elif d not in table and d <= 60:
                    hits.append(("D1", "提醒", f"{d}天 战力{fmt(p)}", "表里没有这个天数，别自己估"))
    if lv and days and not power:
        for d in days:
            table = PAID_DAYS if paid else UNPAID_DAYS
            for L in lv:
                if d in table and L != table[d][0]:
                    hits.append(("D1", "必改", f"{d}天 熔炉{L}级", f"表里{'付费' if paid else '不付费'} {d} 天是 {table[d][0]} 级"))

    for n, u in re.findall(r"(" + NUM + r"|上)\s*(亿|万)\s*多?\s*名?\s*(?:的)?\s*(?:玩家|人|用户|幸存者|领主|指挥官)", text):
        if u == "亿" and n != "上" and cn2num(n) == 3:
            hits.append(("D3", "提醒", f"{n}{u}", "口径对；字节拒过「三亿人都在玩」，投字节要附数据证明，被拒找投放补"))
            continue
        hits.append(("D3", "必改", f"{n}{u}", "人数只写全球 3 亿，不说 1 亿，别的人数不写"))

    for n in re.findall(r"火晶[^，。,]{0,8}?(" + NUM + r")\s*级", text):
        if int(cn2num(n)) != 30:
            hits.append(("D4", "必改", f"火晶{n}级", "火晶 30 级才解锁"))
    if "副本" in text:
        hits.append(("D4", "提醒", "副本", "游戏里没有的副本不写"))
    for name, need in WELFARE.items():
        if name in text and not all(k in text for k in need):
            hits.append(("D2", "提醒", name, "福利说法对一下：第二天签到送传说英雄茉莉 / 首充送娜塔莉亚 / 登录送史诗英雄巴希提 / 首次抽卡必出史诗英雄谢尔盖"))
    for star, title in STARS.items():
        if re.search(rf"(?<![A-Za-z]){star}(?![A-Za-z])", text):
            wrong = "推荐官" if title == "代言人" else "代言人"
            if wrong in text:
                hits.append(("E5", "必改", f"{star} {wrong}", f"{star} 的头衔是{title}"))
            else:
                hits.append(("E5", "提醒", star, f"明星素材：头衔是{title}，投前确认授权材料在账户里"))
    return hits


def has_lv(t):
    return bool(re.search(r"熔炉|级\s*(?:的)?\s*(?:大)?熔炉", t) and re.search(r"\d+\s*级|[一二三四五六七八九十]+\s*级", t))


def has_pw(t):
    return "战力" in t


def scan(units):
    found, seen = [], set()
    full = "".join(t for _, t in units)
    for i, (pos, text) in enumerate(units):
        hits = check_game(text)
        nxt = units[i + 1][1] if i + 1 < len(units) else ""
        if has_lv(text) and not has_pw(text) and has_pw(nxt) and not has_lv(nxt):
            hits += [h for h in check_game(text + " " + nxt) if h[0] == "D1" and "战力" in h[2] and "熔炉" in h[2]]
        for rid, lvl, pat, note in RULES:
            for m in re.finditer(pat, text):
                hits.append((rid, lvl, m.group(), note))
        hits += check_english(text)
        for h in hits:
            key = (h[0], h[2])
            if key in seen:
                continue
            seen.add(key)
            found.append({"rule": h[0], "level": h[1], "pos": pos, "hit": h[2], "note": h[3], "text": text[:60]})
    # 「须」「需」都算对：规则原文是「须」，官方警示语 PNG 和合规示例图是「需」
    if TIP not in re.sub(r"\s", "", full).replace("需达到", "须达到") and "出发相应模块" not in full:
        if "广告创意仅供参考" in full:
            found.append({"rule": "C1", "level": "必改", "pos": "全文", "hit": "提示语", "note": "提示语和原文不一致，照 standard.md C1 原文改", "text": ""})
        else:
            found.append({"rule": "C1", "level": "提醒", "pos": "全文", "hit": "提示语", "note": "文字里没找到提示语；涉及玩法的素材要在画面中下加上", "text": ""})
    found.sort(key=lambda f: LEVELS.index(f["level"]))
    return found


def main():
    # Windows 控制台默认 GBK，遇到 ¥ 这类字会崩，读写统一 UTF-8
    for f in (sys.stdin, sys.stdout):
        f.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="文件路径，- 表示 stdin")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    units = []
    for f in args.files:
        units += read_units(f)
    found = scan(units)
    if args.json:
        print(json.dumps(found, ensure_ascii=False, indent=1))
        return
    count = {lv: sum(f["level"] == lv for f in found) for lv in LEVELS}
    print(f"共 {len(units)} 段文字，红线 {count['红线']} / 必改 {count['必改']} / 提醒 {count['提醒']}（机器初筛，结论要人看）")
    for f in found:
        print(f"[{f['level']}] {f['rule']} {f['pos']}  「{f['hit']}」 {f['note']}" + (f"\n      原文：{f['text']}" if f["text"] else ""))


if __name__ == "__main__":
    main()
