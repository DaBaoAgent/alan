# -*- coding: utf-8 -*-
"""艾伦已解说库查重：python check_done.py "候选片名" [更多片名...]
支持中文名/英文名/别名子串匹配，命中即提示已解说。"""
import sys, os, json, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))

def load_done():
    with open(os.path.join(HERE, "done_movies.json"), encoding="utf-8") as f:
        return json.load(f)

def load_bili():
    """全量投稿标题索引(YT+B站+文件夹合并, 653条), 返回 [(标题, bvid)]"""
    p = os.path.join(HERE, "uploaded_videos.json")
    if not os.path.exists(p):
        return []
    d = json.load(open(p, encoding="utf-8"))
    return [(v["title"], v.get("bvid", v.get("src", ""))) for v in d.get("videos", [])]

def norm(s):
    return (s or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")

def main():
    args = sys.argv[1:]
    if not args:
        print("用法: python check_done.py \"片名\" [...]"); return
    done = load_done()
    bili = load_bili()
    bili_norms = [(norm(t), t, b) for t, b in bili]
    for cand in args:
        nc = norm(cand)
        hits = []
        for d in done:
            pool = [d["cn"], d.get("en", "")]
            if any(nc and nc in norm(p) or norm(p) and norm(p) in nc for p in pool if p):
                hits.append(d)
        b_hits = [bt for bn, bt, b in bili_norms if nc and (nc in bn or bn in nc)]
        if hits or b_hits:
            print(f"【已解说】{cand}")
            for h in hits:
                print(f"   -> {h['cn']} | {h.get('en','')} | {h.get('year')} | {h.get('director','')} | {h.get('note','')}")
            for bt in b_hits[:3]:
                print(f"   -> B站投稿: {bt[:70]}")
        else:
            print(f"【未解说/可做】{cand}  (已解说库{len(done)}部+B站{len(bili)}条)")

if __name__ == "__main__":
    main()
