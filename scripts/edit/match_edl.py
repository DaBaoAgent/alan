# -*- coding: utf-8 -*-
"""匹配层：timeline + shots → edl.json（剪辑决策表）。

算法血统来自 movie-narrator 的 pipeline/match，保留这四项可复现的行为：
    1. act 分区（默认权重 0.15 / 0.25 / 0.40 / 0.20），句子按叙事位置分桶取镜；
    2. 贪心 topk（默认 5）+ 复用惩罚 0.15 + 回看窗口 3；
    3. 窗口 clamp：speed = 原片时长 / 配音时长 必须落在 [0.85, 1.25]，
       超出就以镜头中点为心扩/缩，撞到片头片尾则贴边；
    4. 多样性：滑动窗口 3 内同一镜头被用超过 2 次，换最近未用镜头并重新 clamp。

本项目的关键改动（movie-narrator 没有的）：
    **长句拆槽**。电影解说一句 8~18s，电影镜头平均 3~6s。原实现一句只配一个镜头，
    再靠 clamp 把窗口拉到 1.25 倍，长句仍然严重超时/超速。这里先把长句按标点切成
    k = ceil(句长 / 单槽上限) 个子槽，每槽独立选镜，并要求同句内源时间递增，
    于是 18s 的一句话会落到 3~4 个连续镜头，speed 全程保持在 ±15% 以内。

打分信号分三档（自动降级，结果里写明用了哪档）：
    embed   —— 镜头有画面描述 + sentence-transformers 可用：语义余弦 + 时间先验
    keyword —— 有描述但无模型：中文 2-gram 重叠 + 时间先验
    temporal—— 无描述：纯剧情时序先验（等于按比例猜，精度最低，必须明确告知）
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import build_dir, read_json, t_ff, t_human, write_json  # noqa: E402
else:
    from .common import build_dir, read_json, t_ff, t_human, write_json  # noqa: E402

# ---- movie-narrator 的默认值，改动前先想清楚为什么
MIN_SCORE = 0.25
CLAMP_MIN = 0.85
CLAMP_MAX = 1.25
TOPK = 5
REUSE_PENALTY = 0.15
REUSE_WINDOW = 3
MAX_REUSE = 2
DIVERSITY_WINDOW = 3
ACT_WEIGHTS = [0.15, 0.25, 0.40, 0.20]

_PUNCT_SPLIT = re.compile(r"(?<=[，,、；;])")


# ---------------------------------------------------------------- 打分

def _bigrams(text: str) -> set[str]:
    c = re.sub(r"[\W_]+", "", text)
    if len(c) < 2:
        return {c} if c else set()
    return {c[i:i + 2] for i in range(len(c) - 1)}


class Scorer:
    def __init__(self, shots: list[dict], mode: str = "auto"):
        self.shots = shots
        self.captioned = sum(1 for s in shots if s.get("caption"))
        self.ratio = self.captioned / max(1, len(shots))
        self.mode = mode
        self.model = None

        if mode == "auto":
            if self.ratio < 0.7:
                self.mode = "temporal"
            else:
                self.mode = "embed" if self._load_embed() else "keyword"
        elif mode == "embed":
            if not self._load_embed():
                self.mode = "keyword"

        print(f"  打分模式 {self.mode}（镜头描述覆盖 {self.ratio*100:.0f}%）")

    def _load_embed(self) -> bool:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception:  # noqa: BLE001
            return False
        name = "paraphrase-multilingual-MiniLM-L12-v2"
        try:
            self.model = SentenceTransformer(name)
            self.shot_vecs = self.model.encode(
                [s.get("caption") or "空镜头" for s in self.shots],
                normalize_embeddings=True, show_progress_bar=False,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] 向量模型加载失败（{exc}），降级 keyword")
            return False

    @staticmethod
    def temporal_score(shot_pos: float, expect_pos: float) -> float:
        # 只有时序信号时，位置差必须陡峭，否则 0.15 的复用惩罚会盖过 5% 的位置优势，
        # 镜头就会在相邻两三个镜之间来回跳（实测 0→1→0→2）。
        # 18% 片长以外的镜头直接 0 分。
        return max(0.0, 1.0 - abs(shot_pos - expect_pos) / 0.18)

    def text_score(self, text: str, shot: dict, shot_pos: float, expect_pos: float) -> tuple[float, str]:
        t = self.temporal_score(shot_pos, expect_pos)
        if self.mode == "temporal":
            return t, "temporal"
        if self.mode == "keyword":
            kw = len(_bigrams(text) & _bigrams(shot.get("caption") or "")) / max(
                1, len(_bigrams(text) | _bigrams(shot.get("caption") or "")))
            return 0.65 * kw + 0.35 * t, "keyword"
        if self.mode == "embed":
            vec = self.model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
            cos = float(sum(a * b for a, b in zip(vec, self.shot_vecs[shot["index"]])))
            return 0.75 * max(0.0, cos) + 0.25 * t, "embed"
        return t, self.mode


# ---------------------------------------------------------------- 结构

def act_map(n: int, weights: list[float]) -> list[int]:
    """按叙事权重把 N 句顺序切成 4 组（钩子 / 铺垫 / 正片 / 收尾）。"""
    bounds, cum = [], 0.0
    for w in weights:
        cum += w
        bounds.append(cum)
    acts = []
    for i in range(n):
        frac = (i + 0.5) / max(1, n)
        for k, b in enumerate(bounds):
            if frac <= b:
                acts.append(k)
                break
        else:
            acts.append(len(weights) - 1)
    return acts


def act_buckets(video_dur: float, weights: list[float]) -> list[tuple[float, float]]:
    out, cum = [], 0.0
    for w in weights:
        out.append((cum * video_dur, (cum + w) * video_dur))
        cum += w
    return out


def plan_slots(text: str, start: float, end: float, max_slot: float) -> list[dict]:
    """把一句按标点切成 k 个时间子槽；k 由句长/单槽上限决定。"""
    dur = end - start
    if dur <= max_slot:
        return [{"text": text, "start": start, "end": end, "sub": 0}]

    k = max(2, math.ceil(dur / max_slot))
    pieces = [p for p in _PUNCT_SPLIT.split(text) if p.strip()]
    if len(pieces) < k:  # 没有标点可切，就按字数硬切
        n = len(text)
        pieces = [text[round(i * n / k):round((i + 1) * n / k)] for i in range(k)]
        pieces = [p for p in pieces if p]

    total = sum(len(p) for p in pieces) or 1
    # 归并成不超过 k 组：切点落在累计字数的 total*(g+1)/k
    cuts = [round(total * (g + 1) / k) for g in range(k - 1)]
    groups: list[str] = []
    cur, consumed, cut_i = "", 0, 0
    for i, p in enumerate(pieces):
        cur += p
        consumed += len(p)
        if cut_i < len(cuts) and consumed >= cuts[cut_i] and i < len(pieces) - 1:
            groups.append(cur)
            cur = ""
            cut_i += 1
    if cur:
        groups.append(cur)

    while len(groups) > k:  # 切多了就并尾
        groups[-2] += groups[-1]
        groups.pop()

    slots = []
    t = start
    lens = sum(len(g) for g in groups) or 1
    for i, g in enumerate(groups):
        d = dur * len(g) / lens
        slots.append({"text": g, "start": t, "end": t + d, "sub": i})
        t += d
    if slots:
        slots[-1]["end"] = end
    return slots


# ---------------------------------------------------------------- 窗口

def clamp_window(src_start: float, src_end: float, narr_dur: float,
                 video_start: float, video_end: float,
                 clamp_min: float = CLAMP_MIN, clamp_max: float = CLAMP_MAX) -> tuple[float, float, bool]:
    """让 speed = src_dur / narr_dur 落在 [clamp_min, clamp_max]，围绕镜头中点伸缩。"""
    src_dur = src_end - src_start
    narr = max(0.1, narr_dur)
    factor = src_dur / narr
    if clamp_min <= factor <= clamp_max:
        return src_start, src_end, False

    target = narr * (clamp_max if factor > clamp_max else clamp_min)
    mid = (src_start + src_end) / 2.0
    new_start, new_end = mid - target / 2.0, mid + target / 2.0
    if new_start < video_start:
        new_start = video_start
        new_end = new_start + target
    if new_end > video_end:
        new_end = video_end
        new_start = new_end - target
        if new_start < video_start:
            new_start = video_start
    return max(video_start, new_start), min(video_end, new_end), True


def apply_diversity(clips: list[dict], shots: list[dict], video_dur: float,
                    window: int = DIVERSITY_WINDOW, max_reuse: int = MAX_REUSE) -> list[dict]:
    """窗口内同镜复用超限就换最近未用镜。"""
    swaps: list[dict] = []
    if len(shots) <= 1:
        return swaps
    for i in range(len(clips)):
        win = clips[max(0, i - window + 1): i + 1]
        counts: dict[int, int] = {}
        for c in win:
            counts[c["shot"]] = counts.get(c["shot"], 0) + 1
        cur = clips[i]["shot"]
        if counts.get(cur, 0) <= max_reuse:
            continue
        used = {c["shot"] for c in win}
        cands = [s for s in shots if s["index"] not in used and s.get("usable", True)]
        if not cands:
            continue
        # 优先往前找未用镜头：解说按剧情推进，往回跳会明显穿帮
        ahead = [s for s in cands if s["index"] > cur]
        best = min(ahead, key=lambda s: s["index"] - cur) if ahead else min(
            cands, key=lambda s: abs(s["index"] - cur))
        cs, ce, _ = clamp_window(best["start"], best["end"], clips[i]["narr_dur"],
                                 0.0, video_dur)
        clips[i].update({
            "shot": best["index"], "src_start": round(cs, 3), "src_end": round(ce, 3),
            "src_dur": round(ce - cs, 3),
            "speed": round((ce - cs) / max(0.1, clips[i]["narr_dur"]), 4),
            "expanded": True, "source": clips[i]["source"] + "+diversity",
        })
        swaps.append({"clip": clips[i]["n"], "from": cur, "to": best["index"]})
    return swaps


# ---------------------------------------------------------------- 主流程

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="匹配 → edl.json")
    ap.add_argument("--work")
    ap.add_argument("--segments", help="默认 <build>/segments.json")
    ap.add_argument("--timeline", help="默认 <build>/timeline.json")
    ap.add_argument("--shots", help="默认 <build>/shots.json")
    ap.add_argument("--out", help="默认 <build>/edl.json")
    ap.add_argument("--scorer", choices=["auto", "embed", "keyword", "temporal"], default="auto")
    ap.add_argument("--max-slot", type=float, default=0.0,
                    help="单槽配音上限秒数；0=按镜头均值自动（建议 4~7）")
    ap.add_argument("--act-constraint", choices=["on", "off"], default="on")
    ap.add_argument("--min-score", type=float, default=MIN_SCORE)
    ap.add_argument("--topk", type=int, default=TOPK)
    ap.add_argument("--absorb-gap", type=float, default=1.2,
                    help="把句间停顿吸收进上一句画面（最多这么多秒），否则画面会比配音短")
    ap.add_argument("--monotonic", choices=["on", "off"], default="on",
                    help="on=镜头随解说推进向前走，不回跳（解说按剧情顺序讲时应该开）")
    ap.add_argument("--aspect", default="16:9", choices=["16:9", "9:16"])
    args = ap.parse_args(argv)

    work = Path(args.work).resolve() if args.work else None
    build = build_dir(work) if work else build_dir(".")
    seg_p = Path(args.segments) if args.segments else build / "segments.json"
    tl_p = Path(args.timeline) if args.timeline else build / "timeline.json"
    sh_p = Path(args.shots) if args.shots else build / "shots.json"
    for p in (seg_p, tl_p, sh_p):
        if not p.exists():
            raise SystemExit(f"缺少 {p}：按 script → voice/align → shots 的顺序先跑")

    segments = read_json(seg_p)
    timeline = read_json(tl_p)
    shot_doc = read_json(sh_p)

    sents = timeline["sentences"]
    if len(sents) != len(segments["sentences"]):
        raise SystemExit("timeline 与 segments 句子数不一致，重跑 align_voice.py")

    all_shots = shot_doc["shots"]
    usable = [s for s in all_shots if s.get("usable", True)]
    video_dur = shot_doc.get("duration") or max(s["end"] for s in all_shots)
    audio_dur = timeline["duration"]
    avg_shot = sum(s["dur"] for s in usable) / max(1, len(usable))

    max_slot = args.max_slot or min(9.0, max(4.0, avg_shot * 1.2))
    print(f"镜头 {len(usable)} 个（均 {avg_shot:.2f}s）/ 配音 {audio_dur:.1f}s / 单槽上限 {max_slot:.2f}s")

    scorer = Scorer(usable, args.scorer)
    acts = act_map(len(sents), ACT_WEIGHTS) if args.act_constraint == "on" else [None] * len(sents)
    buckets = act_buckets(video_dur, ACT_WEIGHTS)
    video_end = video_dur

    clips: list[dict] = []
    recent: list[int] = []       # 最近选过的镜头（复用惩罚用）
    last_src_end = 0.0           # 同句内单调约束
    warnings: list[str] = []
    use_count: dict[int, int] = {}

    for si, sent in enumerate(sents):
        # 句间停顿（含段落停顿、场景停顿）没有对应解说词，但画面必须继续。
        # 把它并入本句最后一个槽，否则所有片段累计比配音短，音画会一路累积错位。
        nxt = sents[si + 1]["start"] if si + 1 < len(sents) else audio_dur
        end_eff = sent["end"]
        if args.absorb_gap > 0:
            end_eff = sent["end"] + min(args.absorb_gap, max(0.0, nxt - sent["end"]))

        slots = plan_slots(sent["text"], sent["start"], end_eff, max_slot)
        last_src_end = 0.0
        for slot in slots:
            narr_dur = max(0.3, slot["end"] - slot["start"])
            expect = ((slot["start"] + slot["end"]) / 2) / max(0.1, audio_dur)
            if args.monotonic == "on" and clips:
                prev_mid = (clips[-1]["src_start"] + clips[-1]["src_end"]) / 2 / max(0.1, video_dur)
                # 解说进度是下限：镜头至少要跟上"讲到哪儿"，允许略微超前，不允许倒退太多
                expect = max(expect, min(0.96, prev_mid - 0.02))
            act = acts[si]

            if act is not None:
                b0, b1 = buckets[act]
                pool = [s for s in usable if b0 <= (s["start"] + s["end"]) / 2 < b1]
                if len(pool) < args.topk:
                    pool = usable
            else:
                pool = usable

            scored = []
            for s in pool:
                pos = ((s["start"] + s["end"]) / 2) / max(0.1, video_dur)
                sc, src = scorer.text_score(slot["text"], s, pos, expect)
                scored.append((sc, src, s))
            scored.sort(key=lambda x: -x[0])

            best = None
            for sc, src, s in scored[:max(1, args.topk)]:
                reuse = sum(1 for r in recent[-REUSE_WINDOW:] if r == s["index"])
                eff = sc - REUSE_PENALTY * reuse
                if best is None or eff > best[0]:
                    best = (eff, sc, src, s)

            if best is None or best[1] < args.min_score:
                # 低于阈值不丢段：回退到"最靠近期望位置且未用过"的镜头
                cands = sorted(pool, key=lambda s: abs(
                    ((s["start"] + s["end"]) / 2) / max(0.1, video_dur) - expect))
                pick = next((c for c in cands if c["index"] not in recent[-REUSE_WINDOW:]), cands[0])
                eff, sc, src = 0.2, 0.2, "heuristic"
                warnings.append(f"句 {si} 槽 {slot['sub']} 无达标镜头，回退 heuristic")
            else:
                eff, sc, src, pick = best

            # 同句内源时间递增：优先挑不早于上一槽的候选
            if last_src_end > 0 and pick["start"] < last_src_end - 0.5:
                forward = [c for c in cands_sorted(scored) if c["start"] >= last_src_end - 0.5]
                if forward:
                    pick = forward[0]
                    sc, src = max(0.2, sc - 0.1), src + "+forward"

            cs, ce, expanded = clamp_window(pick["start"], pick["end"], narr_dur, 0.0, video_end)
            if ce - cs < 0.4:
                cs, ce = pick["start"], min(video_end, pick["start"] + max(1.0, narr_dur))

            clips.append({
                "n": len(clips),
                "seg": si,
                "sub": slot["sub"],
                "text": slot["text"],
                "narr_start": round(slot["start"], 3),
                "narr_end": round(slot["end"], 3),
                "narr_dur": round(narr_dur, 3),
                "src_start": round(cs, 3),
                "src_end": round(ce, 3),
                "src_dur": round(ce - cs, 3),
                "speed": round((ce - cs) / narr_dur, 4),
                "shot": pick["index"],
                "score": round(sc, 3),
                "eff": round(eff, 3),
                "source": src,
                "expanded": expanded,
            })
            recent.append(pick["index"])
            use_count[pick["index"]] = use_count.get(pick["index"], 0) + 1
            last_src_end = ce

    swaps = apply_diversity(clips, usable, video_end)

    # ---- 校验
    if clips:
        if abs(clips[0]["narr_start"] - sents[0]["start"]) > 0.05:
            warnings.append("首槽起点与首句起点不一致")
        for a, b in zip(clips, clips[1:]):
            gap = b["narr_start"] - a["narr_end"]
            if gap < -0.02:
                warnings.append(f"片段 {a['n']}→{b['n']} 配音时间重叠 {gap:.2f}s")
            elif gap > 0.05:
                warnings.append(f"片段 {a['n']}→{b['n']} 留白 {gap:.2f}s，画面会比配音短")
        speeds = [c["speed"] for c in clips]
        if min(speeds) < CLAMP_MIN - 1e-3 or max(speeds) > CLAMP_MAX + 1e-3:
            warnings.append(f"speed 越界 [{min(speeds):.2f},{max(speeds):.2f}]")
        covered = sum(c["narr_dur"] for c in clips)
        if abs(covered - (clips[-1]["narr_end"] - clips[0]["narr_start"])) > 0.2:
            warnings.append("槽时长累计与配音区间不符")
        if abs(clips[-1]["narr_end"] - sents[-1]["end"]) > 0.1:
            warnings.append("末槽终点与末句终点不一致")

    reuse_max = max(use_count.values()) if use_count else 0
    payload = {
        "name": segments.get("name"),
        "video": shot_doc["video"],
        "audio": timeline["audio"],
        "duration": round(audio_dur, 3),
        "frame": {"aspect": args.aspect, "width": 1920 if args.aspect == "16:9" else 1080,
                  "height": 1080 if args.aspect == "16:9" else 1920, "fps": 30},
        "params": {
            "max_slot": round(max_slot, 3), "act_weights": ACT_WEIGHTS,
            "clamp": [CLAMP_MIN, CLAMP_MAX], "topk": args.topk,
            "reuse_penalty": REUSE_PENALTY, "min_score": args.min_score,
            "act_constraint": args.act_constraint, "monotonic": args.monotonic,
        },
        "clips": clips,
        "stats": {
            "sentences": len(sents),
            "clips": len(clips),
            "slots_per_sentence": round(len(clips) / max(1, len(sents)), 2),
            "speed_min": min((c["speed"] for c in clips), default=1.0),
            "speed_max": max((c["speed"] for c in clips), default=1.0),
            "expanded": sum(1 for c in clips if c["expanded"]),
            "diversity_swaps": len(swaps),
            "max_reuse": reuse_max,
            "scorer": scorer.mode,
            "caption_coverage": round(scorer.ratio, 3),
            "heuristic_fallbacks": sum(1 for c in clips if c["source"] == "heuristic"),
            "coverage_sec": round(clips[-1]["narr_end"] - clips[0]["narr_start"], 3) if clips else 0,
        },
        "swaps": swaps,
        "warnings": warnings,
    }
    out = Path(args.out) if args.out else build / "edl.json"
    write_json(out, payload)

    st = payload["stats"]
    print(f"EDL 完成：{st['clips']} 个片段 / {st['sentences']} 句（平均 {st['slots_per_sentence']} 槽/句）")
    print(f"  speed [{st['speed_min']:.2f}, {st['speed_max']:.2f}] / 扩展窗口 {st['expanded']} / 换镜 {st['diversity_swaps']}")
    print(f"  打分 {st['scorer']} / 描述覆盖 {st['caption_coverage']*100:.0f}% / heuristic {st['heuristic_fallbacks']}")
    print(f"  edl : {out}")
    for w in warnings[:10]:
        print(f"  [warn] {w}")
    if st["scorer"] == "temporal":
        print("  [note] 只用剧情时序先验，画面语义并未参与匹配；要精准请先给 shots.json 补画面描述")
    return 0


def cands_sorted(scored) -> list[dict]:
    return [s for _sc, _src, s in scored]


if __name__ == "__main__":
    raise SystemExit(main())
