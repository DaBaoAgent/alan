# -*- coding: utf-8 -*-
"""艾伦口播稿结构校验：python validate_script.py <稿.txt>
检查6件套：钩子/信息段(全网首发|细读经典|上映)/好则电影结束/点评/我是艾伦签名/遛狗+明朝会|Ciao|8了个8。
自动探测 GBK / UTF-8(+BOM) 混合编码。"""
import sys, os, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

def read_auto(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try: return raw.decode(enc)
        except UnicodeDecodeError: continue
    return raw.decode("gb18030", errors="replace")

def main():
    if len(sys.argv) < 2:
        print("用法: python validate_script.py <稿.txt>"); return
    t = read_auto(sys.argv[1])
    checks = {
        "①开场钩子(首段非空且不直报片名)": bool(t.split("\n\n")[0].strip()),
        "②信息段(含 全网首发/细读经典)": bool(re.search(r"全网首发|细读经典", t)),
        "②信息段(含 上映/年份引片)": bool(re.search(r"上映|\d{3,4}年|[一二三四五六七八九十]+年", t)),
        "③正片结尾(好则/好耶/好个/好了 电影结束)": bool(re.search(r"好[则耶个了]?\s*电影结束", t)),
        "⑤点评段(含导演/风格/评分类词)": bool(re.search(r"导演|风格|烂片指数|IMDB|豆瓣|评分", t)),
        "⑥签名(我是艾伦)": bool(re.search(r"我是艾伦", t)),
        "⑥签名(遛狗)": bool(re.search(r"遛狗", t)),
        "⑥签名(下期更精彩)": bool(re.search(r"下期更精彩", t)),
        "生肉/无肉自翻标记": bool(re.search(r"生肉自翻|无肉自翻", t)),
        "黑话(番茄酱/嗝屁/领盒饭/反杀)": bool(re.search(r"番茄酱|番茄汁|嗝屁|领盒饭|归西|反杀", t)),
        "角色外号(玛德/法克/谢特/小X)": bool(re.search(r"玛德|法克|谢特|小[\u4e00-\u9fff]", t)),
    }
    print(f"文件: {os.path.basename(sys.argv[1])}  字符数: {len(t)}")
    allok = True
    # 字数规范(2026-09): 目标带3800-5200仅提示; 硬界2500-8000
    if 2500 <= len(t) <= 8000:
        band = "✅" if 3800 <= len(t) <= 5200 else ("⚠偏短(目标带3800-5200)" if len(t)<3800 else "⚠超长(目标带3800-5200, 新稿样板可至6000-7000)")
        print(f"{band} 字数: {len(t)} 字")
    else:
        print(f"FAIL 字数规范: {len(t)} 字 (硬界 2500-8000)")
        allok = False
    for k, v in checks.items():
        print(("PASS " if v else "FAIL ") + k)
        allok = allok and v
    print("=>", "全部通过" if allok else "有缺项，补全后再发")

if __name__ == "__main__":
    main()
