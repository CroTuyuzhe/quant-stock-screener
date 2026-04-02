---
name: quant-stock-screener
description: |
  量化多因子选股系统。当用户说"选股"、"智能选股"、"帮我选股票"、"多因子选股"、"策略选股"时触发。
  支持6大策略组合：低估值、成长性、质量型、动量、低波动、情绪类。覆盖A股和港股。
  流程：用户选择策略组合 → 选择市场(A股/港股/两者) → 跑脚本 → 输出多因子打分排名前50-80只。
  加权方式：ICIR归一化 → 风险平价 → 非线性交互项 → 综合得分排名。
---

# 量化多因子选股系统

## 快速使用

```bash
cd {baseDir}/scripts
python3 screener_main.py --strategies 1456 --market a --top 30 --format text
```

## 交互流程

当用户触发选股时，依次完成以下步骤：

### Step 1: 策略选择

向用户展示6大策略并让用户输入数字组合：

```
🎯 智能选股 — 请选择策略组合（输入数字，如 135）：

1. 📊 低估值选股（低PE、低PB、高股息）
2. 🚀 成长性选股（连续多季度业绩增长）
3. 💎 质量型选股（高ROE、低负债、现金流好）
4. ⚡ 动量选股（剔除1月反转，中期动量）
5. 🛡️ 低波动选股（低波、低Beta、低尾部风险）
6. 🔥 情绪类选股（热点、近1月涨跌停频次）

选择策略后选择市场：
A. A股  B. 港股  C. A股+港股
```

### Step 2: 运行脚本

```bash
cd {baseDir}/scripts && python3 screener_main.py \
  --strategies <strategy_numbers> \
  --market <a|hk|both> \
  --top <top_n, default 80> \
  --format json
```

### Step 3: 结果输出

脚本返回 JSON 格式结果，包含：
- 每只股票的各因子得分（标准化后）
- 大类内 ICIR 归一化权重
- 综合得分（含交互项）
- 排名、行业、市值等基本信息

将 JSON 结果整理为易读报告输出给用户。

## 技术架构

```
全市场行情快照 (腾讯财经API, ~36s)
       │
       ▼
  粗筛 Top 500 (行情快照数据)
       │
       ▼
  精算 (逐只日线获取 ~5min)
       │
       ├── 因子计算 (24个因子, 6大类)
       ├── ICIR筛选 (剔除 ICIR < 0.3)
       ├── ICIR归一化权重
       ├── 非线性交互项
       ├── 综合得分
       │
       ▼
  输出 Top 50-80 排名
```

## 因子定义

详见 [references/factor_definitions.md](references/factor_definitions.md)

## 加权方法论

详见 [references/weighting_methodology.md](references/weighting_methodology.md)

## 依赖

```bash
pip install -r requirements.txt
```

主要依赖：
- **腾讯财经API**（内置，无需额外key，通过 urllib 直接访问）
- pandas / numpy — 数据处理
- scipy — 统计计算

## CLI 参数

| 参数 | 缩写 | 说明 | 默认值 |
|------|------|------|--------|
| `--strategies` | `-s` | 策略组合（如 1456） | 必填 |
| `--market` | `-m` | a= A股, hk=港股, both=两者 | a |
| `--top` | `-t` | 输出前N只 | 80 |
| `--coarse` | `-c` | 粗筛保留数量 | 500 |
| `--format` | `-f` | json 或 text | json |

## 输出格式 (JSON)

```json
{
  "stocks": [
    {
      "rank": 1,
      "code": "600015",
      "composite_score": 3.3769,
      "name": "华夏银行",
      "market_cap": 119203000000.0,
      "pe": 4.38,
      "pb": 0.38,
      "market": "A",
      "s1": 1.375,
      "s4": -0.115,
      "s5": 1.254,
      "s6": -0.04
    }
  ],
  "strategy_weights": { "低估值": 0.25, "动量": 0.25, ... },
  "factors_used": { "低估值": ["EP", "BP", ...], ... },
  "meta": { "total_universe": 5092, "strategies": [...], ... }
}
```

## 注意事项

- 数据基于腾讯财经API，A股覆盖5000+只，港股覆盖恒指成分股
- 财务详细数据（ROE/增长率）暂未接入，质量/成长因子使用行情近似
- 涨跌停频次暂未接入
- 结论仅供研究参考，非投资建议
