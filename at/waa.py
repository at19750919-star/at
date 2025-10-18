#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
產生「整靴全敏感局」的百家樂牌靴（8 副牌 / 416 張）。
需求：
- 不用 A 段、不要標記局；只保留敏感局（swap 前兩張→結果在閒/莊間翻轉、張數相同、且不把 原=和 且 換後=莊 算進來）。
- 主流程：先掃天然敏感局，再對剩牌做「重複洗牌補強」，盡量塞滿。
- 停止條件：當剩餘的牌無法排列成敏感局時(整副牌重洗。
- 如果只剩 4/5/6 張且任何排列都無法成為敏感局 → 放棄此靴、重洗重來。
- 若可排列成敏感局，程式會自動把尾局排列成敏感局，完成 416/416 全敏感。
- 也支援「手動指定最後一局順序」：若指定，並且與剩餘牌面一致且確實為敏感局，就使用手動順序；否則回退自動嘗試。

輸出：
- all_sensitive_B_rounds_*.csv    ：每副牌的敏感局清單（中文欄位，含尾局與花色統計，可一次列出多副）
- all_sensitive_vertical_*.csv    ：依 B 順序列出各牌組（含鞋序，便於逐張檢查）
- cut_hits_*.csv                  ：各鞋切牌模擬結果（中文欄位，附平均命中統計）

使用方式：
- 直接執行本腳本；可調整 CONFIG 區塊（包含 NUM_SHOES 可一次產生多副牌）。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict
import random, time, csv, collections, itertools, os

# =========================
# CONFIG（可依需求調整）
# =========================
SEED: Optional[int] = None        # 指定整體亂數種子；None 表示每次執行都不同
MAX_ATTEMPTS: int = 1000000       # 最多重試靴數（已設極高，請勿調小避免影響成功率）
# 花色處理（以下設定為流程必要條件，不建議修改為其他狀態）
HEART_SIGNAL_ENABLED: bool = True # 固定啟用訊號花色補位
SIGNAL_SUIT: str = '♥'            # 訊號花色（預設愛心，若需更換請同步調整流程）
A_PASSWORD_SUIT: Optional[str] = None
A_PASSWORD_COUNT: int = 0
B_PASSWORD_SUIT: Optional[str] = None
B_PASSWORD_COUNT: int = 0
TIE_SIGNAL_SUIT: Optional[str] = None  # ?��?訊�??�色（None 表示不使?��?
LATE_BALANCE_DIFF: int = 2         # 花色平衡目標：非訊號花色最大差 ≤ 此值（必須保持小數）
COLOR_RULE_ENABLED: bool = True    # 啟用卡牌顏色規則（紅黑各半；莊局前三張同色）

# 手動指定最後一局（可留空）。格式：例如 ["3♣","8♦","4♠","3♠","K♦"]
MANUAL_TAIL: List[str] = []
NUM_SHOES: int = 1               # 一次生成的敏感靴數量
MIN_TAIL_STOP: int = 7            # 剩餘 < 7 張時停止補強，交給尾局排敏感
MULTI_PASS_MIN_CARDS: int = 4     # 重複洗牌補強的最小剩牌門檻

# =========================
# 基本常數與資料結構
# =========================
SUITS = ['♠','♥','♦','♣']
NUM_DECKS = 8
RANKS = ['A'] + [str(i) for i in range(2, 10)] + ['10', 'J', 'Q', 'K']
CARD_VALUES = {**{str(i): i for i in range(2, 10)}, '10': 0, 'J': 0, 'Q': 0, 'K': 0, 'A': 1}

@dataclass
class Card:
    rank: str
    suit: str
    pos: int  # 0..415 在原靴的絕對索引
    color: Optional[str] = None  # 'R' 或 'B'；獨立於花色
    def point(self) -> int: return CARD_VALUES[self.rank]
    def short(self) -> str: return f"{self.rank}{self.suit}"

@dataclass
class Round:
    start_index: int
    cards: List[Card]
    result: str  # '閒' / '莊' / '和'
    sensitive: bool

@dataclass
class RoundView:
    cards: List[Card]
    result: str

@dataclass
class ShoeResult:
    shoe_index: int
    rounds: List[Round]
    tail: List[Card]
    deck: List[Card]

@dataclass
class CutSimulationResult:
    shoe_index: int
    rows: List[Tuple[int, int, int, str, int]]
    avg_hit: float
    avg_rounds: float

# =========================
# 牌靴與模擬
# =========================

def build_shuffled_deck() -> List[Card]:
    base = [Card(rank=r, suit=s, pos=-1) for s in SUITS for r in RANKS]
    deck: List[Card] = []
    for _ in range(NUM_DECKS):
        deck.extend([Card(c.rank, c.suit, -1) for c in base])
    random.shuffle(deck)
    for i, c in enumerate(deck): c.pos = i
    return deck

class Simulator:
    def __init__(self, deck: List[Card]):
        self.deck = deck

    def simulate_round(self, start: int, *, no_swap: bool = False) -> Optional[Round]:
        d = self.deck
        if start + 3 >= len(d):
            return None
        P1,B1,P2,B2 = d[start:start+4]
        idx = start + 4
        p_tot = (P1.point()+P2.point()) % 10
        b_tot = (B1.point()+B2.point()) % 10
        natural = (p_tot in (8,9)) or (b_tot in (8,9))
        p_cards=[P1,P2]; b_cards=[B1,B2]

        if not natural:
            p3=None
            if p_tot<=5:
                if idx>=len(d): return None
                p3=d[idx]; p_cards.append(p3); idx+=1; p_tot=(p_tot+p3.point())%10
            if p3 is None:
                if b_tot<=5:
                    if idx>=len(d): return None
                    b3=d[idx]; b_cards.append(b3); idx+=1; b_tot=(b_tot+b3.point())%10
            else:
                pt=p3.point()
                def draw():
                    nonlocal idx,b_tot
                    if idx>=len(d): return False
                    b3=d[idx]; b_cards.append(b3); idx+=1; b_tot=(b_tot+b3.point())%10; return True
                if b_tot<=2:
                    if not draw(): return None
                elif b_tot==3 and pt!=8:
                    if not draw(): return None
                elif b_tot==4 and pt in (2,3,4,5,6,7):
                    if not draw(): return None
                elif b_tot==5 and pt in (4,5,6,7):
                    if not draw(): return None
                elif b_tot==6 and pt in (6,7):
                    if not draw(): return None

        res = '和' if p_tot==b_tot else ('閒' if p_tot>b_tot else '莊')
        used = d[start:idx]
        if no_swap:
            return Round(start, used, res, False)

        # 敏感判定：只交換前兩張（P1↔B1），張數相同、結果在閒/莊間翻轉，且排除 原=和 且 換後=莊
        swap_res, same_len = self._swap_result(start)
        invalid_swap = (res == '和' and swap_res == '莊')
        sensitive = (
            (swap_res is not None)
            and (swap_res != res)
            and (swap_res != '和')
            and (same_len == len(used))
            and not invalid_swap
        )
        return Round(start, used, res, sensitive)

    def _swap_result(self, start: int) -> Tuple[Optional[str], int]:
        d2 = self.deck.copy()
        d2[start], d2[start+1] = d2[start+1], d2[start]
        sim2 = Simulator(d2)
        r2 = sim2.simulate_round(start, no_swap=True)
        if not r2: return None, 0
        return r2.result, len(r2.cards)

# =========================
# 掃描 / 重複洗牌補強（2222精神）
# =========================

def scan_all_sensitive_rounds(sim: Simulator) -> List[Round]:
    out: List[Round] = []
    last = len(sim.deck) - 1
    for i in range(last):
        r = sim.simulate_round(i)
        if r and r.sensitive:
            out.append(r)
    return out

def multi_pass_candidates_from_cards_simple(card_pool: List[Card]) -> List[Round]:
    """把剩餘牌重洗，找敏感局，並映射回原靴的卡片順序。"""
    if len(card_pool) < 4:
        return []
    # 洗剩牌
    shuffled = card_pool.copy()
    random.shuffle(shuffled)
    # 建臨時牌（pos=臨時索引）與映射到原牌
    temp_cards = [Card(c.rank, c.suit, i) for i,c in enumerate(shuffled)]
    idx2orig: Dict[int, Card] = {i: c for i,c in enumerate(shuffled)}
    temp_sim = Simulator(temp_cards)

    out: List[Round] = []
    used_idx: set[int] = set()
    i = 0
    while i < len(temp_cards) - 3:
        if i in used_idx:
            i += 1; continue
        r = temp_sim.simulate_round(i)
        if not r:
            i += 1; continue
        temp_indices = [c.pos for c in r.cards]
        if any(ti in used_idx for ti in temp_indices):
            i += 1; continue
        if not r.sensitive:
            i += len(r.cards); continue
        # 映回原牌，保持發牌順序
        ordered: List[Card] = []
        seen: set[int] = set()
        valid = True
        for ti in temp_indices:
            oc = idx2orig[ti]
            if oc.pos in seen: valid=False; break
            ordered.append(oc); seen.add(oc.pos)
        if not valid:
            i += 1; continue
        start_pos = ordered[0].pos
        out.append(Round(start_pos, ordered, r.result, True))
        used_idx.update(temp_indices)
        i = max(temp_indices) + 1
    return out

# =========================
# 尾局敏感化（自動/手動）
# =========================

def _seq_result(cards: List[Card]) -> Optional[str]:
    """回傳給定牌序作為一局時的結果（閒/莊/和）。"""
    if len(cards) < 4:
        return None
    tmp = [Card(c.rank, c.suit, i) for i, c in enumerate(cards)]
    sim = Simulator(tmp)
    r = sim.simulate_round(0)
    return r.result if r else None

def _seq_points(cards: List[Card]) -> Optional[Tuple[int, int]]:
    """計算給定牌序作為一局時，閒家與莊家的最終點數。"""
    if len(cards) < 4:
        return None
    
    # 為了不影響原始 Card 物件，這裡建立臨時副本
    temp_deck = [Card(c.rank, c.suit, i) for i, c in enumerate(cards)]
    
    P1, B1, P2, B2 = temp_deck[0:4]
    
    p_tot = (P1.point() + P2.point()) % 10
    b_tot = (B1.point() + B2.point()) % 10
    
    is_natural = (p_tot in (8, 9)) or (b_tot in (8, 9))
    
    card_idx = 4
    if not is_natural:
        p3 = None
        # 閒家補牌
        if p_tot <= 5:
            if card_idx < len(temp_deck):
                p3 = temp_deck[card_idx]
                p_tot = (p_tot + p3.point()) % 10
                card_idx += 1
        
        # 莊家補牌規則
        if p3 is None: # 閒家沒補牌
            if b_tot <= 5:
                if card_idx < len(temp_deck):
                    b3 = temp_deck[card_idx]
                    b_tot = (b_tot + b3.point()) % 10
        else: # 閒家有補牌
            p3_point = p3.point()
            should_draw = False
            if b_tot <= 2: should_draw = True
            elif b_tot == 3 and p3_point != 8: should_draw = True
            elif b_tot == 4 and p3_point in (2,3,4,5,6,7): should_draw = True
            elif b_tot == 5 and p3_point in (4,5,6,7): should_draw = True
            elif b_tot == 6 and p3_point in (6,7): should_draw = True
            
            if should_draw and card_idx < len(temp_deck):
                b3 = temp_deck[card_idx]
                b_tot = (b_tot + b3.point()) % 10

    return b_tot, p_tot

def _is_sensitive_sequence(cards: List[Card]) -> bool:
    if len(cards) < 4:
        return False
    temp = [Card(c.rank, c.suit, i) for i,c in enumerate(cards)]
    sim = Simulator(temp)
    r = sim.simulate_round(0)
    return bool(r and r.sensitive and len(r.cards) == len(temp))

def try_make_tail_sensitive(tail_cards: List[Card]) -> Optional[List[Card]]:
    k = len(tail_cards)
    if k not in (4,5,6):
        return None
    # 常見啟發式
    heuristics: List[List[Card]] = []
    heuristics.append(tail_cards[:])
    heuristics.append(list(reversed(tail_cards)))
    if k>=2:
        t = tail_cards[:]; t[0],t[1] = t[1],t[0]; heuristics.append(t)
    if k>=3:
        t = tail_cards[:]; t[1],t[2] = t[2],t[1]; heuristics.append(t)
    for cand in heuristics:
        if _is_sensitive_sequence(cand):
            return cand
    # 全排列（最多 720 種）
    for perm in itertools.permutations(tail_cards, k):
        cand = list(perm)
        if _is_sensitive_sequence(cand):
            return cand
    return None

def try_use_manual_tail(tail_cards: List[Card], manual: List[str]) -> Optional[List[Card]]:
    if not manual:
        return None
    # 先檢查牌面完全一致（多重集合相同）
    def multiset(seq: List[str]) -> collections.Counter:
        return collections.Counter(seq)
    target_ms = multiset(manual)
    avail_ms = multiset([c.short() for c in tail_cards])
    if target_ms != avail_ms:
        return None
    # 依 manual 順序重建
    short2stack: Dict[str, List[Card]] = collections.defaultdict(list)
    for c in tail_cards:
        short2stack[c.short()].append(c)
    ordered: List[Card] = []
    for face in manual:
        ordered.append(short2stack[face].pop())
    return ordered if _is_sensitive_sequence(ordered) else None

# =========================
# 花色處理（S_idx + 平衡）
# =========================

def compute_sidx_new(rounds: List[RoundView]) -> List[int]:
    """S_idx：當下一局結果為『莊』時，把當前局的索引加入（僅 B/尾局）。"""
    S: List[int] = []
    for i in range(len(rounds) - 1):
        if rounds[i+1].result == '莊':
            S.append(i)
    return S


def _ensure_signal_presence(
    rounds: List[RoundView], signal_suit: str, s_idx: List[int]
) -> set:
    """Fallback：若嚴格分配失敗，至少確保每個 S_idx 擁有一張訊號花色。"""
    donors = [
        (i, j)
        for i, r in enumerate(rounds)
        if i not in s_idx
        for j, card in enumerate(r.cards)
        if card.suit == signal_suit
    ]
    locked_ids: set = set()
    for idx in s_idx:
        rv = rounds[idx]
        if any(card.suit == signal_suit for card in rv.cards):
            continue
        receivers = [j for j, card in enumerate(rv.cards) if card.suit != signal_suit]
        if not donors or not receivers:
            raise RuntimeError("Insufficient signal suit donors for S_idx coverage")
        di, dj = donors.pop()
        rk = receivers.pop()
        rv.cards[rk].suit, rounds[di].cards[dj].suit = (
            rounds[di].cards[dj].suit,
            rv.cards[rk].suit,
        )
    # 鎖住所有 S_idx 中的訊號花色，避免後續平衡/顏色規則移除
    for idx in s_idx:
        for card in rounds[idx].cards:
            if card.suit == signal_suit:
                locked_ids.add(id(card))
    return locked_ids



def _is_tie_result(result: Optional[str]) -> bool:
    if not isinstance(result, str):
        return False
    val = result.strip()
    return val in {'和', 'Tie', 'T'}

def enforce_tie_signal(rounds: List[RoundView], tie_suit: str) -> set:
    """Ensure all tie-trigger rounds use the tie_suit and remove it elsewhere."""
    if not tie_suit:
        return set()
    tie_indices = [
        idx for idx in range(len(rounds) - 1)
        if _is_tie_result(rounds[idx + 1].result)
    ]
    locked_ids: set = set()
    alt_suits = [s for s in SUITS if s != tie_suit] or [tie_suit]
    counts = collections.Counter()
    for rv in rounds:
        for card in rv.cards:
            counts[card.suit] += 1
    for idx, rv in enumerate(rounds):
        if idx in tie_indices:
            for card in rv.cards:
                if card.suit != tie_suit:
                    counts[card.suit] -= 1
                    card.suit = tie_suit
                    counts[tie_suit] += 1
                locked_ids.add(id(card))
        else:
            for card in rv.cards:
                if card.suit == tie_suit:
                    counts[card.suit] -= 1
                    alt = min(alt_suits, key=lambda s: counts[s])
                    card.suit = alt
                    counts[alt] += 1
    return locked_ids


def balance_non_tie_suits(
    rounds: List[RoundView],
    tie_suit: Optional[str],
    locked_ids: set,
    tolerance: int,
):
    if not tie_suit:
        return
    other_suits = [s for s in SUITS if s != tie_suit]
    if not other_suits:
        return

    def counts() -> collections.Counter:
        c = collections.Counter()
        for rv in rounds:
            for card in rv.cards:
                c[card.suit] += 1
        return c

    for _ in range(160):
        c = counts()
        total_other = sum(c[s] for s in other_suits)
        if not total_other:
            return
        target = total_other / len(other_suits)
        hi = max(other_suits, key=lambda s: c[s] - target)
        lo = min(other_suits, key=lambda s: c[s] - target)
        if (c[hi] - target) <= tolerance and (target - c[lo]) <= tolerance:
            return
        moved = False
        for rv in rounds:
            for card in rv.cards:
                if card.suit != hi:
                    continue
                if id(card) in locked_ids:
                    continue
                card.suit = lo
                moved = True
                break
            if moved:
                break
        if not moved:
            break

def validate_tie_signal(rounds: List[RoundView], tie_suit: str) -> None:
    tie_indices = [
        idx for idx in range(len(rounds) - 1)
        if _is_tie_result(rounds[idx + 1].result)
    ]
    for idx in tie_indices:
        if any(card.suit != tie_suit for card in rounds[idx].cards):
            raise RuntimeError(f"Tie signal enforcement failed for index {idx}")
    forbidden = [
        idx for idx in range(len(rounds))
        if idx not in tie_indices and any(card.suit == tie_suit for card in rounds[idx].cards)
    ]
    if forbidden:
        raise RuntimeError(f"Tie signal suit present outside T rounds: {forbidden}")

def enforce_suit_distribution(rounds: List[RoundView], signal_suit: str, s_idx: List[int]) -> set:
    """將訊號花色分配到 s_idx 指定的局中，並鎖定這些牌以供後續平衡保護。"""
    # 1. 計算整副牌中訊號花色的總張數
    total_signal = sum(1 for r in rounds for c in r.cards if c.suit == signal_suit)
    # 2. 計算 S_idx 所涵蓋局的總容量（每局的張數加總）
    s_cap = sum(len(rounds[i].cards) for i in s_idx)
    if s_idx and s_cap < total_signal:
        print(f"[驗證] S_idx 容量不足：容量 {s_cap} < 訊號花色總數 {total_signal}，S_idx 長度={len(s_idx)}")
        raise RuntimeError(f"S_idx 容量不足 ({s_cap})，無法容納所有 {signal_suit} ({total_signal})")

    # 3. 收集所有非 S_idx 的訊號牌當 donors
    donors = []
    for i, r in enumerate(rounds):
        if i in s_idx:
            continue
        for j, card in enumerate(r.cards):
            if card.suit == signal_suit:
                donors.append((i, j))

    locked_ids = set()
    if not s_idx:
        return locked_ids

    # 4. 目標用「現況為下界」，不再硬性每局至少 1
    target = [0] * len(rounds)
    cur_sig = [0] * len(rounds)
    for i in s_idx:
        cur_sig[i] = sum(1 for c in rounds[i].cards if c.suit == signal_suit)
        target[i] = cur_sig[i]

    # 5. 只用「非 S_idx 的訊號數」去增加 target（容量優先）
    remain = total_signal - sum(target)  # = 非 S_idx 的訊號數
    if remain > 0:
        s_idx_sorted = sorted(
            s_idx,
            key=lambda idx: (len(rounds[idx].cards) - target[idx]),  # 尚可填入的容量
            reverse=True
        )
        ptr = 0
        while remain > 0:
            idx = s_idx_sorted[ptr]
            if target[idx] < len(rounds[idx].cards):
                target[idx] += 1
                remain -= 1
            ptr = (ptr + 1) % len(s_idx_sorted)

    # 6. 執行交換：把訊號補到各 S_idx 局
    for i in s_idx:
        cur_cnt = sum(1 for c in rounds[i].cards if c.suit == signal_suit)
        need = target[i] - cur_cnt
        if need <= 0:
            continue
        receivers = [k for k, c in enumerate(rounds[i].cards) if c.suit != signal_suit]
        for _ in range(need):
            if not donors or not receivers:
                print(f"[驗證] 交換資源不足：donors={len(donors)} receivers={len(receivers)}，S_idx 長度={len(s_idx)}")
                raise RuntimeError("花色交換資源不足")
            di, dj = donors.pop()
            rk = receivers.pop()
            rounds[i].cards[rk].suit, rounds[di].cards[dj].suit = rounds[di].cards[dj].suit, rounds[i].cards[rk].suit

    # 7. 嚴格模式：不得殘留訊號於非 S_idx
    assert not donors, f"Leftover signal-suit donors after allocation: {len(donors)}"


    # 8. 將所有已確定的訊號花色牌標記為鎖定，避免後續平衡時被重新調整
    for i in s_idx:
        for card in rounds[i].cards:
            if card.suit == signal_suit:
                locked_ids.add(id(card))
    return locked_ids

def late_balance(rounds: List[RoundView], locked_ids: set, diff: int, signal_suit: Optional[str], tie_suit: Optional[str] = None):
    """把最多的花色往最少的花色移動，直到差值 ≤ diff（跳過鎖定牌；可排除 signal_suit）。"""
    def counts() -> collections.Counter:
        c = collections.Counter()
        for r in rounds:
            for card in r.cards:
                c[card.suit] += 1
        return c

    for _ in range(120):
        c = counts()
        excluded = {s for s in (signal_suit, tie_suit) if s}
        suits_to_balance = [s for s in SUITS if s not in excluded] if excluded else SUITS
        if len(suits_to_balance) < 2:
            return True
        hi = max(suits_to_balance, key=lambda s: c.get(s, 0))
        lo = min(suits_to_balance, key=lambda s: c.get(s, 0))
        if c.get(hi, 0) - c.get(lo, 0) <= diff:
            return True
        moved = False
        for r in rounds:
            for card in r.cards:
                if id(card) in locked_ids: continue
                if card.suit == hi:
                    card.suit = lo
                    moved = True
                    break
            if moved: break
        if not moved: break
    c = collections.Counter()
    for r in rounds:
        for card in r.cards: c[card.suit] += 1
    excluded = {s for s in (signal_suit, tie_suit) if s}
    suits_to_balance = [s for s in SUITS if s not in excluded] if excluded else SUITS
    filtered = [c.get(s, 0) for s in suits_to_balance]
    final_diff = (max(filtered) - min(filtered)) if filtered else 0
    ok = final_diff <= diff
    if not ok:
        # 強化驗證輸出：平衡失敗時輸出分佈與門檻
        dist = ', '.join(f'{s}:{c.get(s, 0)}' for s in (suits_to_balance))
        sig = signal_suit if signal_suit else '-'
        print(f"[驗證] 花色平衡失敗：允許差<={diff}，分佈=({dist})，排除訊號花色={sig}")
    return ok

def _apply_color_rule_for_shoe(round_views: List[RoundView], tail: Optional[List[Card]]) -> None:
    """在整鞋定稿後套用紅黑顏色規則。
    每一局的前四張（或不足四張則全部）必須是：
      - 黑, 黑, 黑, 紅  或
      - 紅, 紅, 紅, 黑
    兩者若都可行則隨機選擇。最後再把剩餘配額平均分配到未上色牌上。
    僅設定 card.color，不更動 rank/suit。
    """
    # 計算全靴總張數
    all_cards: List[Card] = [c for rv in round_views for c in rv.cards] + (tail or [])
    total = len(all_cards)
    red_left = total // 2
    black_left = total - red_left

    def use(color: str, k: int) -> bool:
        nonlocal red_left, black_left
        if color == 'R':
            if red_left < k: return False
            red_left -= k
        else:
            if black_left < k: return False
            black_left -= k
        return True

    def assign_first_four(seq: List[Card]):
        nonlocal red_left, black_left
        k = min(4, len(seq))
        if k == 0:
            return
        pat1 = ['B', 'B', 'B', 'R']  # 黑黑黑紅
        pat2 = ['R', 'R', 'R', 'B']  # 紅紅紅黑

        need1_r = pat1[:k].count('R'); need1_b = pat1[:k].count('B')
        need2_r = pat2[:k].count('R'); need2_b = pat2[:k].count('B')

        ok1 = (red_left >= need1_r and black_left >= need1_b)
        ok2 = (red_left >= need2_r and black_left >= need2_b)

        if not ok1 and not ok2:
            # 嘗試在不破壞整體配額下使用替代（例如若牌不足但可以用倒置少於4張）
            raise RuntimeError("顏色配額不足（前四張模式無可用方案）")

        chosen = None
        if ok1 and ok2:
            chosen = random.choice([pat1, pat2])
        elif ok1:
            chosen = pat1
        else:
            chosen = pat2

        # 使用配額
        if not use('R', chosen[:k].count('R')) or not use('B', chosen[:k].count('B')):
            raise RuntimeError("顏色配額不足（使用時發生不一致）")

        for i in range(k):
            seq[i].color = 'R' if chosen[i] == 'R' else 'B'

    # 1. 逐局處理前四張
    for rv in round_views:
        assign_first_four(rv.cards)

    if tail:
        assign_first_four(tail)

    # 2. 最終分配：將所有剩餘的顏色配額，分配給所有還未上色的牌
    def fill_rest_robust(all_cards_seq: List[Card]):
        nonlocal red_left, black_left

        # 找出所有還未上色的牌
        uncolored = [c for c in all_cards_seq if c.color is None]

        # 建立剩餘顏色的 "配額池"
        color_pool = ['R'] * red_left + ['B'] * black_left

        # 安全檢查：未上色的牌數必須等於剩餘的配額總數
        if len(uncolored) != len(color_pool):
            # 若不符，嘗試補足差異（安全模式：將多餘配額隨機分配與調整）
            # 先嘗試平衡：如果配額不足或超出，調整為能填滿未上色
            diff = len(uncolored) - len(color_pool)
            if diff > 0:
                # 沒有足夠配額，不可接受
                raise RuntimeError(f"顏色分配邏輯錯誤：未上色牌數 {len(uncolored)} 與剩餘配額 {len(color_pool)} 不符。")
            else:
                # 若 color_pool 比 uncolored 多（理論上不會），縮減多餘配額
                color_pool = color_pool[:len(uncolored)]

        random.shuffle(color_pool)  # 隨機化分配

        for card in uncolored:
            card.color = color_pool.pop()

        # 更新剩餘配額為 0
        red_left = 0
        black_left = 0

    fill_rest_robust(all_cards)

    # 3. 最終驗證
    assert red_left == 0 and black_left == 0, f"顏色配額未對齊, 剩餘 R:{red_left}, B:{black_left}"

# =========================
# 主流程（一次打包 + 外層重試）
# =========================

def pack_all_sensitive_once(deck: List[Card], *, min_tail_stop: int, multi_pass_min_cards: int) -> Optional[Tuple[List[Round], List[Card]]]:
    sim = Simulator(deck)
    # 1) 掃全靴天然敏感
    all_sensitive = scan_all_sensitive_rounds(sim)
    # 2) 重複洗牌補強（吃到剩 < min_tail_stop 為止）
    #    用簡化版本：不停把剩牌重洗找敏感局、用到的牌從池子拿掉
    used_pos: set[int] = set()
    out_rounds: List[Round] = []

    # 先把天然敏感局放進暫存（不過濾重疊，後面用 used_pos 控制）
    for r in all_sensitive:
        if any(c.pos in used_pos for c in r.cards):
            continue
        out_rounds.append(r)
        for c in r.cards: used_pos.add(c.pos)

    # 反覆補強
    while True:
        remaining = [c for c in deck if c.pos not in used_pos]
        if len(remaining) < multi_pass_min_cards:
            break
        extra = multi_pass_candidates_from_cards_simple(remaining)
        if not extra:
            break
        for r in extra:
            if any(c.pos in used_pos for c in r.cards):
                continue
            out_rounds.append(r)
            for c in r.cards: used_pos.add(c.pos)
        # 若剩餘 >= min_tail_stop，繼續；否則交給尾局敏感化
        if len([c for c in deck if c.pos not in used_pos]) < min_tail_stop:
            break

    # 3) 處理尾局
    leftover = [c for c in deck if c.pos not in used_pos]
    if not leftover:
        return out_rounds, []
    if len(leftover) >= min_tail_stop:
        return None

    # 3a) 先試手動尾局
    tail = try_use_manual_tail(leftover, MANUAL_TAIL)
    if tail is None:
        # 3b) 自動排列
        tail = try_make_tail_sensitive(leftover)
    if tail is None:
        return None
    return out_rounds, tail


def generate_all_sensitive_shoe_or_retry(*, max_attempts: int, min_tail_stop: int, multi_pass_min_cards: int) -> Tuple[List[Round], List[Card], List[Card]]:
    """外層重試直到整靴 416/416 皆敏感。回傳：(敏感局、尾局牌（可能空）、完整牌靴)。"""
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        # 設定種子：若指定 SEED，每次以 SEED+attempt 改變；否則用時間熵
        if SEED is not None:
            random.seed(SEED + attempt)
        else:
            random.seed(time.time_ns() + attempt)
        deck = build_shuffled_deck()
        packed = pack_all_sensitive_once(deck, min_tail_stop=min_tail_stop, multi_pass_min_cards=multi_pass_min_cards)
        if packed is None:
            continue
        rounds, tail = packed
        total_cards = sum(len(r.cards) for r in rounds) + len(tail)
        if all(r.sensitive for r in rounds) and total_cards == 416:
            return rounds, tail, deck
    raise RuntimeError(f"重試 {max_attempts} 次仍無法全敏感；請提高 MAX_ATTEMPTS 或調整參數。")

# =========================
# 輸出
# =========================


def simulate_all_cuts(deck: List[Card], marked_start_pos: set[int], *, use_b_order: bool, rounds: List[Round], tail: List[Card]) -> Tuple[List[Tuple[int, int, int, str, int]], float, float]:
    if use_b_order:
        seq = [c for r in sorted(rounds, key=lambda x: x.start_index) for c in r.cards]
        if tail:
            seq += tail
    else:
        seq = deck
    rows: List[Tuple[int, int, int, str, int]] = []
    hit_vals: List[int] = []
    round_vals: List[int] = []
    for cut_start in range(len(seq)):
        hit_at, hit_pos, hit_card, rounds_before = first_hit_after_single_cut(seq, marked_start_pos, cut_start=cut_start)
        rows.append((cut_start + 1, hit_at, hit_pos, hit_card, rounds_before))

        if hit_at != -1:
            hit_vals.append(hit_at)
            round_vals.append(rounds_before)
    avg_hit = sum(hit_vals)/len(hit_vals) if hit_vals else 0.0
    avg_rounds = sum(round_vals)/len(round_vals) if round_vals else 0.0
    return rows, avg_hit, avg_rounds


def export_rounds(shoes: List[ShoeResult], ts: str) -> str:
    headers = ['起始', '張數', '結果', '敏感', '信花', '莊點', '閒點', '牌序', '顏色序']
    blocks: List[List[List[str]]] = []

    for shoe in shoes:
        rows: List[List[str]] = []
        sorted_rounds = sorted(shoe.rounds, key=lambda x: x.start_index)

        for r in sorted_rounds:
            signal_cnt = sum(1 for c in r.cards if c.suit == SIGNAL_SUIT)
            bpt, ppt = _seq_points(r.cards) or (None, None)
            colors = ''.join(('紅' if getattr(c, 'color', None) == 'R'
                              else '黑' if getattr(c, 'color', None) == 'B'
                              else '?') for c in r.cards)
            rows.append([
                str(r.start_index),
                str(len(r.cards)),
                r.result,
                'Y' if r.sensitive else '',
                str(signal_cnt),
                '' if bpt is None else str(bpt),
                '' if ppt is None else str(ppt),
                ''.join(c.short() for c in r.cards),
                colors,
            ])

        if shoe.tail:
            signal_cnt = sum(1 for c in shoe.tail if c.suit == SIGNAL_SUIT)
            bpt, ppt = _seq_points(shoe.tail) or (None, None)
            colors = ''.join(('紅' if getattr(c, 'color', None) == 'R'
                              else '黑' if getattr(c, 'color', None) == 'B'
                              else '?') for c in shoe.tail)
            rows.append([
                '尾局',
                str(len(shoe.tail)),
                _seq_result(shoe.tail) or '',
                'Y',
                str(signal_cnt),
                '' if bpt is None else str(bpt),
                '' if ppt is None else str(ppt),
                ''.join(c.short() for c in shoe.tail),
                colors,
            ])

        # 空白列與花色統計（與表頭 9 欄對齊）
        rows.append(['', '', '', '', '', '', '', '', ''])
        all_cards = [c for r in shoe.rounds for c in r.cards]
        if shoe.tail:
            all_cards.extend(shoe.tail)
        suit_counts = collections.Counter(c.suit for c in all_cards)
        for suit in SUITS:
            rows.append([f'花色{suit}', str(suit_counts.get(suit, 0)), '', '', '', '', '', '', ''])

        blocks.append(rows)

    path = f"all_sensitive_B_rounds_{ts}.csv"
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        if not blocks:
            return path
        # 只寫子表頭；不寫「鞋X」群組列
        sub_header: List[str] = []
        block_width = len(headers)
        for idx in range(len(blocks)):
            sub_header.extend(headers)
            if idx < len(blocks) - 1:
                sub_header.append('')
        w.writerow(sub_header)

        max_rows = max(len(block) for block in blocks)
        for i in range(max_rows):
            row: List[str] = []
            for idx, block in enumerate(blocks):
                if i < len(block):
                    row.extend(block[i])
                else:
                    row.extend([''] * block_width)
                if idx < len(blocks) - 1:
                    row.append('')
            w.writerow(row)
    return path



def export_vertical(shoes: List[ShoeResult], ts: str) -> str:
    headers = ['牌']
    blocks: List[List[List[str]]] = []
    for shoe in shoes:
        rows: List[List[str]] = []
        sorted_rounds = sorted(shoe.rounds, key=lambda x: x.start_index)
        for r in sorted_rounds:
            for c in r.cards:
                rows.append([c.short()])
        if shoe.tail:
            for c in shoe.tail:
                rows.append([c.short()])
        blocks.append(rows)

    path = f"all_sensitive_vertical_{ts}.csv"
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        if not blocks:
            return path
        group_header: List[str] = []
        sub_header: List[str] = []
        block_width = len(headers)
        for idx in range(len(blocks)):
            group_header.extend([f'鞋{idx+1}'] + [''] * (block_width - 1))
            sub_header.extend(headers)
            if idx < len(blocks) - 1:
                group_header.append('')
                sub_header.append('')
        w.writerow(group_header)
        w.writerow(sub_header)
        max_rows = max(len(block) for block in blocks)
        for i in range(max_rows):
            row: List[str] = []
            for idx, block in enumerate(blocks):
                if i < len(block):
                    row.extend(block[i])
                else:
                    row.extend([''] * block_width)
                if idx < len(blocks) - 1:
                    row.append('')
            w.writerow(row)
    return path


def export_cut_hits(stats: List[CutSimulationResult], ts: str) -> str:
    headers = ['切點', '命張', '命索', '命牌', '前局']
    blocks: List[List[List[str]]] = []
    for stat in stats:
        rows: List[List[str]] = []
        for cut_start, hit_at, hit_pos, hit_card, rounds_before in stat.rows:
            rows.append([
                str(cut_start),
                str(hit_at),
                str(hit_pos),
                hit_card,
                str(rounds_before),
            ])
        rows.append(['', '', '', '', ''])
        rows.append(['平均', f"{stat.avg_hit:.3f}", '', '', f"{stat.avg_rounds:.3f}"])
        blocks.append(rows)

    path = f"cut_hits_{ts}.csv"
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        if not blocks:
            return path
        group_header: List[str] = []
        sub_header: List[str] = []
        block_width = len(headers)
        for idx in range(len(blocks)):
            group_header.extend([f'鞋{idx+1}'] + [''] * (block_width - 1))
            sub_header.extend(headers)
            if idx < len(blocks) - 1:
                group_header.append('')
                sub_header.append('')
        w.writerow(group_header)
        w.writerow(sub_header)
        max_rows = max(len(block) for block in blocks)
        for i in range(max_rows):
            row: List[str] = []
            for idx, block in enumerate(blocks):
                if i < len(block):
                    row.extend(block[i])
                else:
                    row.extend([''] * block_width)
                if idx < len(blocks) - 1:
                    row.append('')
            w.writerow(row)
    return path

# =========================
# 單次切牌模擬：只在切牌時把前段移到尾巴；之後連續發牌（不回填）。
# 從 cut_start（0-based）開始，遇到任一敏感起點就停止，回傳「第幾張」發生。
# 例如切到第10張開始發 → cut_start=9。
# =========================

def first_hit_after_single_cut(deck: List[Card], marked_start_pos: set[int], cut_start: int = 0) -> Tuple[int, int, str, int]:
    cur = deck[cut_start:] + deck[:cut_start]
    total_dealt = 0
    rounds_before = 0  # 命中事件前已完成的局數
    i = 0  # 指向當前局第一張在 cur 中的索引
    while True:
        if i >= len(cur) - 3:
            return -1, -1, '', rounds_before
        start_pos = cur[i].pos
        if start_pos in marked_start_pos:
            return total_dealt + 1, start_pos, cur[i].short(), rounds_before
        # 用剩餘序列模擬此局需要幾張，然後 i 前進，不把已用牌放回尾端
        sim = Simulator(cur[i:])
        r = sim.simulate_round(0, no_swap=True)
        if not r:
            return -1, -1, '', rounds_before
        k = len(r.cards)
        i += k
        total_dealt += k
        rounds_before += 1


def apply_shoe_rules(rounds: List[Round], tail: Optional[List[Card]]) -> Tuple[List[Round], Optional[List[Card]]]:
    """Apply suit distribution and color rules to a generated shoe."""
    views: List[RoundView] = [RoundView(cards=r.cards, result=r.result) for r in sorted(rounds, key=lambda x: x.start_index)]
    tail_idx: Optional[int] = None
    banker_aliases = {'莊', 'Banker', 'B'}
    if tail:
        tail_res = _seq_result(tail) or ''
        views.append(RoundView(cards=tail, result=tail_res))
        tail_idx = len(views) - 1
    locked_ids: set = set()
    s_idx: List[int] = []
    if HEART_SIGNAL_ENABLED:
        s_idx = compute_sidx_new(views)
        if tail_idx is not None and views:
            first_res = views[0].result if views else None
            if isinstance(first_res, str) and first_res.strip() in banker_aliases and tail_idx not in s_idx:
                s_idx.append(tail_idx)
        try:
            signal_locked = enforce_suit_distribution(views, SIGNAL_SUIT, s_idx)
        except RuntimeError:
            signal_locked = _ensure_signal_presence(views, SIGNAL_SUIT, s_idx)
        locked_ids.update(signal_locked)
    if TIE_SIGNAL_SUIT:
        tie_locked = enforce_tie_signal(views, TIE_SIGNAL_SUIT)
        locked_ids.update(tie_locked)
        balance_non_tie_suits(views, TIE_SIGNAL_SUIT, locked_ids, LATE_BALANCE_DIFF)
    balanced = late_balance(
        views,
        locked_ids,
        LATE_BALANCE_DIFF,
        SIGNAL_SUIT if HEART_SIGNAL_ENABLED else None,
        TIE_SIGNAL_SUIT
    )
    if not balanced:
        raise RuntimeError("Late suit balance failed")
    if COLOR_RULE_ENABLED:
        _apply_color_rule_for_shoe(views, tail)
    if TIE_SIGNAL_SUIT:
        validate_tie_signal(views, TIE_SIGNAL_SUIT)
    if HEART_SIGNAL_ENABLED and s_idx:
        # 驗證：每個 S_idx 局至少含一張訊號花色，否則視為失敗
        missing = [
            idx for idx in s_idx
            if not any(card.suit == SIGNAL_SUIT for card in views[idx].cards)
        ]
        if missing:
            raise RuntimeError(f"Signal suit missing in S_idx rounds: {missing}")
    return rounds, tail

# =========================
# main
# =========================
if __name__ == '__main__':
    print("[開始] 目標：整靴 416/416 皆為敏感局（允許尾段 4/5/6 自動排列）")
    shoe_results: List[ShoeResult] = []
    cut_stats: List[CutSimulationResult] = []
    try:
        shoe_idx = 1
        while shoe_idx <= NUM_SHOES:
            print(f"\n[處理] 第 {shoe_idx} 副牌")
            rounds, tail, deck = generate_all_sensitive_shoe_or_retry(
                max_attempts=MAX_ATTEMPTS,
                min_tail_stop=MIN_TAIL_STOP,
                multi_pass_min_cards=MULTI_PASS_MIN_CARDS,
            )
            total_cards = sum(len(r.cards) for r in rounds) + len(tail)
            starts = sorted({r.start_index for r in rounds})
            # ���B�z�]�Y�ҥΡ^
            try:
                rounds, tail = apply_shoe_rules(rounds, tail)
            except RuntimeError as e:
                print(f"retry shoe {shoe_idx} post-processing failed: {e}, retrying...")
                continue

            print(f"[成功] 敏感局數={len(rounds)}，尾局={len(tail)} 張，覆蓋牌數={total_cards}/416，切牌命中敏感機率約 {len(starts)}/416 = {len(starts)/416:.2%}")

            marked = {r.cards[0].pos for r in rounds}
            if tail:
                marked.add(tail[0].pos)
            rows, avg_hit, avg_rounds = simulate_all_cuts(deck, marked, use_b_order=True, rounds=rounds, tail=tail)
            print(f"[切牌統計] 平均命張={avg_hit:.3f}，平均命前局={avg_rounds:.3f}")

            shoe_results.append(ShoeResult(shoe_index=shoe_idx, rounds=rounds, tail=tail, deck=deck))
            cut_stats.append(CutSimulationResult(shoe_index=shoe_idx, rows=rows, avg_hit=avg_hit, avg_rounds=avg_rounds))
            shoe_idx += 1
    except RuntimeError as e:
        print("[失敗]", e)
    else:
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        rounds_path = export_rounds(shoe_results, timestamp)
        vertical_path = export_vertical(shoe_results, timestamp)
        cut_path = export_cut_hits(cut_stats, timestamp)
        print(f"\n輸出：{os.path.abspath(rounds_path)}")
        print(f"輸出：{os.path.abspath(vertical_path)}")
        print(f"輸出：{os.path.abspath(cut_path)}")
        print(f"[完成] 共處理 {len(shoe_results)} 副牌。")
