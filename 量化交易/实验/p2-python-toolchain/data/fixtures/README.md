# 离线教学数据

本目录的数据由 `tools/build_first_batch.py` 使用固定随机种子生成，只用于演示量化数据结构和算法：

- `daily_prices.csv`：6 个虚拟资产的日线 OHLCV、行业和复权收盘价。
- `intraday_5m.csv`：1 个虚拟 A 股标的的 5 分钟 OHLCV、成交额和带时区时间戳。
- `fixture_metadata.json`：生成参数、字段说明和文件摘要。

这些文件不是实际证券行情，也不用于说明任何资产的历史或未来收益。
