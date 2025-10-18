"""FastAPI 層：負責把前端請求交給 waa.py 處理，並將結果整理後回傳。

主要功能：
1. 產生敏感鞋（/api/generate_shoe），同時可設定訊號花色與生成張數。
2. 切牌模擬（/api/simulate_cut），以目前儲存的鞋子為基礎計算新的 rounds。
3. 匯出直式牌序與切牌命中統計（/api/export/*），提供下載檔案。

模組也會在檔案尾端掛載 /web 下的靜態檔案，讓同一個伺服器能提供 UI。
"""

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import io, csv, time

try:
    import waa  # type: ignore
    WAA_OK = True
except Exception:
    waa = None  # type: ignore
    WAA_OK = False

app = FastAPI()
# 啟用 CORS，允許任何來源呼叫 API（方便本地網頁測試）。
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# 注意：靜態掛載要放在 API 路由之後，避免攔截 /api/*


# --- 請求模型 ---
class GenReq(BaseModel):
    num_shoes: int
    signal_suit: str
    tie_signal_suit: Optional[str] = None


class CutReq(BaseModel):
    cut_pos: int


class ScanReq(BaseModel):
    banker_point: int
    player_point: int
    used_cards: int


# --- 內部狀態 ---
STATE = {"rounds": [], "tail": [], "deck": []}  # 暫存最近一次生成的鞋子資訊，供後續 API 使用


# --- 花色對應 ---
# 允許前端用字母或符號設定花色，這裡提供雙向對照表。
SUIT_LETTER_TO_SYMBOL = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
SUIT_SYMBOL_TO_LETTER = {sym: letter for letter, sym in SUIT_LETTER_TO_SYMBOL.items()}


def _suit_letter(val: Optional[str]) -> str:
    """把輸入轉成花色字母（S/H/D/C）。"""
    if not val:
        return ""
    s = str(val).strip()
    if not s:
        return ""
    upper = s.upper()
    if upper in SUIT_LETTER_TO_SYMBOL:
        return upper
    if s in SUIT_SYMBOL_TO_LETTER:
        return SUIT_SYMBOL_TO_LETTER[s]
    if upper in SUIT_SYMBOL_TO_LETTER:
        return SUIT_SYMBOL_TO_LETTER[upper]
    return upper


def _normalize_suit_input(val: Optional[str]) -> Optional[str]:
    """將字母或符號統一轉成 waa.py 內使用的花色符號。"""
    if not val:
        return None
    letter = _suit_letter(val)
    return SUIT_LETTER_TO_SYMBOL.get(letter, letter)


# --- 工具函式 ---
def _seq_points(cards):
    """呼叫 waa 原生方法計算莊、閒最終點數。"""
    if not WAA_OK or not cards:
        return None
    try:
        return waa._seq_points(cards)  # (banker_total, player_total)
    except Exception:
        return None


def _suit_counts(rounds, tail):
    """整合 rounds 與 tail，計算各花色剩餘張數。"""
    from collections import Counter
    all_cards = [c for r in rounds for c in getattr(r, "cards", [])] + (tail or [])
    counts = Counter()
    for card in all_cards:
        letter = _suit_letter(getattr(card, "suit", None))
        if letter:
            counts[letter] += 1
    return {
        "S": counts.get("S", 0),
        "H": counts.get("H", 0),
        "D": counts.get("D", 0),
        "C": counts.get("C", 0),
    }


def _serialize_rounds(rounds):
    """把 Round 清單轉成前端需要的序列化資料。"""
    out = []
    for r in rounds:
        seq_cards = getattr(r, "cards", [])
        cards = []  # 轉成前端好處理的卡片資料格式
        for c in seq_cards:
            suit_symbol = getattr(c, "suit", "")
            cards.append({
                "label": c.short(),
                "suit": _suit_letter(suit_symbol),
                "suit_symbol": suit_symbol,
            })

        banker_point = player_point = 0
        player_cards_labels = []
        banker_cards_labels = []
        try:
            if len(seq_cards) >= 4:
                P1, B1, P2, B2 = seq_cards[0:4]
                player_cards = [P1, P2]
                banker_cards = [B1, B2]
                p_tot = (P1.point() + P2.point()) % 10
                b_tot = (B1.point() + B2.point()) % 10
                natural = (p_tot in (8, 9)) or (b_tot in (8, 9))
                idx = 4
                p3 = None
                if not natural:
                    if p_tot <= 5 and idx < len(seq_cards):
                        p3 = seq_cards[idx]; idx += 1
                        player_cards.append(p3)
                        p_tot = (p_tot + p3.point()) % 10
                    if p3 is None:
                        if b_tot <= 5 and idx < len(seq_cards):
                            b3 = seq_cards[idx]; idx += 1
                            banker_cards.append(b3)
                            b_tot = (b_tot + b3.point()) % 10
                    else:
                        pt = p3.point()
                        def draw():
                            nonlocal idx, b_tot
                            if idx >= len(seq_cards):
                                return False
                            b3 = seq_cards[idx]; idx += 1
                            banker_cards.append(b3)
                            b_tot = (b_tot + b3.point()) % 10
                            return True
                        if b_tot <= 2:
                            draw()
                        elif b_tot == 3 and pt != 8:
                            draw()
                        elif b_tot == 4 and pt in (2,3,4,5,6,7):
                            draw()
                        elif b_tot == 5 and pt in (4,5,6,7):
                            draw()
                        elif b_tot == 6 and pt in (6,7):
                            draw()
                banker_point, player_point = b_tot, p_tot
                player_cards_labels = [c.short() for c in player_cards]
                banker_cards_labels = [c.short() for c in banker_cards]
            else:
                bp_pp = _seq_points(seq_cards) or (None, None)
                if isinstance(bp_pp, tuple) and len(bp_pp) == 2:
                    banker_point, player_point = bp_pp
        except Exception:
            bp_pp = _seq_points(seq_cards) or (None, None)
            if isinstance(bp_pp, tuple) and len(bp_pp) == 2:
                banker_point, player_point = bp_pp

        # 顏色序列（R/B）：優先使用 Card.color，否則用花色推斷（H/D=R; S/C=B）
        def rb(c):
            col = getattr(c, 'color', None)
            if col in ('R', 'B'):
                return col
            letter = _suit_letter(getattr(c, 'suit', ''))
            return 'R' if letter in ('H', 'D') else 'B'
        color_seq = ''.join(rb(c) for c in seq_cards)

        out.append({
            "result": getattr(r, "result", ""),
            "cards": cards,
            "player_point": player_point if player_point is not None else 0,
            "banker_point": banker_point if banker_point is not None else 0,
            "player": player_cards_labels,
            "banker": banker_cards_labels,
            "color_seq": color_seq,
        })
    return out


def _serialize_rounds_with_flags(rounds, tail):
    ordered = sorted(rounds, key=lambda x: x.start_index)
    views = [waa.RoundView(cards=r.cards, result=r.result) for r in ordered]
    if tail:
        tail_res = waa._seq_result(tail) or ''
        views.append(waa.RoundView(cards=tail, result=tail_res))
    try:
        s_idx_positions = set(waa.compute_sidx_new(views))
    except Exception:
        s_idx_positions = set()
    serialized = _serialize_rounds(ordered)
    signal_enabled = bool(getattr(waa, "HEART_SIGNAL_ENABLED", False))
    signal_suit = getattr(waa, "SIGNAL_SUIT", None)
    for idx, row in enumerate(serialized):
        is_idx = idx in s_idx_positions
        row["is_sidx"] = bool(is_idx)
        if not is_idx:
            row["s_idx_ok"] = False
            continue
        if signal_enabled and signal_suit:
            ok = any(getattr(card, "suit", None) == signal_suit for card in ordered[idx].cards)
        else:
            ok = True
        row["s_idx_ok"] = bool(ok)
    if tail:
        tail_positions = [c.pos for c in tail if isinstance(getattr(c, "pos", None), int)]
        tail_start = min(tail_positions) if tail_positions else None
        if tail_start is None:
            tail_start = (ordered[-1].start_index + len(ordered[-1].cards)) if ordered else 0
        tail_round = waa.Round(
            start_index=tail_start,
            cards=tail,
            result=waa._seq_result(tail) or '',
            sensitive=True,
        )
        tail_serialized = _serialize_rounds([tail_round])[0]
        banker_aliases = {'\u838a', 'Banker', 'B'}
        next_result = ordered[0].result if ordered else None
        tail_is_sidx = isinstance(next_result, str) and next_result.strip() in banker_aliases
        if tail_is_sidx and signal_enabled and signal_suit:
            tail_ok = any(getattr(card, "suit", None) == signal_suit for card in tail)
        else:
            tail_ok = tail_is_sidx
        tail_serialized["is_sidx"] = bool(tail_is_sidx)
        tail_serialized["s_idx_ok"] = bool(tail_ok)
        tail_serialized["is_tail"] = True
        serialized.append(tail_serialized)
    return serialized, ordered


def _rebuild_after_cut(deck, cut_pos):
    """切牌後依序模擬發牌，回傳新的 Round 清單。"""
    if not WAA_OK:
        return []
    cur = deck[cut_pos:] + deck[:cut_pos]
    i = 0
    rounds = []
    while i <= len(cur) - 4:  # 至少保留 4 張才能開局
        sim = waa.Simulator(cur[i:])
        r = sim.simulate_round(0, no_swap=True)
        if not r:
            break
        rounds.append(r)
        i += len(r.cards)
    return rounds


# --- API 端點 ---
@app.post("/api/generate_shoe")
def generate_shoe(req: GenReq):
    """產生敏感鞋，並整合 fallback 邏輯與序列化資料。"""
    if not WAA_OK:
        return {"error": "server_unavailable"}
    # 依請求安全地覆寫 waa 的可調整設定（若存在）
    try:
        if hasattr(waa, "NUM_SHOES"):
            setattr(waa, "NUM_SHOES", int(req.num_shoes))
        if hasattr(waa, "SIGNAL_SUIT") and isinstance(req.signal_suit, str):
            normalized = _normalize_suit_input(req.signal_suit)
            if normalized:
                setattr(waa, "SIGNAL_SUIT", normalized)
        # 和局訊號花色（若演算法支援且有設定值才覆寫）
        if hasattr(waa, "TIE_SIGNAL_SUIT") and req.tie_signal_suit:
            normalized_tie = _normalize_suit_input(req.tie_signal_suit)
            if normalized_tie:
                setattr(waa, "TIE_SIGNAL_SUIT", normalized_tie)
    except Exception:
        # 即使設定失敗也不中斷主流程
        pass
    last_error = None
    max_rule_retry = getattr(waa, "MAX_RULE_RETRY", 10)
    for attempt in range(max_rule_retry):
        rounds, tail, deck = waa.generate_all_sensitive_shoe_or_retry(
            max_attempts=waa.MAX_ATTEMPTS,
            min_tail_stop=waa.MIN_TAIL_STOP,
            multi_pass_min_cards=waa.MULTI_PASS_MIN_CARDS,
        )
        try:
            print(f"[API] generate_shoe: rounds={len(rounds)} tail={len(tail)} deck={len(deck)}")
        except Exception:
            pass
        # Fallback：若主流程沒有找到敏感局，改用 deck 再掃描；仍為 0 就退回切牌重建
        use_rounds = rounds
        fb = None
        if not use_rounds and deck:
            try:
                sim = waa.Simulator(deck)
                scanned = waa.scan_all_sensitive_rounds(sim)
                if scanned:
                    use_rounds = scanned
                    fb = "scan"
            except Exception:
                pass
        if (not use_rounds) and deck:
            rebuilt = _rebuild_after_cut(deck, 0)
            if rebuilt:
                use_rounds = rebuilt
                fb = fb or "all"

        try:
            processed_rounds, processed_tail = waa.apply_shoe_rules(use_rounds, tail)
        except RuntimeError as exc:
            last_error = exc
            continue

        serialized_rounds, ordered_rounds = _serialize_rounds_with_flags(processed_rounds, processed_tail)
        STATE.update({"rounds": ordered_rounds, "tail": processed_tail, "deck": deck})
        return {
            "rounds": serialized_rounds,
            "suit_counts": _suit_counts(ordered_rounds, processed_tail),
            "vertical": "\n".join(
                [c.short() for r in ordered_rounds for c in r.cards]
                + [c.short() for c in (processed_tail or [])]
            ),
            "meta": {"rounds_len": len(ordered_rounds), "tail_len": len(processed_tail), "deck_len": len(deck), "fallback": fb}
        }

    return {"error": "post_process_failed", "detail": str(last_error) if last_error else "unknown"}


@app.post("/api/simulate_cut")
def simulate_cut(req: CutReq):
    """依據指定切點重建回合序列，並更新快取資料。"""
    if not WAA_OK:
        return {"error": "server_unavailable"}
    if not STATE["deck"]:
        return {"error": "no_shoe"}
    rebuilt_rounds = _rebuild_after_cut(STATE["deck"], req.cut_pos)
    if not rebuilt_rounds:
        return {"error": "cut_failed"}
    try:
        processed_rounds, processed_tail = waa.apply_shoe_rules(rebuilt_rounds, STATE["tail"])
    except RuntimeError as exc:
        return {"error": "post_process_failed", "detail": str(exc)}
    serialized_rounds, ordered_rounds = _serialize_rounds_with_flags(processed_rounds, processed_tail)
    STATE["rounds"] = ordered_rounds
    STATE["tail"] = processed_tail
    return {
        "rounds": serialized_rounds,
        "suit_counts": _suit_counts(ordered_rounds, processed_tail),
        "vertical": "\n".join(
            [c.short() for r in ordered_rounds for c in r.cards]
            + [c.short() for c in (processed_tail or [])]
        ),
    }


@app.post("/api/scan")
def scan(req: ScanReq):
    """預留掃描功能，目前尚未實作，固定回傳空結果。"""
    # 尚未提供掃描演算法，先回傳 0
    return {"hits": [], "count": 0}


@app.get("/api/export/vertical")
def export_vertical_plain():
    """輸出目前 rounds 及 tail 的直式牌序，提供前端下載。"""
    if not STATE["rounds"] and not STATE["tail"]:
        return Response("No data", media_type="text/plain")
    text = "\n".join([c.short() for r in STATE["rounds"] for c in r.cards] + [c.short() for c in STATE["tail"]])
    return Response(text, media_type="text/plain")


@app.get("/api/export/cut_hits.csv")
def export_cut_hits_csv():
    """輸出切牌命中統計 CSV，方便後續離線分析。"""
    if not WAA_OK:
        return Response("Server unavailable", media_type="text/plain", status_code=503)
    if not STATE["deck"] or not STATE["rounds"]:
        return Response("No data", media_type="text/plain", status_code=404)

    marked = {r.cards[0].pos for r in STATE["rounds"]}
    if STATE["tail"]:
        marked.add(STATE["tail"][0].pos)
    rows, avg_hit, avg_rounds = waa.simulate_all_cuts(
        STATE["deck"], marked, use_b_order=True, rounds=STATE["rounds"], tail=STATE["tail"]
    )

    buf = io.StringIO()
    w = csv.writer(buf)
    headers = ['鞋號', '用張', '索引', '命中', '局數']
    w.writerow(['切牌命中統計'])
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    w.writerow(['', '', '', '', ''])
    w.writerow(['平均', f"{avg_hit:.3f}", '', '', f"{avg_rounds:.3f}"])
    ts = time.strftime("%Y%m%d_%H%M%S")
    data = buf.getvalue()
    return Response(
        data, media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=cut_hits_{ts}.csv"}
    )

# 將靜態站點掛載在最後，避免攔截 /api/* 路徑
app.mount("/", StaticFiles(directory="web", html=True), name="static")

