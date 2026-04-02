"""
智能多因子选股系统 - 数据获取层（腾讯财经版）
100%使用腾讯财经API，无需akshare/yfinance
在沙箱中完全可用
"""

from __future__ import annotations
import json
import time
import urllib.request
import ssl
import pandas as pd
import numpy as np
from typing import Literal, Dict, List, Optional


def _get_ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _fetch_url(url: str, timeout: int = 15, encoding: str = "gbk") -> Optional[str]:
    """urllib 抓取"""
    ctx = _get_ssl_ctx()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read().decode(encoding, errors="replace")
    except Exception as e:
        return None


# ============================================================
# 第一层：全市场行情快照
# ============================================================

def get_stock_universe(market: Literal["a", "hk", "both"]) -> pd.DataFrame:
    """获取全市场行情快照（腾讯API）"""
    frames = []
    
    if market in ("a", "both"):
        df_a = _fetch_all_a_shares()
        if df_a is not None and len(df_a) > 0:
            df_a["market"] = "A"
            frames.append(df_a)
    
    if market in ("hk", "both"):
        df_hk = _fetch_hk_shares()
        if df_hk is not None and len(df_hk) > 0:
            df_hk["market"] = "HK"
            frames.append(df_hk)
    
    if not frames:
        raise ValueError("无法获取任何市场数据")
    
    df = pd.concat(frames, ignore_index=True)
    df["code"] = df["code"].astype(str)
    return df


def _gen_a_codes() -> List[str]:
    """生成A股代码范围"""
    codes = []
    # 上海：600xxx, 601xxx, 603xxx, 605xxx, 688xxx
    for prefix in ("600", "601", "603", "605", "688"):
        for i in range(1000):
            codes.append(f"{prefix}{i:03d}")
    # 深圳：000xxx, 001xxx, 002xxx, 003xxx, 300xxx, 301xxx
    for prefix in ("000", "001", "002", "003", "300", "301"):
        for i in range(1000):
            codes.append(f"{prefix}{i:03d}")
    return codes


def _fetch_all_a_shares(batch_size: int = 200) -> Optional[pd.DataFrame]:
    """
    批量获取所有A股行情
    腾讯API支持批量，每次最多200只
    """
    all_codes = _gen_a_codes()
    total = len(all_codes)
    records = []
    
    print(f"[INFO] 扫描A股代码 ({total} 个区间)...")
    
    for batch_start in range(0, total, batch_size):
        batch = all_codes[batch_start : batch_start + batch_size]
        
        # 判断上海/深圳
        url_parts = []
        for code in batch:
            if code.startswith(("6", "9")):
                url_parts.append(f"sh{code}")
            else:
                url_parts.append(f"sz{code}")
        
        url = f"https://qt.gtimg.cn/q={','.join(url_parts)}"
        text = _fetch_url(url, timeout=30)
        if not text:
            continue
        
        for line in text.strip().split(";"):
            if "=" not in line or "~" not in line:
                continue
            try:
                parts = line.split("~")
                if len(parts) < 50:
                    continue
                # 跳过无效（价格为空或0）
                price = parts[3]
                if not price or price == "0.00":
                    continue
                
                code = parts[2].strip()
                name = parts[1].strip()
                if not code or not name:
                    continue
                
                records.append({
                    "code": code,
                    "name": name,
                    "close": _safe_float(parts[3]),
                    "prev_close": _safe_float(parts[4]),
                    "open": _safe_float(parts[5]),
                    "volume": _safe_float(parts[6]),
                    "bid1_vol": _safe_float(parts[7]),
                    "ask1_vol": _safe_float(parts[8]),
                    "high": _safe_float(parts[33]),
                    "low": _safe_float(parts[34]),
                    "amount": _safe_float(parts[37]) * 10000,  # 万→元
                    "turnover_rate": _safe_float(parts[38]),
                    "pe": _safe_float(parts[39]),
                    "amplitude": _safe_float(parts[43]),
                    "market_cap": _safe_float(parts[45]) * 1e8,  # 亿→元
                    "float_market_cap": _safe_float(parts[44]) * 1e8,
                    "pb": _safe_float(parts[46]),
                    "pct_chg": _safe_float(parts[32]),
                })
            except Exception:
                continue
        
        batch_num = batch_start // batch_size + 1
        if batch_num % 5 == 0:
            print(f"   进度: {batch_num}/{(total + batch_size - 1) // batch_size} 批次, 已获取 {len(records)} 只")
        
        time.sleep(0.3)
    
    if records:
        df = pd.DataFrame(records)
        # 过滤：有代码有名称有价格
        df = df[(df["code"].str.len() == 6) & (df["name"].str.len() > 0) & (df["close"] > 0)]
        df = df.drop_duplicates(subset=["code"])
        print(f"[OK] A股总计: {len(df)} 只")
        return df
    
    return None


def _fetch_hk_shares() -> Optional[pd.DataFrame]:
    """港股：使用常见恒指成分股"""
    hk_codes = [
        "hk00700", "hk09988", "hk00941", "hk01299", "hk00388",
        "hk02318", "hk00005", "hk03690", "hk01398", "hk00939",
        "hk01810", "hk01211", "hk02020", "hk00883", "hk01024",
        "hk09618", "hk02382", "hk06060", "hk00268", "hk00175",
        "hk02269", "hk01928", "hk09999", "hk00288", "hk01109",
        "hk02015", "hk00857", "hk02688", "hk00688", "hk01093",
    ]
    
    url = f"https://qt.gtimg.cn/q={','.join(hk_codes)}"
    text = _fetch_url(url, encoding="utf-8")
    if not text:
        return None
    
    records = []
    for line in text.strip().split(";"):
        if "=" not in line or "~" not in line:
            continue
        try:
            parts = line.split("~")
            if len(parts) < 40:
                continue
            code = parts[2].strip()
            name = parts[1].strip()
            price = _safe_float(parts[3])
            if not code or price <= 0:
                continue
            records.append({
                "code": code,
                "name": name,
                "close": price,
                "prev_close": _safe_float(parts[4]),
                "open": _safe_float(parts[5]),
                "high": _safe_float(parts[33]),
                "low": _safe_float(parts[34]),
                "volume": _safe_float(parts[6]),
                "amount": _safe_float(parts[37]) * 10000,
                "pct_chg": _safe_float(parts[32]),
                "pe": _safe_float(parts[39]),
                "pb": _safe_float(parts[46]),
                "market_cap": _safe_float(parts[45]) * 1e8,
                "turnover_rate": np.nan,
                "ret_60d": np.nan,
                "volume_ratio": np.nan,
            })
        except Exception:
            continue
    
    if records:
        df = pd.DataFrame(records)
        print(f"[OK] 港股: {len(df)} 只")
        return df
    return None


# ============================================================
# 第二层：逐只日线数据
# ============================================================

def fetch_daily_batch(
    codes: List[str],
    market: str = "A",
    days: int = 500,
    batch_sleep: float = 0.2,
) -> Dict[str, pd.DataFrame]:
    """批量获取日K线（腾讯API）"""
    result = {}
    total = len(codes)
    
    for i, code in enumerate(codes):
        if (i + 1) % 50 == 0:
            print(f"   日线进度: {i+1}/{total}")
        
        df = _fetch_daily_tencent(code, market, days)
        if df is not None and len(df) >= 20:
            result[code] = df
        
        time.sleep(batch_sleep)
    
    return result


def _fetch_daily_tencent(code: str, market: str, days: int = 500) -> Optional[pd.DataFrame]:
    """腾讯日K线 API"""
    if market == "A":
        prefix = "sh" if code.startswith(("6", "9")) else "sz"
    elif market == "HK":
        prefix = "hk"
    else:
        prefix = "sh" if code.startswith(("6", "9")) else "sz"
    
    symbol = f"{prefix}{code}"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{min(days, 1000)},qfq"
    
    text = _fetch_url(url, encoding="utf-8")
    if not text:
        return None
    
    try:
        data = json.loads(text)
        stock_data = data.get("data", {}).get(symbol, {})
        klines = stock_data.get("qfqday", []) or stock_data.get("day", [])
        
        if not klines:
            return None
        
        records = []
        for k in klines:
            if len(k) >= 6:
                records.append({
                    "date": k[0],
                    "open": _safe_float(k[1]),
                    "close": _safe_float(k[2]),
                    "high": _safe_float(k[3]),
                    "low": _safe_float(k[4]),
                    "volume": _safe_float(k[5]),
                })
        
        return pd.DataFrame(records)
    except Exception:
        return None


# ============================================================
# 第二层：逐只财务数据（简化版）
# ============================================================

def fetch_financial_batch(
    codes: List[str],
    market: str = "A",
    batch_sleep: float = 0.3,
) -> Dict[str, dict]:
    """
    财务数据获取
    腾讯API的行情数据已包含PE/PB，但没有详细财务指标
    这里用PE/PB/市值做近似推算
    """
    result = {}
    # 财务数据需要额外来源，暂用行情数据近似
    print("[INFO] 财务详细数据使用行情数据近似（PE/PB/市值）")
    return result


# ============================================================
# 涨跌停数据（近似）
# ============================================================

def fetch_limit_up_batch(days: int = 20, sleep_sec: float = 0.5) -> Dict[str, int]:
    """涨跌停数据需要额外接口，暂用空"""
    return {}


def fetch_limit_down_batch(days: int = 20, sleep_sec: float = 0.5) -> Dict[str, int]:
    return {}


# ============================================================
# 工具函数
# ============================================================

def _safe_float(val, default: float = 0.0) -> float:
    """安全转浮点"""
    if val is None or val == "" or val == "--":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default
