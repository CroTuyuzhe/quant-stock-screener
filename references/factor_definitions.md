# 因子定义

## 1. 低估值因子（策略1）

| 因子 | 定义 | 方向 | 数据源 |
|------|------|------|--------|
| EP | 1/PE（市盈率倒数） | 高=便宜 | akshare/实时行情 |
| BP | 1/PB（市净率倒数） | 高=便宜 | akshare/实时行情 |
| DY | 股息率（近12月分红/市值） | 高=高回报 | akshare/实时行情 |
| EP_hist_rank | PE历史分位数（3年） | 低分位=便宜 | akshare日线+财务 |

行业中性：行业内排名标准化。

## 2. 成长性因子（策略2）

| 因子 | 定义 | 方向 | 数据源 |
|------|------|------|--------|
| rev_growth | 营收同比增长率 | 高=成长快 | akshare财务报表 |
| profit_growth | 归母净利润同比增长率 | 高=成长快 | akshare财务报表 |
| rev_consist | 连续N季度营收正增长（N=季度数） | 高=稳定增长 | akshare财务报表 |
| profit_consist | 连续N季度净利润正增长 | 高=稳定增长 | akshare财务报表 |
| earn_accel | 盈利加速（近季增速 > 前季增速） | 1=加速 | akshare财务报表 |

## 3. 质量型因子（策略3）

| 因子 | 定义 | 方向 | 数据源 |
|------|------|------|--------|
| ROE | 净资产收益率（TTM） | 高=高质量 | akshare财务报表 |
| debt_ratio | 资产负债率 | 低=安全 | akshare财务报表 |
| CFO_ratio | 经营性现金流/净利润 | 高=盈利质量好 | akshare财务报表 |
| gross_margin | 毛利率 | 高=护城河 | akshare财务报表 |
| accrual | 应计比率（经营现金流-净利润）/总资产 | 低=真实盈利 | akshare财务报表 |

## 4. 动量因子（策略4）

| 因子 | 定义 | 方向 | 数据源 |
|------|------|------|--------|
| mom_3m | 过去3个月收益率（剔除最近1个月） | 高=中期动量 | akshare日线 |
| mom_6m | 过去6个月收益率（剔除最近1个月） | 高=中期动量 | akshare日线 |
| mom_12m | 过去12个月收益率（剔除最近1个月） | 高=长期动量 | akshare日线 |
| trend_strength | (MA20-MA60)/MA60 | 高=趋势强 | akshare日线 |

关键：剔除最近1个月收益以避免短期反转效应。

## 5. 低波动因子（策略5）

| 因子 | 定义 | 方向 | 数据源 |
|------|------|------|--------|
| vol_60d | 60日波动率 | 低=低风险 | akshare日线 |
| beta_60d | 60日Beta（对沪深300/恒生指数） | 低=低风险 | akshare日线 |
| tail_risk | 尾部风险（5%VaR / 波动率） | 低=低风险 | akshare日线 |
| max_drawdown_6m | 6个月最大回撤 | 高=风险大（取反） | akshare日线 |
| downside_vol | 下行波动率 | 低=低风险 | akshare日线 |

## 6. 情绪类因子（策略6）

| 因子 | 定义 | 方向 | 数据源 |
|------|------|------|--------|
| limit_up_count | 近1月涨停次数 | 高=情绪高涨 | akshare涨跌停数据 |
| limit_down_count | 近1月跌停次数 | 低=情绪稳定 | akshare涨跌停数据 |
| turnover_rate | 近1月平均换手率 | 适度=有关注 | akshare日线 |
| hot_sector | 是否属于近期热点板块 | 1=是 | akshare板块数据 |
| abnormal_volume | 近5日均量/20日均量 | 高=关注度上升 | akshare日线 |

情绪因子做特殊处理：非线性打分（避免追涨杀跌）。

## 数据获取

A股：`akshare.stock_zh_a_hist()`, `akshare.stock_financial_report_sina()`
港股：`akshare.stock_hk_hist()`, `akshare.stock_hk_spot()`
实时行情：`akshare.stock_zh_a_spot_em()`, `akshare.stock_hk_spot()`
