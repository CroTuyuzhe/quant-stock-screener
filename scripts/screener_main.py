#!/usr/bin/env python3
"""
智能多因子选股系统 - 主入口（两阶段筛选版）
Stage 1: 粗筛（行情快照，全市场）→ 保留 Top 500
Stage 2: 精算（日线 + 财务数据，逐只）→ 输出 Top 80

Usage: python3 screener_main.py --strategies 234 --market a --top 80 --format json
"""

from __future__ import annotations

import argparse
import json
import sys
import os
import time
import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings("ignore")

# 支持从任意目录运行
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from data_fetcher import (
    get_stock_universe,
    fetch_daily_batch,
    fetch_financial_batch,
    fetch_limit_up_batch,
    fetch_limit_down_batch,
)
from factor_engine import (
    calc_valuation_factors,
    calc_growth_factors,
    calc_quality_factors,
    calc_momentum_factors,
    calc_lowvol_factors,
    calc_sentiment_factors,
    zscore_neutralize,
    parse_financial_row,
)
from scorer import (
    compute_strategy_score,
    compute_composite_score,
    rank_stocks,
    STRATEGY_NAMES,
)

FACTOR_CALCULATORS = {
    1: ("低估值", calc_valuation_factors),      # financials optional (enhanced with)
    2: ("成长性", calc_growth_factors),          # needs financials
    3: ("质量型", calc_quality_factors),          # needs financials
    4: ("动量", calc_momentum_factors),           # needs daily
    5: ("低波动", calc_lowvol_factors),           # needs daily
    6: ("情绪", calc_sentiment_factors),          # needs daily + limit data
}


# ============================================================
# 粗筛：用行情快照做第一轮过滤
# ============================================================

def coarse_filter(
    df: pd.DataFrame,
    strategies: list[int],
    top_n: int = 500,
) -> pd.DataFrame:
    """
    第一轮粗筛：用行情快照中的可用数据做简单打分
    目标：从 5000+ 只缩到 500 只左右
    """
    scores = pd.Series(0.0, index=df.index)
    n_strategies = 0
    
    # 低估值粗筛
    if 1 in strategies:
        pe = pd.to_numeric(df.get("pe", pd.Series(index=df.index, dtype=float)), errors="coerce")
        pb = pd.to_numeric(df.get("pb", pd.Series(index=df.index, dtype=float)), errors="coerce")
        mcap = pd.to_numeric(df.get("market_cap", pd.Series(index=df.index, dtype=float)), errors="coerce")
        s = pd.Series(0.0, index=df.index)
        s += zscore_neutralize(safe_div_q(1.0, pe))
        s += zscore_neutralize(safe_div_q(1.0, pb))
        # 市销率粗筛：大市值 + 低PE → 可能低PS
        if mcap.notna().sum() > 0:
            s += zscore_neutralize(np.log1p(mcap.fillna(0) / 1e8))
        scores += s
        n_strategies += 1
    
    # 成长性粗筛（用涨跌幅代理：近期涨势好可能有业绩支撑）
    if 2 in strategies:
        ret60 = pd.to_numeric(df.get("ret_60d", pd.Series(index=df.index, dtype=float)), errors="coerce")
        scores += zscore_neutralize(ret60.fillna(0))
        n_strategies += 1
    
    # 质量粗筛（用PE倒数 × 市值代理：合理估值 + 大市值 = 更可能高质量）
    if 3 in strategies:
        mcap = pd.to_numeric(df.get("market_cap", pd.Series(index=df.index, dtype=float)), errors="coerce")
        pe = pd.to_numeric(df.get("pe", pd.Series(index=df.index, dtype=float)), errors="coerce")
        quality_proxy = safe_div_q(1.0, pe) * np.log1p(mcap.fillna(0) / 1e8)
        scores += zscore_neutralize(quality_proxy)
        n_strategies += 1
    
    # 动量粗筛（用60日涨跌幅）
    if 4 in strategies:
        ret60 = pd.to_numeric(df.get("ret_60d", pd.Series(index=df.index, dtype=float)), errors="coerce")
        scores += zscore_neutralize(ret60.fillna(0))
        n_strategies += 1
    
    # 低波动粗筛（用涨跌幅绝对值的倒数）
    if 5 in strategies:
        pct = pd.to_numeric(df.get("pct_chg", pd.Series(index=df.index, dtype=float)), errors="coerce")
        scores += zscore_neutralize(-pct.abs().fillna(0))
        n_strategies += 1
    
    # 情绪粗筛（用换手率 + 成交额 + 量比综合）
    if 6 in strategies:
        turnover = pd.to_numeric(df.get("turnover_rate", pd.Series(index=df.index, dtype=float)), errors="coerce")
        amount = pd.to_numeric(df.get("amount", pd.Series(index=df.index, dtype=float)), errors="coerce")
        vol_ratio = pd.to_numeric(df.get("volume_ratio", pd.Series(index=df.index, dtype=float)), errors="coerce")
        s = pd.Series(0.0, index=df.index)
        s += zscore_neutralize(np.log1p(turnover.fillna(0)))
        s += zscore_neutralize(np.log1p(amount.fillna(0)))
        if vol_ratio.notna().sum() > 10:
            s += zscore_neutralize(np.log1p(vol_ratio.fillna(0)))
        scores += s
        n_strategies += 1
    
    if n_strategies > 0:
        scores = scores / n_strategies
    
    # 排序，取前 top_n
    filtered = df.loc[scores.sort_values(ascending=False).head(top_n).index]
    
    return filtered


def safe_div_q(a, b):
    """pandas 版安全除法"""
    return a / b.replace(0, np.nan)


# ============================================================
# 财务数据解析
# ============================================================

def enrich_with_financials(
    codes: list[str],
) -> dict:
    """逐只获取并解析财务数据"""
    print("[2b/5] 获取财务数据（逐只，约500只）...")
    
    raw_financials = fetch_financial_batch(codes, batch_sleep=0.3)
    
    # 解析为统一格式
    parsed = {}
    for code, df in raw_financials.items():
        parsed[code] = parse_financial_row(df)
    
    print(f"   财务数据获取: {len(parsed)}/{len(codes)} 只成功")
    return parsed


# ============================================================
# 主流程
# ============================================================

def run_screener(
    strategies: list[int],
    market: str = "a",
    top_n: int = 80,
    coarse_top: int = 500,
) -> dict:
    """
    两阶段选股流程
    """
    # ========== Stage 0: 获取全市场行情 ==========
    print(f"[1/5] 获取行情快照 ({market.upper()})...")
    universe = get_stock_universe(market)
    
    # 过滤 ST/退市/停牌/无价格
    if "name" in universe.columns:
        mask = ~universe["name"].astype(str).str.contains("ST|退|N/A", na=False)
        universe = universe[mask]
    close_num = pd.to_numeric(universe.get("close", pd.Series()), errors="coerce")
    universe = universe[close_num > 0]
    
    if "code" in universe.columns:
        universe = universe.set_index("code")
    
    print(f"   全市场: {len(universe)} 只")
    
    # ========== Stage 1: 粗筛 ==========
    print(f"[2/5] 粗筛 → Top {coarse_top}...")
    filtered = coarse_filter(universe, strategies, coarse_top)
    print(f"   粗筛后: {len(filtered)} 只")
    
    # ========== Stage 2: 获取精细数据 ==========
    # 数据需求分析
    needs_daily = any(s in (4, 5, 6) for s in strategies)  # 动量、低波动、情绪都需要日线
    needs_financial = any(s in (1, 2, 3) for s in strategies)  # 估值(增强)、成长、质量需要财务
    needs_limit = 6 in strategies  # 情绪需要涨跌停数据
    
    codes_list = filtered.index.tolist()
    daily_data = None
    financials = None
    limit_up = None
    limit_down = None
    
    # 获取日线数据（用于动量、低波动、情绪）
    if needs_daily:
        print("[3/5] 获取日线数据（逐只）...")
        daily_data = fetch_daily_batch(codes_list, market=market.upper() if market != "both" else "A", days=500, batch_sleep=0.2)
        print(f"   日线获取: {len(daily_data)}/{len(codes_list)} 只成功")
    else:
        print("[3/5] 跳过日线获取（所选策略不需要）")
    
    # 获取财务数据（用于低估值增强、成长性、质量）
    if needs_financial:
        financials = enrich_with_financials(codes_list)
    else:
        print("[3b/5] 跳过财务获取（所选策略不需要）")
    
    # 获取涨跌停数据（用于情绪）
    if needs_limit:
        print("[3c/5] 获取涨跌停数据（近20个交易日）...")
        limit_up = fetch_limit_up_batch(days=20, sleep_sec=0.3)
        limit_down = fetch_limit_down_batch(days=20, sleep_sec=0.3)
        print(f"   涨停记录: {len(limit_up)} 只 | 跌停记录: {len(limit_down)} 只")
    
    # ========== Stage 3: 计算因子 ==========
    print("[4/5] 计算因子打分...")
    strategy_scores = {}
    factor_details = {}
    
    for sid in strategies:
        name, calculator = FACTOR_CALCULATORS[sid]
        print(f"   计算 {name} 因子...")
        
        # 根据策略类型传入对应数据
        kwargs = {}
        if sid == 1 and financials is not None:
            kwargs["financials"] = financials
        if sid in (2, 3) and financials is not None:
            kwargs["financials"] = financials
        if sid in (4, 5) and daily_data is not None:
            kwargs["daily_data"] = daily_data
        if sid == 6:
            if daily_data is not None:
                kwargs["daily_data"] = daily_data
            if limit_up is not None:
                kwargs["limit_up_counts"] = limit_up
            if limit_down is not None:
                kwargs["limit_down_counts"] = limit_down
        
        factor_df = calculator(filtered, **kwargs)
        
        score = compute_strategy_score(factor_df, sid)
        strategy_scores[sid] = score
        factor_details[sid] = factor_df.columns.tolist()
    
    # ========== Stage 4: 综合得分 ==========
    print("[5/5] 综合打分 + 排名...")
    composite = compute_composite_score(strategy_scores)
    
    # 排名
    ranked = rank_stocks(composite, filtered.reset_index(), top_n)
    
    # 附加各策略得分
    for sid, score in strategy_scores.items():
        col_name = f"s{sid}"
        score_map = score.to_dict()
        ranked[col_name] = ranked["code"].map(
            lambda c: round(float(score_map.get(str(c), score_map.get(c, 0))), 3)
        )
    
    # 构建输出
    output = {
        "stocks": ranked.to_dict(orient="records"),
        "strategy_weights": {
            STRATEGY_NAMES[sid]: round(1.0 / len(strategies), 3)
            for sid in strategies
        },
        "factors_used": {
            STRATEGY_NAMES[sid]: cols
            for sid, cols in factor_details.items()
        },
        "meta": {
            "total_universe": len(universe),
            "after_coarse_filter": len(filtered),
            "market": market.upper(),
            "strategies": [STRATEGY_NAMES[sid] for sid in strategies],
            "top_n": top_n,
        },
    }
    
    return output


def format_report(data: dict) -> str:
    """格式化为可读报告"""
    meta = data["meta"]
    lines = []
    lines.append("=" * 60)
    lines.append("🎯 智能多因子选股报告")
    lines.append("=" * 60)
    lines.append(f"市场: {meta['market']}")
    lines.append(f"策略组合: {' + '.join(meta['strategies'])}")
    lines.append(f"选股池: {meta['total_universe']} 只 → 粗筛 {meta['after_coarse_filter']} → Top {meta['top_n']}")
    lines.append("")
    
    # 使用的因子
    lines.append("📊 因子明细:")
    for strategy, factors in data.get("factors_used", {}).items():
        lines.append(f"  [{strategy}] {', '.join(factors)}")
    lines.append("")
    
    # 权重
    lines.append("⚖️ 策略权重:")
    for name, w in data["strategy_weights"].items():
        lines.append(f"  {name}: {w * 100:.0f}%")
    lines.append("")
    
    # Top 结果
    stocks = data["stocks"]
    lines.append(f"🏆 Top {min(30, len(stocks))} 选股结果:")
    lines.append("-" * 60)
    lines.append(f"{'排名':<4} {'代码':<8} {'名称':<10} {'得分':<8}")
    lines.append("-" * 60)
    
    for stock in stocks[:30]:
        rank = stock.get("rank", "")
        code = str(stock.get("code", ""))
        name = str(stock.get("name", ""))[:8]
        score = stock.get("composite_score", 0)
        lines.append(f"{rank:<4} {code:<8} {name:<10} {score:<8}")
    
    lines.append("-" * 60)
    if len(stocks) > 30:
        lines.append(f"... 共 {len(stocks)} 只（完整结果见 JSON）")
    
    lines.append("")
    lines.append("⚠️ 仅供研究参考，非投资建议。数据来源: akshare")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="智能多因子选股系统 v2")
    parser.add_argument("--strategies", "-s", type=str, required=True,
                        help="策略组合，如 234")
    parser.add_argument("--market", "-m", type=str, default="a",
                        choices=["a", "hk", "both"],
                        help="市场: a=A股, hk=港股, both=两者")
    parser.add_argument("--top", "-t", type=int, default=80,
                        help="输出前N只股票")
    parser.add_argument("--coarse", "-c", type=int, default=500,
                        help="粗筛保留数量")
    parser.add_argument("--format", "-f", type=str, default="json",
                        choices=["json", "text"],
                        help="输出格式")
    
    args = parser.parse_args()
    
    strategies = [int(c) for c in args.strategies if c in "123456"]
    if not strategies:
        print("错误: 请至少选择一个有效策略 (1-6)")
        sys.exit(1)
    
    print(f"🎯 选股策略: {' + '.join([STRATEGY_NAMES[s] for s in strategies])}")
    print(f"   市场: {args.market.upper()}")
    print()
    
    t0 = time.time()
    result = run_screener(strategies, args.market, args.top, args.coarse)
    elapsed = time.time() - t0
    
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_report(result))
    
    print(f"\n⏱️ 耗时: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
