"""
智能多因子选股系统 - 打分与加权模块
ICIR归一化 + 风险平价 + 非线性交互项
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Dict, Optional


# 策略名称映射
STRATEGY_NAMES = {
    1: "低估值",
    2: "成长性",
    3: "质量型",
    4: "动量",
    5: "低波动",
    6: "情绪",
}

# 因子名称 → 大类映射（用于交互项判断）
FACTOR_TO_STRATEGY = {
    "EP": 1, "BP": 1, "DY": 1, "DY_proxy": 1, "PS_inv": 1, "PEG_inv": 1, "PE_cross_rank": 1,
    "rev_growth": 2, "profit_growth": 2, "consistency": 2, "earn_accel": 2,
    "ROE": 3, "debt_score": 3, "cashflow_quality": 3, "gross_margin": 3,
    "mom_3m_skip1": 4, "mom_6m_skip1": 4, "mom_12m_skip1": 4,
    "trend_strength": 4, "vol_momentum": 4, "mom_2m": 4,
    "vol_60d": 5, "downside_dev": 5, "sortino_proxy": 5, "VaR_5pct": 5,
    "skewness": 5, "vol_pct_rank": 5,
    "downside_vol": 5, "max_dd_6m": 5, "beta_proxy": 5,
    "limit_up_freq": 6, "limit_down_inv": 6, "turnover_log": 6,
    "volume_burst": 6, "price_position": 6, "short_reversal": 6, "amount_rank": 6,
    "turnover_score": 6, "pct_rank": 6,
}

# 大类内因子默认权重（无ICIR时等权）
DEFAULT_STRATEGY_WEIGHTS = {
    1: {"EP": 0.25, "BP": 0.20, "PS_inv": 0.15, "PEG_inv": 0.15, "DY": 0.15, "PE_cross_rank": 0.10},
    2: {"rev_growth": 0.25, "profit_growth": 0.30, "consistency": 0.25, "earn_accel": 0.20},
    3: {"ROE": 0.30, "debt_score": 0.25, "cashflow_quality": 0.25, "gross_margin": 0.20},
    4: {"mom_3m_skip1": 0.25, "mom_6m_skip1": 0.25, "mom_12m_skip1": 0.15,
        "trend_strength": 0.20, "vol_momentum": 0.15},
    5: {"vol_60d": 0.20, "downside_dev": 0.20, "sortino_proxy": 0.15,
        "VaR_5pct": 0.15, "skewness": 0.15, "vol_pct_rank": 0.15},
    6: {"limit_up_freq": 0.20, "limit_down_inv": 0.15, "turnover_log": 0.15,
        "volume_burst": 0.15, "price_position": 0.10, "short_reversal": 0.10, "amount_rank": 0.15},
}


def compute_factor_icir(factor_series: pd.Series, min_periods: int = 30) -> float:
    """
    计算因子ICIR（截面版）
    
    当无未来收益时，用因子值的截面区分度作为有效性代理：
    IC ≈ rank_corr(factor, time_index) 的稳定性
    """
    s = factor_series.dropna()
    if len(s) < min_periods:
        return 0.0
    
    # 截面区分度：因子值的变异系数
    cv = abs(s.mean()) / (s.std() + 1e-8)
    
    # 极端值比例（因子是否有尾巴信号）
    pct_extreme = ((s.abs() > 2).sum() / len(s))
    
    # 综合ICIR代理
    icir = cv * 0.5 + pct_extreme * 0.5
    
    # 限制范围
    return np.clip(icir, 0, 2.0)


def icir_normalize_weights(icir_dict: Dict[str, float]) -> Dict[str, float]:
    """按ICIR归一化权重"""
    total = sum(icir_dict.values())
    if total < 1e-8:
        n = len(icir_dict)
        return {k: 1.0 / n for k in icir_dict}
    return {k: v / total for k, v in icir_dict.items()}


def risk_parity_weights(factor_df: pd.DataFrame) -> pd.Series:
    """
    风险平价权重：w_i ∝ 1 / Var(factor_i)
    """
    variances = factor_df.var()
    inv_var = 1.0 / variances.replace(0, np.nan)
    total = inv_var.sum()
    weights = inv_var / total
    return weights


def compute_strategy_score(
    factor_df: pd.DataFrame,
    strategy_id: int,
) -> pd.Series:
    """
    计算单个策略大类的综合得分
    
    流程：
    1. 计算各因子ICIR
    2. ICIR < 0.3 剔除
    3. 按ICIR归一化权重
    4. 加权求和
    """
    if factor_df.empty or factor_df.shape[1] == 0:
        return pd.Series(0.0, index=factor_df.index)
    
    # 1. 计算每个因子的ICIR
    icir_dict = {}
    for col in factor_df.columns:
        icir = compute_factor_icir(factor_df[col])
        icir_dict[col] = icir
    
    # 2. 剔除低效因子（ICIR < 0.3）
    effective_cols = [col for col, icir in icir_dict.items() if icir >= 0.3]
    
    if not effective_cols:
        # 全不达标 → 使用默认权重
        default_w = DEFAULT_STRATEGY_WEIGHTS.get(strategy_id, {})
        available = [c for c in default_w if c in factor_df.columns]
        if not available:
            available = factor_df.columns.tolist()[:4]
        weights = {c: default_w.get(c, 1.0 / len(available)) for c in available}
        total_w = sum(weights.values())
        weights = {c: w / total_w for c, w in weights.items()}
        effective_cols = available
    else:
        effective_icir = {c: icir_dict[c] for c in effective_cols}
        weights = icir_normalize_weights(effective_icir)
    
    # 3. 加权求和
    score = pd.Series(0.0, index=factor_df.index)
    for col, w in weights.items():
        if col in factor_df.columns:
            score += w * factor_df[col].fillna(0)
    
    return score


def compute_interaction_terms(strategy_scores: Dict[int, pd.Series]) -> pd.Series:
    """
    非线性交互项
    
    - 低波 × 动量：低波动环境下动量更持续
    - 质量 × 成长：高质量 + 高成长 = 双击
    - 低估值 × 情绪：低估值 + 情绪回暖 = 戴维斯双击
    """
    if not strategy_scores:
        return pd.Series()
    
    # 取第一个 series 的 index
    idx = list(strategy_scores.values())[0].index
    result = pd.Series(0.0, index=idx)
    
    # 低波动 × 动量（正向：两个正信号叠加）
    if 4 in strategy_scores and 5 in strategy_scores:
        interaction = strategy_scores[4] * strategy_scores[5]
        result += 0.15 * interaction
    
    # 质量 × 成长
    if 2 in strategy_scores and 3 in strategy_scores:
        interaction = strategy_scores[2] * strategy_scores[3]
        result += 0.10 * interaction
    
    # 低估值 × 情绪
    if 1 in strategy_scores and 6 in strategy_scores:
        interaction = strategy_scores[1] * strategy_scores[6]
        result += 0.10 * interaction
    
    return result


def compute_composite_score(
    strategy_scores: Dict[int, pd.Series],
    strategy_weights: Optional[Dict[int, float]] = None,
) -> pd.Series:
    """
    综合得分 = Σ(权重_i × 因子_i_zscore) + 交互项
    """
    if not strategy_scores:
        return pd.Series()
    
    if strategy_weights is None:
        n = len(strategy_scores)
        strategy_weights = {sid: 1.0 / n for sid in strategy_scores}
    
    # 主得分
    idx = list(strategy_scores.values())[0].index
    composite = pd.Series(0.0, index=idx)
    for sid, score in strategy_scores.items():
        w = strategy_weights.get(sid, 0)
        composite += w * score.fillna(0)
    
    # 交互项
    interaction = compute_interaction_terms(strategy_scores)
    if len(interaction) > 0:
        composite += interaction
    
    # 最终标准化
    if composite.std() > 1e-8:
        composite = (composite - composite.mean()) / composite.std()
    
    return composite


def rank_stocks(
    composite_scores: pd.Series,
    stock_info: pd.DataFrame,
    top_n: int = 80,
) -> pd.DataFrame:
    """排名输出前N只"""
    ranked = composite_scores.sort_values(ascending=False).head(top_n)
    
    result = pd.DataFrame({
        "rank": range(1, len(ranked) + 1),
        "code": ranked.index,
        "composite_score": ranked.values.round(4),
    })
    
    # 合并股票信息
    if stock_info is not None:
        info_cols = {c: c for c in ["code", "name", "market_cap", "pe", "pb", "market"] if c in stock_info.columns}
        if "code" in info_cols:
            info_map = stock_info[list(info_cols.values())].drop_duplicates(subset=["code"]).set_index("code")
            for col in ["name", "market_cap", "pe", "pb", "market"]:
                if col in info_map.columns:
                    result[col] = result["code"].map(info_map[col]).fillna("")
    
    return result.reset_index(drop=True)
