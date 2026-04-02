"""
智能多因子选股系统 - 因子计算模块
6大策略因子计算（优化版：支持真实财务数据 + 日线数据）
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Literal, Dict, Optional


# ============================================================
# 通用工具
# ============================================================

def zscore_neutralize(
    series: pd.Series,
    industry: pd.Series = None,
    winsorize_pct: float = 0.025,
) -> pd.Series:
    """缩尾 + 行业中性 + z-score 标准化"""
    s = series.copy().astype(float)
    
    # 缩尾处理（去除极端值）
    if winsorize_pct > 0:
        lo, hi = s.quantile(winsorize_pct), s.quantile(1 - winsorize_pct)
        s = s.clip(lo, hi)
    
    # 行业内标准化
    if industry is not None and industry.nunique() > 1:
        for grp, idx in s.groupby(industry).groups.items():
            vals = s.loc[idx]
            if vals.std() > 1e-8:
                s.loc[idx] = (vals - vals.mean()) / vals.std()
    
    # 全局标准化
    if s.std() > 1e-8:
        s = (s - s.mean()) / s.std()
    
    return s.clip(-3, 3)


def safe_div(a, b):
    """安全除法（避免除零）"""
    return a / b.replace(0, np.nan)


def parse_financial_row(df: pd.DataFrame) -> dict:
    """
    从 akshare 财务指标 DataFrame 提取关键指标
    兼容 stock_financial_abstract_ths 和 stock_financial_analysis_indicator
    """
    result = {}
    if df is None or len(df) == 0:
        return result
    
    # 取最新一期数据
    latest = df.iloc[0]
    col_names = [str(c) for c in df.columns]
    
    # 动态匹配列名
    def find_col(keywords):
        for kw in keywords:
            for c in col_names:
                if kw in c:
                    return c
        return None
    
    # 营收增长率
    col = find_col(["营业收入增长率", "营收增长率", "主营业务收入增长率", "收入增长率"])
    if col:
        try:
            result["rev_growth"] = float(latest[col])
        except (ValueError, TypeError):
            result["rev_growth"] = 0.0
    
    # 净利润增长率
    col = find_col(["净利润增长率", "归母净利润增长率", "归属净利润增长率", "净利润同比"])
    if col:
        try:
            result["profit_growth"] = float(latest[col])
        except (ValueError, TypeError):
            result["profit_growth"] = 0.0
    
    # 净资产收益率
    col = find_col(["净资产收益率", "ROE", "加权净资产收益率"])
    if col:
        try:
            result["roe"] = float(latest[col])
        except (ValueError, TypeError):
            result["roe"] = 0.0
    
    # 资产负债率
    col = find_col(["资产负债率", "负债率"])
    if col:
        try:
            result["debt_ratio"] = float(latest[col])
        except (ValueError, TypeError):
            result["debt_ratio"] = 50.0
    
    # 毛利率
    col = find_col(["毛利率", "销售毛利率", "主营毛利率"])
    if col:
        try:
            result["gross_margin"] = float(latest[col])
        except (ValueError, TypeError):
            result["gross_margin"] = 0.0
    
    # 净利润
    col = find_col(["净利润", "归母净利润"])
    if col:
        try:
            result["net_profit"] = float(latest[col])
        except (ValueError, TypeError):
            result["net_profit"] = 0.0
    
    # 每股收益（EPS）
    col = find_col(["每股收益", "基本每股收益", "EPS"])
    if col:
        try:
            result["eps"] = float(latest[col])
        except (ValueError, TypeError):
            result["eps"] = 0.0
    
    # EPS增长率（用于PEG计算）
    col = find_col(["每股收益增长率", "EPS增长率", "每股收益同比"])
    if col:
        try:
            result["eps_growth"] = float(latest[col])
        except (ValueError, TypeError):
            result["eps_growth"] = 0.0
    
    # 每股分红
    col = find_col(["每股分红", "每股派息", "分红", "派息"])
    if col:
        try:
            result["dividend_per_share"] = float(latest[col])
        except (ValueError, TypeError):
            result["dividend_per_share"] = 0.0
    
    # 总资产（用于应计比率）
    col = find_col(["总资产", "资产总计"])
    if col:
        try:
            result["total_assets"] = float(latest[col])
        except (ValueError, TypeError):
            result["total_assets"] = 0.0
    
    # 经营现金流净额
    col = find_col(["经营现金流净额", "经营活动现金流", "经营性现金流"])
    if col:
        try:
            result["cfo"] = float(latest[col])
        except (ValueError, TypeError):
            result["cfo"] = 0.0
    
    # 营业收入
    col = find_col(["营业总收入", "营业收入", "主营收入"])
    if col:
        try:
            result["revenue"] = float(latest[col])
        except (ValueError, TypeError):
            result["revenue"] = 0.0
    
    # 净利润
    col = find_col(["净利润", "归母净利润"])
    if col:
        try:
            result["net_profit"] = float(latest[col])
        except (ValueError, TypeError):
            result["net_profit"] = 0.0
    
    return result


# ============================================================
# 策略1: 低估值因子（优化版）
# ============================================================

def calc_valuation_factors(
    df: pd.DataFrame,
    financials: Optional[Dict[str, dict]] = None,
) -> pd.DataFrame:
    """
    低估值因子（6个）：
    EP(1/PE), BP(1/PB), PS(1/市销率), PEG, DY(股息率), PE_cross_rank(PE截面分位)
    """
    result = pd.DataFrame(index=df.index)
    
    pe = pd.to_numeric(df.get("pe", pd.Series(index=df.index, dtype=float)), errors="coerce")
    pb = pd.to_numeric(df.get("pb", pd.Series(index=df.index, dtype=float)), errors="coerce")
    mcap = pd.to_numeric(df.get("market_cap", pd.Series(index=df.index, dtype=float)), errors="coerce")
    
    # === EP = 1/PE ===
    result["EP"] = safe_div(1.0, pe)
    
    # === BP = 1/PB ===
    result["BP"] = safe_div(1.0, pb)
    
    # === PS = 市值 / 营收 → 1/PS（市销率越低越好）===
    if financials is not None:
        revenues = []
        for code in df.index:
            fin = financials.get(code, {})
            rev = fin.get("revenue", 0.0)
            revenues.append(rev)
        rev_series = pd.Series(revenues, index=df.index)
        if rev_series.abs().sum() > 0 and mcap.notna().sum() > 0:
            # PS = 市值 / 营收 → EP_reverse = 营收 / 市值
            result["PS_inv"] = safe_div(rev_series.replace(0, np.nan), mcap)
        else:
            result["PS_inv"] = pd.Series(0.0, index=df.index)
    else:
        result["PS_inv"] = pd.Series(0.0, index=df.index)
    
    # === PEG = PE / EPS增长率 → 1/PEG（越低越好 → 取倒数）===
    if financials is not None:
        pegs = []
        for code in df.index:
            fin = financials.get(code, {})
            eps_g = fin.get("eps_growth", 0.0)
            stock_pe = pe.get(code, np.nan) if code in pe.index else np.nan
            if not pd.isna(stock_pe) and eps_g > 0:
                peg = stock_pe / eps_g
                pegs.append(1.0 / peg if peg > 0 else 0)
            else:
                pegs.append(0.0)
        result["PEG_inv"] = pd.Series(pegs, index=df.index)
    else:
        result["PEG_inv"] = pd.Series(0.0, index=df.index)
    
    # === 股息率 DY ===
    if financials is not None:
        dys = []
        for code in df.index:
            fin = financials.get(code, {})
            dps = fin.get("dividend_per_share", 0.0)
            if dps > 0:
                # 股息率 = 每股分红 / 股价
                close_price = pd.to_numeric(df.loc[code].get("close", 0), errors="coerce")
                if close_price and close_price > 0:
                    dys.append(dps / close_price * 100)
                else:
                    dys.append(0.0)
            else:
                dys.append(0.0)
        result["DY"] = pd.Series(dys, index=df.index)
    else:
        # 降级：PE倒数 × 市值做粗略代理
        if mcap.notna().sum() > 0 and pe.notna().sum() > 0:
            result["DY_proxy"] = safe_div(1.0, pe) * np.log1p(mcap / 1e8)
        else:
            result["DY_proxy"] = pd.Series(0.0, index=df.index)
    
    # === PE截面分位数（行业内PE相对排名）===
    if pe.notna().sum() > 20:
        # 百分位排名（0=最便宜，1=最贵）→ 取反（低PE=高分）
        pe_rank = pe.rank(pct=True, na_option="keep")
        result["PE_cross_rank"] = -(pe_rank - 0.5)  # 中心化
    else:
        result["PE_cross_rank"] = pd.Series(0.0, index=df.index)
    
    for col in result.columns:
        result[col] = zscore_neutralize(result[col])
    
    return result


# ============================================================
# 策略2: 成长性因子（优化版）
# ============================================================

def calc_growth_factors(
    df: pd.DataFrame,
    financials: Optional[Dict[str, dict]] = None,
) -> pd.DataFrame:
    """
    成长性因子：
    营收增长率、净利润增长率、连续增长季数、盈利加速
    financials: {code: {"rev_growth": x, "profit_growth": x, ...}}
    """
    result = pd.DataFrame(index=df.index)
    
    rev_growths = []
    profit_growths = []
    consistency = []
    earn_accel = []
    
    for code in df.index:
        fin = financials.get(code, {}) if financials else {}
        
        rg = fin.get("rev_growth", 0.0)
        pg = fin.get("profit_growth", 0.0)
        
        rev_growths.append(rg)
        profit_growths.append(pg)
        
        # 连续增长信号：营收和净利润同时正增长 → 一致性=1
        if rg > 0 and pg > 0:
            consistency.append(1.0)
        elif rg > 0 or pg > 0:
            consistency.append(0.5)
        else:
            consistency.append(0.0)
        
        # 盈利加速：净利润增速 > 营收增速 → 盈利改善
        if pg > rg:
            earn_accel.append(1.0)
        else:
            earn_accel.append(0.0)
    
    result["rev_growth"] = pd.Series(rev_growths, index=df.index)
    result["profit_growth"] = pd.Series(profit_growths, index=df.index)
    result["consistency"] = pd.Series(consistency, index=df.index)
    result["earn_accel"] = pd.Series(earn_accel, index=df.index)
    
    for col in result.columns:
        result[col] = zscore_neutralize(result[col])
    
    return result


# ============================================================
# 策略3: 质量型因子（优化版）
# ============================================================

def calc_quality_factors(
    df: pd.DataFrame,
    financials: Optional[Dict[str, dict]] = None,
) -> pd.DataFrame:
    """
    质量因子：
    高ROE、低负债率、现金流好、高毛利率、低应计
    """
    result = pd.DataFrame(index=df.index)
    
    roes = []
    debt_scores = []
    cashflow_scores = []
    gross_margins = []
    
    for code in df.index:
        fin = financials.get(code, {}) if financials else {}
        
        # ROE
        roe = fin.get("roe", 0.0)
        roes.append(roe)
        
        # 负债率（越低越好 → 取反）
        debt = fin.get("debt_ratio", 50.0)
        debt_scores.append(-debt)
        
        # 现金流质量：经营现金流 / 净利润（>1 说明盈利有现金支撑）
        cfo = fin.get("cfo", 0.0)
        net_profit = fin.get("net_profit", 0.0)
        if abs(net_profit) > 1e6:
            cf_ratio = cfo / net_profit
            # 限制在合理范围
            cashflow_scores.append(min(max(cf_ratio, -2), 3))
        else:
            cashflow_scores.append(0.0)
        
        # 毛利率
        gm = fin.get("gross_margin", 0.0)
        gross_margins.append(gm)
    
    result["ROE"] = pd.Series(roes, index=df.index)
    result["debt_score"] = pd.Series(debt_scores, index=df.index)
    result["cashflow_quality"] = pd.Series(cashflow_scores, index=df.index)
    result["gross_margin"] = pd.Series(gross_margins, index=df.index)
    
    for col in result.columns:
        result[col] = zscore_neutralize(result[col])
    
    return result


# ============================================================
# 策略4: 动量因子（优化版）
# ============================================================

def calc_momentum_factors(
    df: pd.DataFrame,
    daily_data: Optional[Dict[str, pd.DataFrame]] = None,
) -> pd.DataFrame:
    """
    动量因子：
    中期动量（剔除最近1个月）、趋势强度、成交量动量
    
    核心逻辑：取 (t-60, t-20) 的收益率作为动量信号
    剔除最近20个交易日（约1个月）避免短期反转
    """
    result = pd.DataFrame(index=df.index)
    
    mom_3m_skip1 = []  # 3个月动量剔除1月
    mom_6m_skip1 = []  # 6个月动量剔除1月
    mom_12m_skip1 = []  # 12个月动量剔除1月
    trend_strength = []
    vol_momentum = []  # 量价配合
    
    for code in df.index:
        hist = daily_data.get(code) if daily_data else None
        
        if hist is None or len(hist) < 20:
            # 降级：用行情快照的 ret_60d 近似
            ret60 = pd.to_numeric(df.loc[code].get("ret_60d", 0), errors="coerce")
            mom_3m_skip1.append(float(ret60) if not pd.isna(ret60) else 0)
            mom_6m_skip1.append(0)
            mom_12m_skip1.append(0)
            trend_strength.append(0)
            vol_momentum.append(0)
            continue
        
        close = hist["close"].values.astype(float)
        n = len(close)
        
        # 3个月动量（约60个交易日），剔除最近20天
        if n >= 60:
            m3 = (close[-20] / close[-60] - 1) * 100
        else:
            m3 = (close[-20] / close[0] - 1) * 100 if n >= 20 else 0
        mom_3m_skip1.append(m3)
        
        # 6个月动量（约120个交易日），剔除最近20天
        if n >= 120:
            m6 = (close[-20] / close[-120] - 1) * 100
        else:
            m6 = (close[-20] / close[0] - 1) * 100 if n >= 20 else 0
        mom_6m_skip1.append(m6)
        
        # 12个月动量（约240个交易日），剔除最近20天
        if n >= 240:
            m12 = (close[-20] / close[-240] - 1) * 100
        else:
            m12 = (close[-20] / close[0] - 1) * 100 if n >= 20 else 0
        mom_12m_skip1.append(m12)
        
        # 趋势强度 = (MA20 - MA60) / MA60 × 100
        ma20 = np.mean(close[-20:]) if n >= 20 else close[-1]
        ma60 = np.mean(close[-60:]) if n >= 60 else close[0]
        trend = (ma20 - ma60) / ma60 * 100 if ma60 > 0 else 0
        trend_strength.append(trend)
        
        # 量价配合：近5日均量 / 20日均量 × 价格方向
        if "volume" in hist.columns:
            vol = hist["volume"].values.astype(float)
            if n >= 20:
                avg_vol_5 = np.mean(vol[-5:])
                avg_vol_20 = np.mean(vol[-20:])
                vol_ratio = avg_vol_5 / avg_vol_20 if avg_vol_20 > 0 else 1
                price_direction = np.sign(close[-1] / close[-5] - 1) if len(close) >= 5 else 0
                vol_momentum.append(vol_ratio * price_direction)
            else:
                vol_momentum.append(0)
        else:
            vol_momentum.append(0)
    
    result["mom_3m_skip1"] = pd.Series(mom_3m_skip1, index=df.index)
    result["mom_6m_skip1"] = pd.Series(mom_6m_skip1, index=df.index)
    result["mom_12m_skip1"] = pd.Series(mom_12m_skip1, index=df.index)
    result["trend_strength"] = pd.Series(trend_strength, index=df.index)
    result["vol_momentum"] = pd.Series(vol_momentum, index=df.index)
    
    for col in result.columns:
        result[col] = zscore_neutralize(result[col])
    
    return result


# ============================================================
# 策略5: 低波动因子（优化版）
# ============================================================

def calc_lowvol_factors(
    df: pd.DataFrame,
    daily_data: Optional[Dict[str, pd.DataFrame]] = None,
) -> pd.DataFrame:
    """
    低波动因子（6个）：
    年化波动率、下行偏差、Sortino代理、VaR(5%)、偏度(尾部风险)、波动率截面分位
    """
    result = pd.DataFrame(index=df.index)
    
    vols = []
    down_devs = []
    sortino_proxys = []
    vars_5pct = []
    skewnesses = []
    vol_pct_ranks = []
    
    # 先收集所有波动率（用于截面排名）
    raw_vols = {}
    
    for code in df.index:
        hist = daily_data.get(code) if daily_data else None
        
        if hist is None or len(hist) < 20:
            pct = pd.to_numeric(df.loc[code].get("pct_chg", 0), errors="coerce")
            vols.append(-abs(float(pct)) if not pd.isna(pct) else 0)
            down_devs.append(0)
            sortino_proxys.append(0)
            vars_5pct.append(0)
            skewnesses.append(0)
            raw_vols[code] = 0
            continue
        
        close = hist["close"].values.astype(float)
        rets = np.diff(np.log(close))
        n = len(rets)
        
        # === 年化波动率（60日）===
        lookback = min(n, 60)
        vol = np.std(rets[-lookback:]) * np.sqrt(252) * 100
        vols.append(-vol)  # 负号：低波动=高分
        raw_vols[code] = vol
        
        # === 下行偏差（Downside Deviation）===
        # 只算负收益的标准差（比波动率更能捕捉真正的风险）
        neg_rets = rets[rets < 0]
        if len(neg_rets) >= 10:
            lookback_neg = min(len(neg_rets), 60)
            down_dev = np.std(neg_rets[-lookback_neg:]) * np.sqrt(252) * 100
        else:
            down_dev = vol * 0.6  # 没有足够负收益 → 近似
        down_devs.append(-down_dev)
        
        # === Sortino 近似 = 均值收益 / 下行偏差 ===
        mean_ret = np.mean(rets[-lookback:]) * 252 * 100  # 年化
        if down_dev > 0.1:
            sortino = mean_ret / down_dev
            sortino_proxys.append(min(max(sortino, -3), 3))
        else:
            sortino_proxys.append(0)
        
        # === VaR 5% (历史模拟法) ===
        if lookback >= 20:
            var_5 = np.percentile(rets[-lookback:], 5) * 100  # 日VaR(%)
            vars_5pct.append(-abs(var_5))  # VaR越大(负)风险越高→取反
        else:
            vars_5pct.append(0)
        
        # === 偏度（Skewness）===
        # 负偏度 = 左尾更重 = 尾部风险更高
        if lookback >= 30:
            skew = _skewness(rets[-lookback:])
            skewnesses.append(-skew)  # 负偏度越大→风险越高→取反=正分
        else:
            skewnesses.append(0)
    
    # === 波动率截面分位 ===
    vol_series = pd.Series(raw_vols, index=df.index)
    if vol_series.notna().sum() > 20:
        vol_rank = vol_series.rank(pct=True, na_option="keep")
        vol_pct_ranks = (-(vol_rank - 0.5)).tolist()  # 低波动=高分
    else:
        vol_pct_ranks = [0.0] * len(df)
    
    result["vol_60d"] = pd.Series(vols, index=df.index)
    result["downside_dev"] = pd.Series(down_devs, index=df.index)
    result["sortino_proxy"] = pd.Series(sortino_proxys, index=df.index)
    result["VaR_5pct"] = pd.Series(vars_5pct, index=df.index)
    result["skewness"] = pd.Series(skewnesses, index=df.index)
    result["vol_pct_rank"] = pd.Series(vol_pct_ranks, index=df.index)
    
    for col in result.columns:
        result[col] = zscore_neutralize(result[col])
    
    return result


def _skewness(x: np.ndarray) -> float:
    """计算偏度"""
    n = len(x)
    if n < 3:
        return 0.0
    mean = np.mean(x)
    std = np.std(x, ddof=1)
    if std < 1e-12:
        return 0.0
    return np.mean(((x - mean) / std) ** 3)


# ============================================================
# 策略6: 情绪类因子（优化版）
# ============================================================

def calc_sentiment_factors(
    df: pd.DataFrame,
    daily_data: Optional[Dict[str, pd.DataFrame]] = None,
    limit_up_counts: Optional[Dict[str, int]] = None,
    limit_down_counts: Optional[Dict[str, int]] = None,
) -> pd.DataFrame:
    """
    情绪因子（6个）：
    涨停频次、跌停频次(反向)、换手率异常度、量比、价格位置(20日)、5日反转信号
    """
    result = pd.DataFrame(index=df.index)
    
    # === 涨停频次（近20天涨停天数）===
    if limit_up_counts is not None:
        lu = [limit_up_counts.get(str(code), 0) for code in df.index]
        result["limit_up_freq"] = pd.Series(lu, index=df.index)
    else:
        result["limit_up_freq"] = pd.Series(0, index=df.index)
    
    # === 跌停频次（反向：跌停多=情绪差=低分）===
    if limit_down_counts is not None:
        ld = [-limit_down_counts.get(str(code), 0) for code in df.index]
        result["limit_down_inv"] = pd.Series(ld, index=df.index)
    else:
        result["limit_down_inv"] = pd.Series(0, index=df.index)
    
    # === 换手率异常度 ===
    # 用 log(turnover) 做打分：高换手=市场关注度高
    turnover = pd.to_numeric(df.get("turnover_rate", pd.Series(index=df.index, dtype=float)), errors="coerce")
    if turnover.notna().sum() > 10:
        result["turnover_log"] = np.log1p(turnover.clip(0, 50))
    else:
        result["turnover_log"] = pd.Series(0.0, index=df.index)
    
    # === 量比 ===
    vol_ratio = pd.to_numeric(df.get("volume_ratio", pd.Series(index=df.index, dtype=float)), errors="coerce")
    if vol_ratio.notna().sum() > 10:
        result["volume_burst"] = np.log1p(vol_ratio.clip(0, 10))
    else:
        result["volume_burst"] = pd.Series(0.0, index=df.index)
    
    # === 价格位置（20日区间位置）===
    # (当前价 - 20日最低) / (20日最高 - 20日最低) → 0=底部，1=顶部
    if daily_data is not None and len(daily_data) > 0:
        price_positions = []
        for code in df.index:
            hist = daily_data.get(code)
            if hist is not None and len(hist) >= 20:
                close = hist["close"].values.astype(float)
                high_20 = np.max(close[-20:])
                low_20 = np.min(close[-20:])
                if high_20 > low_20:
                    pos = (close[-1] - low_20) / (high_20 - low_20)
                    # 中性偏好：底部超卖反弹 + 顶部动量持续
                    # 用 (pos - 0.5) 绝对值小 → 位置适中
                    price_positions.append(pos)
                else:
                    price_positions.append(0.5)
            else:
                price_positions.append(0.5)
        # 适中位置最佳（非极端）
        pos_series = pd.Series(price_positions, index=df.index)
        result["price_position"] = pos_series  # 保留原始值，z-score会标准化
    else:
        result["price_position"] = pd.Series(0.5, index=df.index)
    
    # === 5日短期反转信号 ===
    # 近5日涨幅过大的可能反转 → 负信号
    if daily_data is not None and len(daily_data) > 0:
        short_revs = []
        for code in df.index:
            hist = daily_data.get(code)
            if hist is not None and len(hist) >= 5:
                close = hist["close"].values.astype(float)
                rev_5d = (close[-1] / close[-5] - 1) * 100
                short_revs.append(-rev_5d)  # 反转信号：涨多了该跌→取反
            else:
                pct = pd.to_numeric(df.loc[code].get("pct_chg", 0), errors="coerce")
                short_revs.append(-float(pct) if not pd.isna(pct) else 0)
        result["short_reversal"] = pd.Series(short_revs, index=df.index)
    else:
        pct = pd.to_numeric(df.get("pct_chg", pd.Series(index=df.index, dtype=float)), errors="coerce")
        result["short_reversal"] = -pct.fillna(0)
    
    # === 成交额排名（大成交额=高关注度）===
    amount = pd.to_numeric(df.get("amount", pd.Series(index=df.index, dtype=float)), errors="coerce")
    if amount.notna().sum() > 10:
        result["amount_rank"] = np.log1p(amount).rank(pct=True)
    else:
        result["amount_rank"] = pd.Series(0.5, index=df.index)
    
    for col in result.columns:
        result[col] = zscore_neutralize(result[col])
    
    return result
