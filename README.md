<div align="center">

```
 ██████╗ ██╗   ██╗ █████╗ ███╗   ██╗████████╗
██╔═══██╗██║   ██║██╔══██╗████╗  ██║╚══██╔══╝
██║   ██║██║   ██║███████║██╔██╗ ██║   ██║
██║▄▄ ██║██║   ██║██╔══██║██║╚██╗██║   ██║
╚██████╔╝╚██████╔╝██║  ██║██║ ╚████║   ██║
 ╚══▀▀═╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝
```

# 量化多因子选股系统

> *用量化的方法，筛出值得研究的股票*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://python.org)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.ai/code)
[![AgentSkills](https://img.shields.io/badge/AgentSkills-Standard-green)](https://agentskills.io)

<br>

全市场 5000+ 只 A 股 / 港股实时扫描<br>
6 大策略 × 24 个因子 × ICIR 加权 × 非线性交互<br>
一句话触发，8 分钟出 Top 80 排名

[快速开始](#快速开始) · [策略说明](#策略矩阵) · [因子定义](#因子总览) · [安装](#安装) · [CLI](#命令行用法)

</div>

---

## 它是什么？

一个**智能多因子选股系统**，作为 Claude Code / OpenClaw 的 Skill 运行。

你只需要说一句话，它就能自动完成：

```
用户  ❯ 选股

系统  ❯ 请选择策略组合（输入数字）
         1.低估值  2.成长性  3.质量型  4.动量  5.低波动  6.情绪

用户  ❯ 1456

系统  ❯ 选择市场：A.A股  B.港股  C.两者

用户  ❯ A

         ⏳ 全市场扫描 5000+ 只 → 粗筛 500 → 精算 498 只...
         ✅ 耗时 8 分钟，输出 Top 80
```

无需手动跑脚本、无需配置数据源、无需 API Key。

---

## 策略矩阵

| # | 策略 | 核心逻辑 | 因子数 |
|---|------|---------|:------:|
| 1 | 📊 低估值 | 找价格被低估的股票 | 6 |
| 2 | 🚀 成长性 | 找业绩持续增长的股票 | 4 |
| 3 | 💎 质量型 | 找基本面优质的公司 | 4 |
| 4 | ⚡ 动量 | 找趋势正在形成的股票 | 5 |
| 5 | 🛡️ 低波动 | 找风险可控的标的 | 6 |
| 6 | 🔥 情绪 | 找市场关注度高的股票 | 7 |

**可自由组合**，如 `1456`（低估值+动量+低波动+情绪）、`234`（成长+质量+动量）。

---

## 因子总览

<details>
<summary>📊 低估值（6个因子）</summary>

| 因子 | 定义 | 方向 |
|------|------|------|
| EP | 1/PE（市盈率倒数） | 越高越便宜 |
| BP | 1/PB（市净率倒数） | 越高越便宜 |
| PS_inv | 营收/市值（市销率倒数） | 越高越便宜 |
| PEG_inv | EPS增长率/PE | 越高性价比越好 |
| DY | 每股分红/股价 | 越高回报越好 |
| PE_cross_rank | PE 截面分位数 | 排名越低越便宜 |

</details>

<details>
<summary>🚀 成长性（4个因子）</summary>

| 因子 | 定义 | 方向 |
|------|------|------|
| rev_growth | 营收同比增长率 | 正增长 |
| profit_growth | 净利润同比增长率 | 正增长 |
| consistency | 营收+利润同时正增长 | 双确认 |
| earn_accel | 净利润增速 > 营收增速 | 盈利改善 |

</details>

<details>
<summary>💎 质量型（4个因子）</summary>

| 因子 | 定义 | 方向 |
|------|------|------|
| ROE | 净资产收益率 | 越高越好 |
| debt_score | 资产负债率（取反） | 越低越安全 |
| cashflow_quality | 经营现金流/净利润 | >1 有现金支撑 |
| gross_margin | 毛利率 | 越高护城河越宽 |

</details>

<details>
<summary>⚡ 动量（5个因子）</summary>

| 因子 | 定义 | 方向 |
|------|------|------|
| mom_3m_skip1 | 3 个月动量，剔除最近 1 个月 | 正=上升趋势 |
| mom_6m_skip1 | 6 个月动量，剔除最近 1 个月 | 正=上升趋势 |
| mom_12m_skip1 | 12 个月动量，剔除最近 1 个月 | 正=长期趋势 |
| trend_strength | (MA20 - MA60) / MA60 | 正=均线多头 |
| vol_momentum | 量价配合（放量上涨） | 正=强动量 |

</details>

<details>
<summary>🛡️ 低波动（6个因子）</summary>

| 因子 | 定义 | 方向 |
|------|------|------|
| vol_60d | 60 日年化波动率（取反） | 越低越稳 |
| downside_dev | 下行偏差（负收益标准差） | 越低越安全 |
| sortino_proxy | 年化收益/下行偏差 | 越高风险调整越好 |
| VaR_5pct | 5% 分位数风险价值 | 损失越小越好 |
| skewness | 收益分布偏度（取反） | 负偏=尾部风险 |
| vol_pct_rank | 波动率截面分位 | 越低排名越好 |

</details>

<details>
<summary>🔥 情绪（7个因子）</summary>

| 因子 | 定义 | 方向 |
|------|------|------|
| limit_up_freq | 近 20 日涨停天数 | 市场热度 |
| limit_down_inv | 近 20 日跌停天数（取反） | 越少越好 |
| turnover_log | ln(换手率) | 关注度 |
| volume_burst | ln(量比) | 放量信号 |
| price_position | 20 日区间位置 | 0~1 区间 |
| short_reversal | 5 日涨跌幅（取反） | 均值回归 |
| amount_rank | 成交额截面排名 | 大资金关注 |

</details>

---

## 加权方法论

```
因子原始值 → 缩尾(2.5%) → 行业中性 → z-score 标准化
       │
       ▼
  计算 ICIR（截面区分度代理）
  剔除 ICIR < 0.3 的因子
       │
       ▼
  ICIR 归一化权重（大类内）
       │
       ▼
  策略等权 × 非线性交互项
       │
       ▼
  综合得分排名 → Top N
```

**交互项（非线性叠加）：**
- 低波动 × 动量 (+15%)：低波动环境下动量更持续
- 质量 × 成长 (+10%)：高质量+高成长 = 双击潜力
- 低估值 × 情绪 (+10%)：低估值+情绪回暖 = 戴维斯双击

---

## 技术架构

```
┌──────────────────────────────────────────────┐
│               全市场行情快照                    │
│         腾讯财经 API（无需 Key）                │
│              ~36 秒，5000+ 只                  │
└──────────────────┬───────────────────────────┘
                   ▼
          ┌─────────────────┐
          │   粗筛 Top 500   │  ← 行情快照数据
          │  PE/PB/涨跌幅    │
          └────────┬────────┘
                   ▼
          ┌─────────────────┐
          │  精算（逐只日线）  │  ← 腾讯 K 线 API
          │  ~5 分钟 / 500 只 │
          └────────┬────────┘
                   ▼
     ┌─────────────────────────────┐
     │  24 个因子 × 6 大类          │
     │  ICIR 筛选 + 归一化权重       │
     │  非线性交互项                  │
     └─────────────┬───────────────┘
                   ▼
          ┌─────────────────┐
          │   Top 80 排名    │
          │  JSON / Text     │
          └─────────────────┘
```

---

## 安装

### Claude Code

```bash
# 克隆到 skills 目录
git clone https://github.com/CroTuyuzhe/quant-stock-screener ~/.claude/skills/quant-stock-screener

# 安装依赖
pip3 install -r requirements.txt
```

### OpenClaw

```bash
git clone https://github.com/CroTuyuzhe/quant-stock-screener ~/.openclaw/workspace/skills/quant-stock-screener
pip3 install -r requirements.txt
```

---

## 命令行用法

```bash
cd scripts

# A 股 + 低估值 + 动量 + 低波动 + 情绪
python3 screener_main.py --strategies 1456 --market a --top 30 --format text

# 港股 + 质量 + 成长
python3 screener_main.py --strategies 23 --market hk --top 20

# 两者 + 全策略
python3 screener_main.py --strategies 123456 --market both --top 80 --format json
```

| 参数 | 缩写 | 说明 | 默认 |
|------|------|------|------|
| `--strategies` | `-s` | 策略组合（如 1456） | **必填** |
| `--market` | `-m` | `a` / `hk` / `both` | `a` |
| `--top` | `-t` | 输出前 N 只 | `80` |
| `--coarse` | `-c` | 粗筛保留数 | `500` |
| `--format` | `-f` | `json` / `text` | `json` |

---

## 输出示例

```json
{
  "stocks": [
    {
      "rank": 1,
      "code": "600015",
      "composite_score": 3.3769,
      "name": "华夏银行",
      "pe": 4.38,
      "pb": 0.38,
      "s1": 1.375,
      "s4": -0.115,
      "s5": 1.254,
      "s6": -0.04
    }
  ],
  "strategy_weights": { "低估值": 0.25, "动量": 0.25, ... },
  "meta": { "total_universe": 5092, "strategies": [...] }
}
```

---

## 项目结构

```
quant-stock-screener/
├── SKILL.md                      # Skill 入口定义
├── README.md
├── requirements.txt
├── references/
│   ├── factor_definitions.md     # 24 个因子定义与公式
│   └── weighting_methodology.md  # ICIR 加权方法论
└── scripts/
    ├── screener_main.py          # 主入口（CLI）
    ├── factor_engine.py          # 因子计算引擎
    ├── scorer.py                 # ICIR 加权 & 打分
    ├── data_fetcher.py           # 腾讯财经 API 数据层
    └── backtest.py               # 回测模块（WIP）
```

---

## 已知限制

- 财务详细数据（ROE/增长率/现金流）暂未接入，质量/成长因子使用行情近似
- 涨跌停频次统计暂未接入
- 港股仅覆盖恒指成分股（~30 只）
- 回测模块开发中

---

## Roadmap

- [ ] 接入财报数据（东方财富 F10）
- [ ] 涨跌停频次统计
- [ ] 月度回测验证
- [ ] 定时选股 + 飞书自动推送
- [ ] 港股全量覆盖
- [ ] 行业中性约束
- [ ] 因子 IC 时序图

---

<div align="center">

**觉得有用的话，给个 Star ⭐**

[![Star](https://img.shields.io/github/stars/CroTuyuzhe/quant-stock-screener?style=social)](https://github.com/CroTuyuzhe/quant-stock-screener)

MIT License © CroTuyuzhe

</div>
