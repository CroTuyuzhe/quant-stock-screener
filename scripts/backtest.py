#!/usr/bin/env python3
"""
智能多因子选股系统 - 回测模块
模拟历史月度调仓，计算策略收益 vs 基准

Usage: python3 backtest.py --strategies 1456 --market a --months 24 --top 50
"""

from __future__ import annotations

import argparse
import json
import sys
import os
import time
import numpy as np
import pandas as pd
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import get_stock_universe, fetch_daily_batch, _fetch_daily_tencent, _fetch_url
from factor_engine import (
    calc_valuation_factors, calc_momentum_factors,
    calc_lowvol_factors, calc_sentiment_factors,
    calc_growth_factors, calc_quality_factors,
    zscore_neutralize,
)
from scorer import compute_strategy_score, compute_composite_score, STRATEGY_NAMES

FACTOR_CALCULATORS = {
    1: ("低估值", calc_valuation_factors),
    2: ("成长性", calc_growth_factors),
    3: ("质量型", calc_quality_factors),
    4: ("动量", calc_momentum_factors),
    5: ("低波动", calc_lowvol_factors),
    6: ("情绪", calc_sentiment_factors),
}


def fetch_benchmark(months: int = 24) -> pd.DataFrame:
    """获取沪深300历史日线作为基准"""
    df = _fetch_daily_tencent("000300", "index", days=months * 30 + 60)
    if df is None or len(df) == 0:
        # 备选：上证指数
        df = _fetch_daily_tencent("000001", "index", days=months * 30 + 60)
    return df


def run_backtest(
    strategies: list[int],
    market: str = "a",
    top_n: int = 50,
    months: int = 24,
    rebal_day: int = 1,  # 每月第几个交易日调仓
) -> dict:
    """
    回测流程：
    1. 获取全市场日线数据（约5000只，需要分批）
    2. 获取基准（沪深300）
    3. 逐月回测：在每个调仓日，用截至该日的数据计算因子 → 选股 → 持有到下次调仓
    4. 汇总收益指标
    """
    print(f"[回测] 策略: {'+'.join(STRATEGY_NAMES[s] for s in strategies)}")
    print(f"[回测] 市场: {market.upper()} | Top {top_n} | {months}个月")
    print()
    
    # Step 1: 获取当前股票池（用于确定代码列表）
    print("[1/5] 获取股票池...")
    universe = get_stock_universe(market)
    
    # 过滤
    if "name" in universe.columns:
        universe = universe[~universe["name"].astype(str).str.contains("ST|退|N/A", na=False)]
    close_num = pd.to_numeric(universe.get("close", pd.Series()), errors="coerce")
    universe = universe[close_num > 0]
    if "code" in universe.columns:
        universe = universe.set_index("code")
    
    # 选市值前500只作为回测池（太大跑不完）
    mcap = pd.to_numeric(universe.get("market_cap", pd.Series()), errors="coerce")
    if mcap.notna().sum() > 500:
        universe = universe.loc[mcap.sort_values(ascending=False).head(500).index]
    
    codes = universe.index.tolist()
    print(f"   回测池: {len(codes)} 只（市值前1500）")
    
    # Step 2: 批量获取日线数据
    print("[2/5] 获取历史日线（批量）...")
    daily_data = _fetch_backtest_daily(codes, market, days=months * 22 + 60)
    print(f"   日线获取: {len(daily_data)}/{len(codes)} 只")
    
    # Step 3: 获取基准
    print("[3/5] 获取基准（沪深300）...")
    benchmark = fetch_benchmark(months)
    if benchmark is not None and len(benchmark) > 0:
        bench_close = benchmark["close"].values.astype(float)
        bench_dates = benchmark["date"].values if "date" in benchmark.columns else range(len(bench_close))
        print(f"   基准数据: {len(bench_close)} 天")
    else:
        bench_close = None
        bench_dates = None
        print("   [WARN] 基准数据获取失败")
    
    # Step 4: 确定调仓日期
    print("[4/5] 计算调仓日期...")
    # 使用第一只有足够数据的股票的日期作为交易日历
    sample_code = list(daily_data.keys())[0]
    sample_dates = daily_data[sample_code]["date"].values
    
    # 每月选取第N个交易日
    rebal_dates = _get_monthly_rebal_dates(sample_dates, rebal_day, months)
    print(f"   调仓次数: {len(rebal_dates)} 次")
    
    # Step 5: 逐月回测
    print("[5/5] 逐月回测...")
    portfolio_returns = []
    bench_returns = []
    rebal_log = []
    
    for i, rebal_date in enumerate(rebal_dates):
        if i >= len(rebal_dates) - 1:
            break
        
        next_date = rebal_dates[i + 1]
        
        # 用截至调仓日的数据计算因子
        try:
            selected = _select_stocks_at_date(
                codes, universe, daily_data, strategies,
                rebal_date, top_n,
            )
        except Exception as e:
            print(f"   [SKIP] {rebal_date}: {e}")
            continue
        
        if len(selected) == 0:
            continue
        
        # 计算持有期收益（等权）
        port_ret = _calc_portfolio_return(daily_data, selected, rebal_date, next_date)
        portfolio_returns.append(port_ret)
        
        # 基准收益
        bench_ret = _calc_bench_return(bench_close, bench_dates, rebal_date, next_date)
        bench_returns.append(bench_ret)
        
        # 超额
        excess = port_ret - bench_ret
        rebal_log.append({
            "date": str(rebal_date),
            "stocks": len(selected),
            "top3": selected[:3],
            "portfolio_return": round(port_ret * 100, 2),
            "benchmark_return": round(bench_ret * 100, 2),
            "excess_return": round(excess * 100, 2),
        })
        
        print(f"   {rebal_date} | 持仓{len(selected)}只 | "
              f"组合{port_ret*100:+.2f}% | 基准{bench_ret*100:+.2f}% | "
              f"超额{excess*100:+.2f}%")
    
    # 计算汇总指标
    metrics = _calc_metrics(portfolio_returns, bench_returns)
    
    return {
        "metrics": metrics,
        "rebal_log": rebal_log,
        "meta": {
            "strategies": [STRATEGY_NAMES[s] for s in strategies],
            "market": market.upper(),
            "top_n": top_n,
            "months": months,
            "rebal_count": len(rebal_log),
            "universe_size": len(codes),
        },
    }


def _fetch_backtest_daily(codes: list, market: str, days: int) -> dict:
    """批量获取回测日线"""
    result = {}
    batch_size = 50
    total = len(codes)
    
    for i in range(0, total, batch_size):
        batch = codes[i:i + batch_size]
        for code in batch:
            df = _fetch_daily_tencent(code, market, days)
            if df is not None and len(df) >= 60:
                result[code] = df
        
        done = min(i + batch_size, total)
        if done % 200 == 0:
            print(f"   日线进度: {done}/{total}")
        time.sleep(0.1)
    
    return result


def _get_monthly_rebal_dates(dates: np.ndarray, rebal_day: int, months: int) -> list:
    """从交易日序列中提取每月调仓日"""
    if len(dates) == 0:
        return []
    
    date_series = pd.to_datetime(dates)
    # date_series 是 DatetimeIndex，不能用 .dt
    periods = date_series.to_period("M")
    
    rebal_dates = []
    seen_months = set()
    
    for i, d in enumerate(date_series):
        p = periods[i]
        if p not in seen_months:
            seen_months.add(p)
            # 该月第N个交易日的索引
            month_mask = periods == p
            month_indices = np.where(month_mask)[0]
            if len(month_indices) >= rebal_day:
                rebal_idx = month_indices[rebal_day - 1]
                rebal_date = str(date_series[rebal_idx].date())
                # 只取最近N个月
                cutoff = date_series[-1] - pd.DateOffset(months=months)
                if date_series[rebal_idx] >= cutoff and date_series[rebal_idx] < date_series[-1]:
                    rebal_dates.append(rebal_date)
    
    return sorted(rebal_dates)


def _select_stocks_at_date(
    codes: list, universe: pd.DataFrame, daily_data: dict,
    strategies: list[int], date: str, top_n: int,
) -> list:
    """
    在指定日期，用截至该日的数据选股
    """
    # 构建截面数据
    snapshot = universe.copy()
    
    # 用历史数据计算因子
    # 只保留截至date的数据
    truncated_daily = {}
    for code, hist in daily_data.items():
        if "date" in hist.columns:
            mask = hist["date"] <= date
            truncated = hist[mask]
            if len(truncated) >= 20:
                truncated_daily[code] = truncated
    
    if len(truncated_daily) < 50:
        return []
    
    # 过滤 snapshot 到有日线数据的股票
    available_codes = list(truncated_daily.keys())
    snapshot = snapshot.loc[snapshot.index.isin(available_codes)]
    
    # 计算各策略得分
    strategy_scores = {}
    for sid in strategies:
        name, calculator = FACTOR_CALCULATORS[sid]
        try:
            if sid == 1:
                factor_df = calculator(snapshot)
            elif sid in (4, 5):
                factor_df = calculator(snapshot, daily_data=truncated_daily)
            else:
                factor_df = calculator(snapshot)
            
            if factor_df is not None and len(factor_df) > 0:
                score = compute_strategy_score(factor_df, sid)
                strategy_scores[sid] = score
        except Exception:
            continue
    
    if not strategy_scores:
        return []
    
    # 综合得分
    composite = compute_composite_score(strategy_scores)
    ranked = composite.sort_values(ascending=False)
    
    return ranked.head(top_n).index.tolist()


def _calc_portfolio_return(daily_data: dict, codes: list, start_date: str, end_date: str) -> float:
    """计算等权组合持有期收益"""
    returns = []
    for code in codes:
        hist = daily_data.get(code)
        if hist is None or "date" not in hist.columns:
            continue
        
        mask_start = hist["date"] == start_date
        mask_end = hist["date"] == end_date
        
        if mask_start.sum() == 0 or mask_end.sum() == 0:
            # 找最近的日期
            dates = hist["date"].values
            start_idx = np.where(dates <= start_date)[0]
            end_idx = np.where(dates <= end_date)[0]
            
            if len(start_idx) == 0 or len(end_idx) == 0:
                continue
            start_price = hist["close"].values[start_idx[-1]]
            end_price = hist["close"].values[end_idx[-1]]
        else:
            start_price = hist.loc[mask_start, "close"].values[0]
            end_price = hist.loc[mask_end, "close"].values[0]
        
        if start_price > 0:
            returns.append(end_price / start_price - 1)
    
    return np.mean(returns) if returns else 0.0


def _calc_bench_return(bench_close, bench_dates, start_date: str, end_date: str) -> float:
    """计算基准持有期收益"""
    if bench_close is None or bench_dates is None:
        return 0.0
    
    try:
        start_idx = np.where(bench_dates <= start_date)[0]
        end_idx = np.where(bench_dates <= end_date)[0]
        
        if len(start_idx) == 0 or len(end_idx) == 0:
            return 0.0
        
        s_price = bench_close[start_idx[-1]]
        e_price = bench_close[end_idx[-1]]
        
        return (e_price / s_price - 1) if s_price > 0 else 0.0
    except Exception:
        return 0.0


def _calc_metrics(portfolio_returns: list, bench_returns: list) -> dict:
    """计算回测指标"""
    if not portfolio_returns:
        return {"error": "无收益数据"}
    
    port = np.array(portfolio_returns)
    bench = np.array(bench_returns[:len(port)])
    excess = port - bench
    
    # 月度收益 → 年化
    n_months = len(port)
    cumulative = np.prod(1 + port)
    annual_ret = cumulative ** (12 / n_months) - 1 if n_months > 0 else 0
    
    bench_cumulative = np.prod(1 + bench) if len(bench) > 0 else 1
    bench_annual = bench_cumulative ** (12 / n_months) - 1 if n_months > 0 else 0
    
    # 波动率（年化）
    monthly_vol = np.std(port, ddof=1) if len(port) > 1 else 0
    annual_vol = monthly_vol * np.sqrt(12)
    
    # 夏普比率（假设无风险利率2.5%）
    rf_monthly = 0.025 / 12
    sharpe = (np.mean(port) - rf_monthly) / monthly_vol * np.sqrt(12) if monthly_vol > 0 else 0
    
    # 最大回撤（月度）
    cum_returns = np.cumprod(1 + port)
    peak = np.maximum.accumulate(cum_returns)
    drawdowns = (peak - cum_returns) / peak
    max_dd = np.max(drawdowns) if len(drawdowns) > 0 else 0
    
    # 胜率
    win_rate = np.sum(port > 0) / len(port) if len(port) > 0 else 0
    
    # 超额收益
    excess_cumulative = np.prod(1 + excess) if len(excess) > 0 else 1
    excess_annual = excess_cumulative ** (12 / n_months) - 1 if n_months > 0 else 0
    
    # 信息比率
    tracking_error = np.std(excess, ddof=1) * np.sqrt(12) if len(excess) > 1 else 0
    info_ratio = excess_annual / tracking_error if tracking_error > 0 else 0
    
    # Calmar比率
    calmar = annual_ret / max_dd if max_dd > 0 else 0
    
    return {
        "annual_return": round(annual_ret * 100, 2),
        "benchmark_annual_return": round(bench_annual * 100, 2),
        "excess_annual_return": round(excess_annual * 100, 2),
        "annual_volatility": round(annual_vol * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown": round(max_dd * 100, 2),
        "calmar_ratio": round(calmar, 3),
        "win_rate": round(win_rate * 100, 1),
        "info_ratio": round(info_ratio, 3),
        "total_months": n_months,
        "cumulative_return": round((cumulative - 1) * 100, 2),
        "benchmark_cumulative": round((bench_cumulative - 1) * 100, 2),
    }


def format_backtest_report(data: dict) -> str:
    """格式化回测报告"""
    m = data["metrics"]
    meta = data["meta"]
    
    lines = []
    lines.append("=" * 60)
    lines.append("📈 多因子策略回测报告")
    lines.append("=" * 60)
    lines.append(f"策略: {' + '.join(meta['strategies'])}")
    lines.append(f"市场: {meta['market']} | Top {meta['top_n']} | {meta['months']}个月")
    lines.append(f"调仓次数: {meta['rebal_count']} 次 | 回测池: {meta['universe_size']} 只")
    lines.append("")
    
    lines.append("📊 核心指标:")
    lines.append("-" * 40)
    lines.append(f"  策略年化收益:   {m.get('annual_return', 0):+.2f}%")
    lines.append(f"  基准年化收益:   {m.get('benchmark_annual_return', 0):+.2f}%")
    lines.append(f"  超额年化收益:   {m.get('excess_annual_return', 0):+.2f}%")
    lines.append(f"  累计收益:       {m.get('cumulative_return', 0):+.2f}%")
    lines.append(f"  基准累计收益:   {m.get('benchmark_cumulative', 0):+.2f}%")
    lines.append("")
    lines.append(f"  年化波动率:     {m.get('annual_volatility', 0):.2f}%")
    lines.append(f"  最大回撤:       {m.get('max_drawdown', 0):.2f}%")
    lines.append(f"  夏普比率:       {m.get('sharpe_ratio', 0):.3f}")
    lines.append(f"  Calmar比率:     {m.get('calmar_ratio', 0):.3f}")
    lines.append(f"  信息比率:       {m.get('info_ratio', 0):.3f}")
    lines.append(f"  月度胜率:       {m.get('win_rate', 0):.1f}%")
    lines.append("-" * 40)
    
    # 月度明细
    lines.append("")
    lines.append("📋 月度调仓明细:")
    lines.append(f"{'日期':<12} {'持仓':<5} {'组合':<10} {'基准':<10} {'超额':<10}")
    lines.append("-" * 50)
    for log in data.get("rebal_log", [])[-12:]:  # 最近12个月
        lines.append(
            f"{log['date']:<12} {log['stocks']:<5} "
            f"{log['portfolio_return']:>+.2f}%    "
            f"{log['benchmark_return']:>+.2f}%    "
            f"{log['excess_return']:>+.2f}%"
        )
    
    if len(data.get("rebal_log", [])) > 12:
        lines.append(f"... 共 {len(data['rebal_log'])} 期")
    
    lines.append("")
    lines.append("⚠️ 回测不代表未来表现，仅供研究参考")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="多因子策略回测")
    parser.add_argument("--strategies", "-s", type=str, required=True)
    parser.add_argument("--market", "-m", type=str, default="a")
    parser.add_argument("--top", "-t", type=int, default=50)
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--format", "-f", type=str, default="text", choices=["json", "text"])
    
    args = parser.parse_args()
    strategies = [int(c) for c in args.strategies if c in "123456"]
    
    if not strategies:
        print("错误: 请至少选择一个有效策略")
        sys.exit(1)
    
    t0 = time.time()
    result = run_backtest(strategies, args.market, args.top, args.months)
    elapsed = time.time() - t0
    
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_backtest_report(result))
    
    print(f"\n⏱️ 耗时: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
