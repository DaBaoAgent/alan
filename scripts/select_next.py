# -*- coding: utf-8 -*-
"""候选池过滤：python select_next.py <candidates.json>
candidates.json 结构: [{"cn":"片名","en":"English Title","year":1985,"director":"","actress":"","note":""}, ...]
输出: 可做清单（未在已解说库）+ 疑似已做（名字部分撞车，需人工复核）。"""
import sys, os, json, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))

def norm(s):
    return (s or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")

def extract_braced(title):
    """从投稿标题提取《片名》"""
    return [m.group(1) for m in re.finditer(r"《([^》]+)》", title or "")]

def main():
    if len(sys.argv) < 2:
        print("用法: python select_next.py <candidates.json>"); return
    done = json.load(open(os.path.join(HERE, "done_movies.json"), encoding="utf-8"))
    cands = json.load(open(sys.argv[1], encoding="utf-8"))
    # 全量投稿(653条): 《》片名 + 完整标题
    up_p = os.path.join(HERE, "uploaded_videos.json")
    up_titles, up_braced = [], []
    if os.path.exists(up_p):
        for v in json.load(open(up_p, encoding="utf-8"))["videos"]:
            up_titles.append(v["title"])
            up_braced.extend(extract_braced(v["title"]))
    up_braced = [norm(b) for b in up_braced]
    up_titles = [norm(t) for t in up_titles]
    ok, dup = [], []
    for c in cands:
        nc, ne = norm(c.get("cn")), norm(c.get("en", ""))
        hit = False
        for d in done:
            if (nc and any(nc in norm(p) or norm(p) in nc for p in [d["cn"], d.get("en","")] if p)) or \
               (ne and any(ne in norm(p) or norm(p) in ne for p in [d["cn"], d.get("en","")] if p)):
                hit = True; break
        if not hit:
            for b in up_braced:
                if nc and (nc in b or b in nc) or ne and (ne in b or b in ne):
                    hit = True; break
        if not hit:
            for t in up_titles:  # 全标题兜底(含无《》的)
                if nc and len(nc) >= 3 and nc in t:
                    hit = True; break
        (dup if hit else ok).append(c)
    print(f"===== 可做 {len(ok)} 部 =====")
    for i, c in enumerate(ok, 1):
        print(f"{i}. {c.get('cn')} | {c.get('en','')} | {c.get('year','')} | {c.get('director','')} | 女主:{c.get('actress','')} | {c.get('note','')}")
    if dup:
        print(f"\n===== 已解说/疑似 {len(dup)} 部 =====")
        for c in dup:
            print(f"- {c.get('cn')} | {c.get('en','')} | {c.get('note','')}")

if __name__ == "__main__":
    main()
