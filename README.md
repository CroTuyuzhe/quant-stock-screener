# 🎯 Quant Stock Screener - 量化多因子选股系统

A multi-factor stock screening system for A-shares and HK stocks, with ICIR-weighted scoring and factor interaction terms.

## Features

- **6 Strategy Factors**: Low Valuation, Growth, Quality, Momentum, Low Volatility, Sentiment
- **24 Factors** across 6 categories with ICIR-based weighting
- **Two-Stage Screening**: Coarse filter (5000+ → 500) → Fine computation (→ Top 80)
- **A-Shares & HK Stocks**: Full market coverage via Tencent Finance API
- **Non-Linear Interactions**: Low Vol × Momentum, Quality × Growth, Value × Sentiment

## Quick Start

```bash
pip install -r requirements.txt
cd scripts

# Screen A-shares with valuation + momentum + low vol + sentiment
python3 screener_main.py --strategies 1456 --market a --top 30 --format text

# Screen both A-shares and HK stocks
python3 screener_main.py --strategies 1346 --market both --top 50 --format json
```

## Strategies

| # | Strategy | Factors |
|---|----------|---------|
| 1 | 📊 Low Valuation | EP, BP, PS_inv, PEG_inv, DY, PE_cross_rank |
| 2 | 🚀 Growth | rev_growth, profit_growth, consistency, earn_accel |
| 3 | 💎 Quality | ROE, debt_score, cashflow_quality, gross_margin |
| 4 | ⚡ Momentum | mom_3m_skip1, mom_6m_skip1, mom_12m_skip1, trend_strength, vol_momentum |
| 5 | 🛡️ Low Volatility | vol_60d, downside_dev, sortino_proxy, VaR_5pct, skewness, vol_pct_rank |
| 6 | 🔥 Sentiment | limit_up_freq, limit_down_inv, turnover_log, volume_burst, price_position, short_reversal, amount_rank |

## Scoring Methodology

1. **Factor Neutralization**: Industry-neutral + winsorize + z-score
2. **ICIR Filtering**: Factors with ICIR < 0.3 are eliminated
3. **ICIR Normalized Weights**: Within each strategy category
4. **Equal Weight Across Strategies**: (or custom weights)
5. **Non-Linear Interaction Terms**:
   - Low Vol × Momentum (+15%): Momentum more persistent in low-vol environments
   - Quality × Growth (+10%): Double-click potential
   - Value × Sentiment (+10%): Davis Double-Play
6. **Composite Score**: Σ(weight × factor_zscore) + interactions

## CLI Arguments

| Arg | Short | Description | Default |
|-----|-------|-------------|---------|
| `--strategies` | `-s` | Strategy combo (e.g. 1456) | Required |
| `--market` | `-m` | `a`=A-shares, `hk`=HK, `both` | `a` |
| `--top` | `-t` | Top N stocks | 80 |
| `--coarse` | `-c` | Coarse filter size | 500 |
| `--format` | `-f` | `json` or `text` | `json` |

## Data Source

[Tencent Finance API](https://qt.gtimg.cn) — free, no API key required.

## Project Structure

```
quant-stock-screener/
├── README.md
├── SKILL.md                      # Agent skill definition
├── requirements.txt
├── references/
│   ├── factor_definitions.md     # Factor definitions & formulas
│   └── weighting_methodology.md  # ICIR weighting methodology
└── scripts/
    ├── screener_main.py          # Main entry point
    ├── factor_engine.py          # Factor computation (24 factors)
    ├── scorer.py                 # ICIR weighting & scoring
    ├── data_fetcher.py           # Tencent Finance API data layer
    └── backtest.py               # Backtesting (WIP)
```

## Disclaimer

⚠️ For research purposes only. Not investment advice.
