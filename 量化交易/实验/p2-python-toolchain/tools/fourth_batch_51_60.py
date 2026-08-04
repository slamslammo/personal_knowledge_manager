#!/usr/bin/env python
"""Build P2 lessons 51–60 and integrated labs L5–L6."""

from __future__ import annotations

from build_first_batch import COMMON_SETUP, LABS, NOTEBOOKS, code, md, write_notebook


PACKAGES = {
    51: "51_youtube-16Ypll6C4Is",
    52: "52_youtube-QtFJ1eiu_8o",
    53: "53_youtube-LGYrfTakPyM",
    54: "54_youtube-fad02SOf_Zw",
    55: "55_youtube-6y6MEAgElz0",
    56: "56_youtube-gKF2PotbNDU",
    57: "57_youtube-n6aFAoJ_xp4",
    58: "58_youtube-dnU4YmbMe68",
    59: "59_youtube-VvDcJnhVYeY",
    60: "60_youtube-2PGtdJ9pXfQ",
}


def source_note(number: int, title: str, data_note: str) -> str:
    return f"""
# 第 {number} 课｜{title}

本 Notebook 对应「365 天量化金融」第 {number} 课。课程方法来自本地完整视频、课件截图和本地 Whisper 口播整理；这里把它重建为可运行、可验证的量化工程教学实现。

- 图文口播：`/Users/mojiawen/Documents/学习资料归档/_暂存/pam-video-captures/365-days-quant-finance/{PACKAGES[number]}/index.html`
- 环境：`pkm-quant`
- 数据：{data_note}
- 状态：可运行学习稿；不代表生产交易系统
"""


def end_note(items: str) -> str:
    return f"""
## 方法边界与复用结论

{items}

本课首先保护数据正确性、时间一致性和可复现性，再讨论速度或自动化。局部代码通过不代表整套交易系统满足权限、监控、灾备和实盘延迟要求。
"""


def build_51():
    cells = [
        md(source_note(51, "装饰器、重试、缓存与资源边界", "离线模拟数据接口，不发起网络请求")),
        md("""
## 本节量化问题

计时、重试和缓存会横跨许多接口函数；上下文管理器负责确保文件或事务在异常时释放。目标是减少重复控制代码，同时让重试次数、缓存命中和异常仍然可观测。
"""),
        code(COMMON_SETUP),
        md("""
## 1. 计时装饰器必须在异常时也记录

装饰器接收函数并返回包装后的函数。`functools.wraps` 保留原函数名称和文档；`finally` 保证无论成功或失败都写入耗时记录。
"""),
        code("""
# 为任意函数增加计时证据，同时保留原函数元数据。
from functools import wraps
import time

timing_log = []

def timed(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        status = "ok"
        try:
            return function(*args, **kwargs)
        except Exception:
            status = "failed"
            raise
        finally:
            timing_log.append({
                "function": function.__name__,
                "status": status,
                "elapsed_ms": (time.perf_counter() - start) * 1000,
            })
    return wrapper

@timed
def compute_returns(prices):
    return prices.pct_change(fill_method=None)

small_prices = pd.Series([100.0, 101.0, 99.0])
display(compute_returns(small_prices))
display(pd.DataFrame(timing_log))
assert timing_log[-1]["function"] == "compute_returns"
"""),
        md("""
## 2. 重试只处理明确的暂时性异常

指数退避公式为 `wait_k = min(cap, base × 2^k)`。教学中把 `sleep` 注入为零等待函数，既能验证次数和间隔，又不拖慢 Notebook。下单、付款等非幂等操作不能盲目重试。
"""),
        code("""
# 模拟前两次超时、第三次成功，并记录退避序列。
def retry(max_attempts=3, base=0.1, cap=1.0, retry_on=(TimeoutError,), sleep=time.sleep):
    def decorate(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            waits = []
            for attempt in range(max_attempts):
                try:
                    return function(*args, **kwargs), waits
                except retry_on:
                    if attempt == max_attempts - 1:
                        raise
                    wait = min(cap, base * 2 ** attempt)
                    waits.append(wait)
                    sleep(wait)
        return wrapper
    return decorate

state = {"calls": 0}
@retry(max_attempts=4, base=0.25, cap=1.0, sleep=lambda seconds: None)
def flaky_fetch(symbol):
    state["calls"] += 1
    if state["calls"] < 3:
        raise TimeoutError("temporary")
    return {"symbol": symbol, "rows": 756}

payload, waits = flaky_fetch("DEMO_A")
print("结果:", payload, "等待计划:", waits, "调用次数:", state["calls"])
assert waits == [0.25, 0.5]
assert state["calls"] == 3
"""),
        md("""
## 3. 缓存键要包含数据版本和复权口径

函数参数相同不表示数据语义相同。缓存键还应包含 `as_of`、复权方式和适配器版本；命中率为 `hits / (hits + misses)`。
"""),
        code("""
# 构造版本化缓存，重复请求产生一次 miss 和一次 hit。
cache = {}
cache_stats = {"hits": 0, "misses": 0}

def cached_price(symbol, as_of, adjustment, adapter_version):
    key = (symbol, as_of, adjustment, adapter_version)
    if key in cache:
        cache_stats["hits"] += 1
        return cache[key]
    cache_stats["misses"] += 1
    value = {"symbol": symbol, "as_of": as_of, "price": 100.0, "adjustment": adjustment}
    cache[key] = value
    return value

first = cached_price("DEMO_A", "2025-01-02", "qfq", "v1")
second = cached_price("DEMO_A", "2025-01-02", "qfq", "v1")
hit_rate = cache_stats["hits"] / sum(cache_stats.values())
print("缓存统计:", cache_stats, "命中率:", hit_rate)
assert first is second
assert hit_rate == 0.5
"""),
        md("""
## 4. 上下文管理器保证异常时释放资源

`contextlib.contextmanager` 中 `yield` 前是获取资源，`finally` 是释放资源。下面故意抛错，退出记录仍然出现。
"""),
        code("""
# 捕获教学异常，并验证资源总会关闭。
from contextlib import contextmanager

resource_log = []
@contextmanager
def research_resource(name):
    resource_log.append(f"open:{name}")
    try:
        yield {"name": name}
    finally:
        resource_log.append(f"close:{name}")

try:
    with research_resource("snapshot") as resource:
        print("使用:", resource)
        raise ValueError("teaching failure")
except ValueError:
    print("已捕获教学异常")

print(resource_log)
assert resource_log == ["open:snapshot", "close:snapshot"]
"""),
        md(end_note("""
- 装饰器层数过多会隐藏控制流，必须输出计时、重试和缓存指标。
- 只有暂时性、幂等操作适合自动重试。
- 缓存必须有版本、失效条件、时区与公司行动更新策略。
""")),
    ]
    write_notebook(NOTEBOOKS / "51_装饰器重试缓存与资源边界.ipynb", cells)


def build_52():
    cells = [
        md(source_note(52, "asyncio 受控并发数据获取", "离线模拟网络延迟和逐标的失败")),
        md("""
## 本节量化问题

`asyncio` 在等待 I/O 时切换任务，适合多标的数据接口。它不加速 CPU 计算，也不能用无限并发绕过服务端限流。
"""),
        code(COMMON_SETUP),
        code("""
# asyncio、random 都来自 Python 标准库。
import asyncio
"""),
        md("""
## 1. coroutine、await 与事件循环

`async def` 调用后先得到协程对象；只有 `await` 后才真正执行。`await asyncio.sleep` 模拟网络等待，并把控制权交回事件循环。
"""),
        code("""
# 执行一个协程并检查返回结构；Jupyter 已有事件循环，所以直接 await。
async def fetch_one(symbol, delay=0.01):
    await asyncio.sleep(delay)
    return {"symbol": symbol, "rows": 10, "status": "ok"}

coroutine_object = fetch_one("DEMO_A")
print("调用后的对象类型:", type(coroutine_object).__name__)
single_result = await coroutine_object
print("await 结果:", single_result)
assert single_result["status"] == "ok"
"""),
        md("""
## 2. Semaphore 限制同时在途请求

即使同时创建很多任务，`async with semaphore` 只允许固定数量进入接口区。下面额外记录 `max_in_flight`，用证据验证并发上限。
"""),
        code("""
# 并发执行 6 个模拟请求，并验证最多只有 2 个同时在途。
state = {"in_flight": 0, "max_in_flight": 0}
semaphore = asyncio.Semaphore(2)

async def limited_fetch(symbol):
    async with semaphore:
        state["in_flight"] += 1
        state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
        try:
            await asyncio.sleep(0.015)
            if symbol == "FAIL_A":
                raise TimeoutError("simulated timeout")
            return {"symbol": symbol, "status": "ok", "rows": 10}
        except TimeoutError as exc:
            return {"symbol": symbol, "status": "failed", "rows": 0, "error": str(exc)}
        finally:
            state["in_flight"] -= 1

symbols = ["A", "B", "C", "FAIL_A", "D", "E"]
results = await asyncio.gather(*(limited_fetch(symbol) for symbol in symbols))
status = pd.DataFrame(results).sort_values("symbol").reset_index(drop=True)
display(status)
print("最大同时在途:", state["max_in_flight"])
assert state["max_in_flight"] == 2
assert status["status"].value_counts().to_dict() == {"ok": 5, "failed": 1}
"""),
        md("""
## 3. 超时属于逐请求状态

`asyncio.wait_for` 把单个请求限制在指定时长；一个任务超时不应让成功任务丢失。最终结果显式按代码排序，不能依赖完成顺序。
"""),
        code("""
# 给不同延迟的任务加统一超时，并保留每项状态。
async def with_timeout(symbol, delay, timeout):
    try:
        result = await asyncio.wait_for(fetch_one(symbol, delay), timeout=timeout)
        return result
    except asyncio.TimeoutError:
        return {"symbol": symbol, "rows": 0, "status": "timeout"}

timed_results = await asyncio.gather(
    with_timeout("FAST", 0.005, 0.02),
    with_timeout("SLOW", 0.04, 0.02),
)
timed_status = pd.DataFrame(timed_results).sort_values("symbol")
display(timed_status)
assert timed_status.set_index("symbol").loc["SLOW", "status"] == "timeout"
"""),
        md(end_note("""
- asyncio 适合 I/O-bound，不会加速占满 CPU 的回测循环。
- 并发量应服从数据源条款、限频和本地连接资源。
- 普通脚本可用 `asyncio.run(main())`；Jupyter 已有事件循环，应在单元格直接 `await`。
""")),
    ]
    write_notebook(NOTEBOOKS / "52_asyncio受控并发数据获取.ipynb", cells)


def build_53():
    cells = [
        md(source_note(53, "线程、进程与回测并行边界", "离线模拟 I/O 任务和确定性计算任务")),
        md("""
## 本节量化问题

先判断瓶颈是 I/O 等待还是 CPU 计算，再选择线程、进程或向量化。课程重点不是“核心越多越快”，而是任务粒度、序列化、随机种子和结果顺序。
"""),
        code(COMMON_SETUP),
        code("""
# concurrent.futures 属于标准库；本 Notebook 实际执行线程示例。
from concurrent.futures import ThreadPoolExecutor
import time
"""),
        md("""
## 1. ThreadPoolExecutor 适合 I/O 等待

每项任务仅等待 20ms。串行总时间约为任务数乘等待，线程池可在等待期间推进其他任务。性能只做现场测量，不写死加速倍数断言。
"""),
        code("""
# 比较 8 个模拟 I/O 请求的串行与线程执行。
def io_task(symbol):
    time.sleep(0.02)
    return {"symbol": symbol, "rows": 10}

symbols = [f"ASSET_{i}" for i in range(8)]
start = time.perf_counter()
serial = [io_task(symbol) for symbol in symbols]
serial_time = time.perf_counter() - start

start = time.perf_counter()
with ThreadPoolExecutor(max_workers=4) as executor:
    threaded = list(executor.map(io_task, symbols))
thread_time = time.perf_counter() - start

print(f"串行 {serial_time:.3f}s，线程 {thread_time:.3f}s，加速比 {serial_time / thread_time:.2f}x")
assert [item["symbol"] for item in threaded] == symbols
"""),
        md("""
## 2. CPU 任务先考虑 NumPy 向量化

纯 Python 循环受 GIL 影响；NumPy 在底层数值库中批量计算。线程不能自动让 Python 字节码并行，进程也可能被传输大数组的 Pickle 开销抵消。
"""),
        code("""
# 用相同输入比较 Python 循环与 NumPy 向量化，核对数值一致。
rng = np.random.default_rng(365)
array = rng.normal(size=300_000)

def python_sum_of_squares(values):
    total = 0.0
    for value in values:
        total += value * value
    return total

start = time.perf_counter()
python_result = python_sum_of_squares(array)
python_time = time.perf_counter() - start
start = time.perf_counter()
numpy_result = np.square(array).sum()
numpy_time = time.perf_counter() - start

print(f"Python {python_time:.4f}s，NumPy {numpy_time:.4f}s")
np.testing.assert_allclose(python_result, numpy_result, rtol=1e-12)
"""),
        md("""
## 3. Amdahl 定律给并行加速设上限

若可并行比例为 `f`，使用 p 个执行单元，理论上限为：

`S_p <= 1 / ((1-f) + f/p)`。

即使无限核心，串行部分仍然存在。
"""),
        code("""
# 比较不同并行比例和核心数的理论上限。
rows = []
for fraction in [0.50, 0.80, 0.95]:
    for workers in [2, 4, 8, 16]:
        speedup = 1 / ((1 - fraction) + fraction / workers)
        rows.append({
            "parallel_fraction": fraction,
            "workers": workers,
            "max_speedup": speedup,
            "efficiency": speedup / workers,
        })
amdahl = pd.DataFrame(rows)
display(amdahl.pivot(index="parallel_fraction", columns="workers", values="max_speedup").round(2))
assert amdahl["max_speedup"].gt(1).all()
"""),
        md("""
## 4. ProcessPool 的安全脚本模板

macOS/Jupyter 的进程启动语义与普通脚本不同，因此课程页不在内核中强行 fork。下面生成一个可从终端运行的独立脚本：计算函数定义在模块顶层，并用 `if __name__ == "__main__"` 保护入口。
"""),
        code("""
# 生成独立进程池模板，不在 Notebook 内核里启动子进程。
process_script = '''from concurrent.futures import ProcessPoolExecutor

def backtest_task(seed):
    total = 0
    for value in range(200_000):
        total += (value + seed) % 97
    return seed, total

if __name__ == "__main__":
    seeds = [365, 366, 367, 368]
    with ProcessPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(backtest_task, seeds))
    print(sorted(results))
'''
script_path = OUTPUT_DIR / "53_process_pool_example.py"
script_path.write_text(process_script, encoding="utf-8")
print(process_script)
assert 'if __name__ == "__main__":' in process_script
assert script_path.exists()
"""),
        md(end_note("""
- 小任务并行可能更慢；先剖析热点，再决定并行层级。
- BLAS、NumPy 或模型内部可能已多线程，外层进程池会过度订阅 CPU。
- 并行任务要派生独立随机种子，并显式排序结果；完成顺序不能参与策略逻辑。
""")),
    ]
    write_notebook(NOTEBOOKS / "53_线程进程与回测并行边界.ipynb", cells)


def build_54():
    cells = [
        md(source_note(54, "Numba 数值循环加速与验算", "固定随机种子的 NumPy 收益数组")),
        md("""
## 本节量化问题

Numba 把适合的数值循环即时编译成机器码。正确基准要把首次编译时间与预热后的运行时间分开，并用 Python 参考实现检查结果一致。
"""),
        code(COMMON_SETUP),
        code("""
# Numba 已进入统一 pkm-quant 环境。
import numba
from numba import njit
import time
print("Numba:", numba.__version__)
"""),
        md("""
## 1. 一个逐时点回撤循环

输入是 `float64` 净值数组，输出每个时点相对历史峰值的回撤。该算法有顺序依赖，不适合简单 `prange`，但很适合 `njit` 编译显式循环。
"""),
        code("""
# Python 参考实现和 Numba 实现保持完全相同的控制流。
def drawdown_python(nav):
    output = np.empty_like(nav)
    peak = nav[0]
    for i in range(len(nav)):
        if nav[i] > peak:
            peak = nav[i]
        output[i] = nav[i] / peak - 1.0
    return output

@njit
def drawdown_numba(nav):
    output = np.empty_like(nav)
    peak = nav[0]
    for i in range(len(nav)):
        if nav[i] > peak:
            peak = nav[i]
        output[i] = nav[i] / peak - 1.0
    return output

small_nav = np.array([1.00, 1.10, 1.05, 1.20, 1.08])
expected = np.array([0.0, 0.0, 1.05 / 1.10 - 1, 0.0, 1.08 / 1.20 - 1])
np.testing.assert_allclose(drawdown_python(small_nav), expected)
np.testing.assert_allclose(drawdown_numba(small_nav), expected)
display(pd.DataFrame({"nav": small_nav, "drawdown": expected}))
"""),
        md("""
## 2. 首次调用 = 编译 + 运行

第一次输入某种 dtype 时，Numba 要生成机器码；后续同类型调用才接近稳定运行时间。不能用首次 Numba 时间与已预热的 Python/NumPy 时间比较。
"""),
        code("""
# 分别记录首次编译调用和预热后的重复运行。
rng = np.random.default_rng(365)
returns = rng.normal(0.0002, 0.01, 500_000)
nav = np.cumprod(1 + returns).astype(np.float64)

start = time.perf_counter()
first_result = drawdown_numba(nav)
first_time = time.perf_counter() - start

start = time.perf_counter()
warmed_result = drawdown_numba(nav)
warmed_time = time.perf_counter() - start

start = time.perf_counter()
python_result = drawdown_python(nav)
python_time = time.perf_counter() - start

print(f"Numba 首次: {first_time:.4f}s")
print(f"Numba 预热后: {warmed_time:.4f}s")
print(f"Python 循环: {python_time:.4f}s")
print(f"本机预热加速比: {python_time / warmed_time:.1f}x")
np.testing.assert_allclose(first_result, python_result, rtol=1e-12, atol=1e-12)
np.testing.assert_allclose(warmed_result, python_result, rtol=1e-12, atol=1e-12)
"""),
        md("""
## 3. dtype 是编译签名的一部分

`float32` 与 `float64` 会形成不同签名，也可能带来不同舍入误差。性能优化后要明确 `rtol/atol`，不能因为结果“看起来差不多”就跳过验算。
"""),
        code("""
# 展示已编译签名，并用合理容差比较 float32。
float32_result = drawdown_numba(nav.astype(np.float32))
print("已编译签名:")
for signature in drawdown_numba.signatures:
    print(" ", signature)
np.testing.assert_allclose(float32_result, python_result, rtol=1e-5, atol=1e-6)
assert len(drawdown_numba.signatures) >= 2
"""),
        md(end_note("""
- Numba 最适合数值型 NumPy 数组和显式循环，不直接适合 Pandas/字符串/动态 Python 对象。
- 向量化 NumPy 已很快的代码未必能从 JIT 获益。
- 课程中的百倍加速不是保证；必须在目标硬件、真实数据量和预热后实测。
""")),
    ]
    write_notebook(NOTEBOOKS / "54_Numba数值循环加速与验算.ipynb", cells)


def build_55():
    cells = [
        md(source_note(55, "回测调试、不变量与未来函数审计", "离线模拟价格与故意错误的信号")),
        md("""
## 本节量化问题

异常漂亮的回测先当作错误线索。调试链条是：数据 → 特征 → 信号 → 持仓 → 成交 → 成本 → 净值，并用日志、断言和截断不变性测试定位问题。
"""),
        code(COMMON_SETUP),
        code("""
# logging 使用结构化字段记录关键状态；本课不进入交互式断点。
import logging
logger = logging.getLogger("lesson55")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
"""),
        md("""
## 1. shift 方向错误会直接读取未来收益

错误特征 `return.shift(-1)` 把明日收益放到今日。正确动量特征使用已经发生的过去收益；仓位再向后移动一日。
"""),
        code("""
# 并排展示未来泄漏信号与可执行信号。
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
prices = daily.query("symbol == 'TECH_A'").sort_values("date").set_index("date")["adj_close"]
asset_return = prices.pct_change(fill_method=None)
wrong_signal = (asset_return.shift(-1) > 0).astype(int)
past_signal = (asset_return.rolling(5, min_periods=5).mean() > 0).astype(int)
correct_position = past_signal.shift(1).fillna(0)
audit = pd.DataFrame({
    "return": asset_return,
    "wrong_future_signal": wrong_signal,
    "past_signal": past_signal,
    "correct_position": correct_position,
}).dropna().head(8)
display(audit)
assert audit["correct_position"].iloc[1] == audit["past_signal"].iloc[0]
"""),
        md("""
## 2. 截断不变性测试

若信号在 t 日只依赖 t 及以前数据，那么删除 t 之后的数据，不应改变截至 t 的信号。下面对正确函数和错误函数分别验证。
"""),
        code("""
# 比较完整序列与截断序列在共同历史上的输出。
def causal_signal(series):
    return (series.pct_change(fill_method=None).rolling(5, min_periods=5).mean() > 0).astype(int)

def leaky_signal(series):
    # 直接返回向前移动的未来收益，截断边界必然从“已知数值”变成 NaN。
    return series.pct_change(fill_method=None).shift(-1)

cut = 300
causal_full = causal_signal(prices).iloc[:cut]
causal_truncated = causal_signal(prices.iloc[:cut])
leaky_full = leaky_signal(prices).iloc[:cut]
leaky_truncated = leaky_signal(prices.iloc[:cut])

pd.testing.assert_series_equal(causal_full, causal_truncated)
leak_detected = not leaky_full.equals(leaky_truncated)
print("正确信号截断一致:", True)
print("错误信号检测到未来依赖:", leak_detected)
assert leak_detected
"""),
        md("""
## 3. 会计恒等式和成本单调性是不变量

组合权益应等于现金加持仓市值；在其他条件相同时，非负交易成本不应提高最终净值。
"""),
        code("""
# 用小型交易账本验证权益恒等式，并验证加成本后净值不更高。
ledger = pd.DataFrame({
    "cash": [1000.0, 500.0, 520.0],
    "position": [0, 5, 5],
    "price": [100.0, 100.0, 102.0],
    "equity": [1000.0, 1000.0, 1030.0],
})
ledger["calculated_equity"] = ledger["cash"] + ledger["position"] * ledger["price"]
np.testing.assert_allclose(ledger["equity"], ledger["calculated_equity"])

position = correct_position.reindex(asset_return.index).fillna(0)
gross = position * asset_return.fillna(0)
turnover = position.diff().abs().fillna(position.abs())
net = gross - turnover * 0.001
gross_nav = (1 + gross).cumprod()
net_nav = (1 + net).cumprod()
assert net_nav.iloc[-1] <= gross_nav.iloc[-1] + 1e-12
logger.info("final_gross=%.4f final_net=%.4f", gross_nav.iloc[-1], net_nav.iloc[-1])
display(ledger)
"""),
        md(end_note("""
- 调试器展示执行状态，但不能自动判断金融假设是否合理。
- 日志应含时间、标的、信号、委托、成交、成本和持仓，同时控制级别避免淹没信息。
- 修复错误导致收益下降是正常结果；修复后仍需独立样本外验证。
""")),
    ]
    write_notebook(NOTEBOOKS / "55_回测调试与未来函数审计.ipynb", cells)


def build_56():
    cells = [
        md(source_note(56, "pytest 量化单元测试", "可手算的小型合成价格、信号和成本")),
        md("""
## 本节量化问题

单元测试把收益公式、信号滞后、手续费和会计规则变成自动护栏。本节先在 Notebook 展示 AAA 模式，再生成一个真正由 pytest 执行的测试文件。
"""),
        code(COMMON_SETUP),
        code("""
# pytest 已进入统一环境；subprocess 用同一解释器运行测试。
import pytest
import subprocess
import textwrap
print("pytest:", pytest.__version__)
"""),
        md("""
## 1. AAA：Arrange、Act、Assert

下面价格从 100 到 110 再到 99，日收益应为 10% 和 -10%。期望值来自手算，不来自待测函数自身。
"""),
        code("""
# Arrange：准备价格；Act：计算收益；Assert：与手算期望比较。
def simple_returns(prices):
    prices = np.asarray(prices, dtype=float)
    if len(prices) < 2:
        return np.array([], dtype=float)
    return prices[1:] / prices[:-1] - 1

prices = np.array([100.0, 110.0, 99.0])
actual = simple_returns(prices)
expected = np.array([0.10, -0.10])
np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)
print("实际:", actual, "期望:", expected)
"""),
        md("""
## 2. 参数化测试覆盖正常值、空样本和零分母

价格为零不应悄悄得到无穷大，因此稳健函数显式拒绝非正价格。`pytest.raises` 验证预期异常。
"""),
        code("""
# 定义带输入契约的收益函数，并在 Notebook 中直接检查边界。
def validated_returns(prices):
    values = np.asarray(prices, dtype=float)
    if np.any(values <= 0):
        raise ValueError("prices must be positive")
    return simple_returns(values)

assert validated_returns([100.0]).size == 0
with pytest.raises(ValueError, match="positive"):
    validated_returns([100.0, 0.0])
"""),
        md("""
## 3. 生成并实际运行 pytest 文件

测试覆盖：

- 可手算收益；
- 参数化边界；
- 持仓必须使用上一期信号；
- 成本后终值不高于无成本终值。
"""),
        code("""
# 写入独立测试文件，并用当前 pkm-quant 解释器运行。
test_source = textwrap.dedent('''
import numpy as np
import pytest

def simple_returns(prices):
    values = np.asarray(prices, dtype=float)
    if np.any(values <= 0):
        raise ValueError("prices must be positive")
    return values[1:] / values[:-1] - 1

@pytest.mark.parametrize("prices, expected", [
    ([100.0, 110.0], [0.10]),
    ([100.0], []),
    ([100.0, 90.0, 99.0], [-0.10, 0.10]),
])
def test_returns(prices, expected):
    np.testing.assert_allclose(simple_returns(prices), expected, rtol=1e-12, atol=1e-12)

def test_zero_price_rejected():
    with pytest.raises(ValueError):
        simple_returns([100.0, 0.0])

def test_signal_is_lagged_and_cost_is_monotone():
    signal = np.array([1.0, 0.0, 1.0])
    position = np.r_[0.0, signal[:-1]]
    returns = np.array([0.01, -0.02, 0.03])
    gross = position * returns
    turnover = np.abs(np.diff(np.r_[0.0, position]))
    net = gross - 0.001 * turnover
    assert position[1] == signal[0]
    assert np.prod(1 + net) <= np.prod(1 + gross)
''')
test_path = OUTPUT_DIR / "56_test_quant_core.py"
test_path.write_text(test_source, encoding="utf-8")
completed = subprocess.run(
    [sys.executable, "-m", "pytest", "-q", str(test_path)],
    capture_output=True, text=True, check=False,
)
print(completed.stdout)
if completed.stderr:
    print(completed.stderr)
assert completed.returncode == 0
"""),
        md(end_note("""
- 测试通过只保护已经声明的行为；未覆盖的错误仍然存在。
- 期望值应来自定义、手算或独立参考实现，不能把当前输出复制成“正确答案”。
- 网络接口契约测试和纯计算单元测试应分开，避免外部不稳定污染核心测试。
""")),
    ]
    write_notebook(NOTEBOOKS / "56_pytest量化单元测试.ipynb", cells)


def build_57():
    cells = [
        md(source_note(57, "Git 实验版本与结果追踪", "本地项目元数据；Notebook 不执行提交或历史修改")),
        md("""
## 本节量化问题

Git 版本化代码，但可复现实验还需要数据哈希、配置和环境版本。本课只读取 Git 状态并生成实验清单，不执行 `add/commit/revert`。
"""),
        code(COMMON_SETUP),
        code("""
# subprocess 以参数数组执行只读 Git 命令，避免 shell 拼接。
import subprocess
import hashlib
import importlib.metadata as metadata
"""),
        md("""
## 1. 工作区、暂存区和提交是三个状态

- `git diff`：工作区相对暂存区；
- `git diff --staged`：暂存区相对最新提交；
- `git log` / SHA：已提交历史。

本 Notebook 不替用户决定提交范围。
"""),
        code("""
# 读取 Git 版本和当前项目是否位于仓库，不修改任何状态。
git_version = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True).stdout.strip()
probe = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"],
    cwd=PROJECT_ROOT,
    capture_output=True, text=True, check=False,
)
repository_root = probe.stdout.strip() if probe.returncode == 0 else None
print("Git:", git_version)
print("仓库根:", repository_root or "当前 P2 目录不在 Git 仓库中")
"""),
        md("""
## 2. 实验引用由四部分组成

`commit_sha + config_sha256 + data_sha256 + packages`。即使当前目录尚未提交，清单也明确记录 `commit_sha=null`，避免误以为已经版本化。
"""),
        code("""
# 生成不依赖 Git 是否存在的实验清单。
commit_probe = subprocess.run(
    ["git", "rev-parse", "HEAD"],
    cwd=PROJECT_ROOT,
    capture_output=True, text=True, check=False,
)
commit_sha = commit_probe.stdout.strip() if commit_probe.returncode == 0 else None
config = {"lesson": 57, "symbol": "DEMO_A", "cost_bps": 10}
config_text = json.dumps(config, ensure_ascii=False, sort_keys=True)
data_path = DATA_DIR / "daily_prices.csv"
manifest = {
    "commit_sha": commit_sha,
    "config": config,
    "config_sha256": hashlib.sha256(config_text.encode()).hexdigest(),
    "data_file": data_path.name,
    "data_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
    "packages": {
        name: metadata.version(name)
        for name in ["numpy", "pandas", "scipy", "scikit-learn"]
    },
}
manifest_path = OUTPUT_DIR / "57_experiment_manifest.json"
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
display(pd.Series({k: v for k, v in manifest.items() if k != "packages"}, name="value").to_frame())
assert len(manifest["data_sha256"]) == 64
"""),
        md("""
## 3. `.gitignore` 排除大文件与秘密，但保留清单

原始行情、视频、环境目录、缓存和密钥不进入普通 Git 历史；可提交的是数据说明、schema、下载参数和哈希。
"""),
        code("""
# 生成教学用 ignore 模板，不覆盖项目现有 .gitignore。
ignore_template = """ + '"""' + """
.env
.venv/
__pycache__/
.ipynb_checkpoints/
data/raw/
*.mp4
*.parquet
*.sqlite
outputs/
!.gitkeep
""" + '"""' + """
ignore_path = OUTPUT_DIR / "57_gitignore_template.txt"
ignore_path.write_text(ignore_template.strip() + "\\n", encoding="utf-8")
print(ignore_template)
assert ".env" in ignore_template and "*.mp4" in ignore_template
"""),
        md(end_note("""
- Git 版本化代码不等于版本化数据或环境。
- 密钥一旦提交，即使后来删除仍可能留在历史中；敏感信息从一开始就不能进入仓库。
- 恢复共享历史优先使用可追溯的 `git revert`，不要随意强制改写。
""")),
    ]
    write_notebook(NOTEBOOKS / "57_Git实验版本与结果追踪.ipynb", cells)


def build_58():
    cells = [
        md(source_note(58, "Docker 可复现研究环境设计", "生成 Dockerfile 与忽略清单，不启动 Docker")),
        md("""
## 本节量化问题

Docker 镜像封装 Linux 用户空间、Python 和依赖；数据、密钥和输出通过挂载或 secret 进入。Notebook 生成并静态检查最小 Docker 配置，不假设本机已经启动 Docker Desktop。
"""),
        code(COMMON_SETUP),
        md("""
## 1. Dockerfile 的分层顺序影响缓存

先复制依赖锁文件并安装，后复制代码。只改代码时可以复用依赖层。镜像内使用非 root 用户，运行命令只生成本地报告。
"""),
        code("""
# 生成最小研究镜像配置。
dockerfile = '''FROM python:3.11-slim

WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r requirements.lock

RUN useradd --create-home quant
COPY --chown=quant:quant src/ /app/src/
USER quant

CMD ["python", "-m", "src.monthly_report"]
'''
dockerfile_path = OUTPUT_DIR / "58_Dockerfile.example"
dockerfile_path.write_text(dockerfile, encoding="utf-8")
print(dockerfile)
assert dockerfile.index("COPY requirements.lock") < dockerfile.index("COPY --chown=quant:quant src/")
assert "USER quant" in dockerfile
"""),
        md("""
## 2. 原始数据、输出和密钥不进入镜像

`.dockerignore` 缩小构建上下文；真实数据通过只读挂载 `/data:ro`，输出挂载 `/outputs`。密钥不写入 Dockerfile 或镜像层。
"""),
        code("""
# 生成 .dockerignore 与可复制的 build/run 命令。
dockerignore = '''.git
.env
.venv
__pycache__
data/
outputs/
*.mp4
*.sqlite
'''
ignore_path = OUTPUT_DIR / "58_dockerignore.example"
ignore_path.write_text(dockerignore, encoding="utf-8")
commands = pd.Series({
    "build": "docker build -f 58_Dockerfile.example -t pkm-quant:p2 .",
    "run": "docker run --rm -v $PWD/data:/data:ro -v $PWD/outputs:/outputs pkm-quant:p2",
}, name="command")
display(commands.to_frame())
assert ".env" in dockerignore
assert "/data:ro" in commands["run"]
"""),
        md("""
## 3. 静态安全检查

检查 Dockerfile 没有复制 `.env`、原始数据或 outputs，也没有使用 `ARG SECRET`。这是最低限度检查，不替代镜像扫描。
"""),
        code("""
# 对生成配置执行确定性的静态规则。
forbidden = ["COPY .env", "COPY data", "COPY outputs", "ARG SECRET", "ENV API_KEY"]
violations = [token for token in forbidden if token in dockerfile]
audit = pd.Series({
    "forbidden_instructions": len(violations),
    "non_root_user": "USER quant" in dockerfile,
    "dependency_lock_first": dockerfile.index("requirements.lock") < dockerfile.index("src/"),
    "data_ignored": "data/" in dockerignore,
    "secrets_ignored": ".env" in dockerignore,
})
display(audit.to_frame("result"))
assert not violations
assert audit.drop("forbidden_instructions").all()
"""),
        md(end_note("""
- 容器共享宿主机内核，不等于虚拟机；macOS 上还经过 Linux 虚拟化层。
- 相同镜像不能消除 CPU 架构、线程库、时区和外部数据变化。
- 生产镜像还应固定摘要 digest、扫描漏洞，并以 secret 管理敏感配置。
""")),
    ]
    write_notebook(NOTEBOOKS / "58_Docker可复现研究环境设计.ipynb", cells)


def build_59():
    cells = [
        md(source_note(59, "自动月报流水线与幂等交付", "离线模拟多资产日线；生成本地 HTML 月报")),
        md("""
## 本节量化问题

月报流水线分为 Extract → Validate → Compute → Render → Publish。这里的 Publish 仅指写入本地输出目录，不向任何人或外部系统发送。
"""),
        code(COMMON_SETUP),
        code("""
# Jinja2 只负责模板渲染，指标仍由独立计算函数产生。
from jinja2 import Template
import hashlib
"""),
        md("""
## 1. 报告期间由 `as_of_date` 显式确定

取数据中最后一个完整月份作为报告月。`period_start/period_end` 不是“最近 30 行”，而是自然月边界。
"""),
        code("""
# 提取最后一个完整自然月的模拟价格。
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
wide = daily.pivot(index="date", columns="symbol", values="adj_close").sort_index()
last_date = wide.index.max()
as_of_date = last_date
period = as_of_date.to_period("M")
period_start = period.start_time
period_end = period.end_time
monthly_prices = wide.loc[period_start:period_end]

print("报告期间:", period_start.date(), "→", period_end.date())
print("交易日:", len(monthly_prices))
assert len(monthly_prices) >= 15
assert monthly_prices.notna().all().all()
"""),
        md("""
## 2. Compute 层统一指标口径

- 月收益：`P_end / P_start - 1`；
- 日收益年化波动：`std(r_daily) × sqrt(252)`；
- 最大回撤：`min(NAV / cumulative_max(NAV) - 1)`；
- 等权基准：每日六只资产简单收益的均值。
"""),
        code("""
# 从同一月度价格对象计算全部指标。
daily_return = monthly_prices.pct_change(fill_method=None).dropna()
nav = monthly_prices / monthly_prices.iloc[0]
drawdown = nav / nav.cummax() - 1
metrics = pd.DataFrame({
    "monthly_return": monthly_prices.iloc[-1] / monthly_prices.iloc[0] - 1,
    "annualized_volatility": daily_return.std(ddof=1) * np.sqrt(252),
    "max_drawdown": drawdown.min(),
})
benchmark_return = (1 + daily_return.mean(axis=1)).prod() - 1
metrics["excess_vs_equal_weight"] = metrics["monthly_return"] - benchmark_return
display(metrics.style.format("{:.2%}"))
assert metrics.index.equals(monthly_prices.columns)
"""),
        md("""
## 3. Render 层只消费已校验结果

图表、表格和文字都来自 `metrics/nav`。同一参数重复渲染应得到相同字节哈希。
"""),
        code("""
# 保存净值图，并用 Jinja2 渲染自包含本地报告。
axis = nav.plot(figsize=(9, 4), title=f"{period} 月度净值（模拟数据）")
axis.set(xlabel="日期", ylabel="月初=1")
axis.grid(alpha=0.2)
axis.figure.tight_layout()
chart_path = OUTPUT_DIR / "59_monthly_nav.png"
axis.figure.savefig(chart_path, dpi=150)
plt.close(axis.figure)

template = Template('''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8">
<title>{{ period }} 量化月报</title>
<style>body{font:16px/1.65 -apple-system,"PingFang SC",sans-serif;max-width:1000px;margin:40px auto;padding:0 24px}table{border-collapse:collapse;width:100%}th,td{padding:8px;border-bottom:1px solid #ddd;text-align:right}th:first-child,td:first-child{text-align:left}img{max-width:100%}.note{color:#666}</style>
<h1>{{ period }} 量化研究月报</h1>
<p class="note">数据：固定模拟行情；本报告不是投资建议。期间 {{ start }} 至 {{ end }}。</p>
{{ table }}
<img src="{{ chart }}" alt="月度净值图">
</html>''')

def render_report():
    return template.render(
        period=str(period), start=str(period_start.date()), end=str(period_end.date()),
        table=metrics.to_html(float_format=lambda value: f"{value:.2%}"),
        chart=chart_path.name,
    )

html_first = render_report()
html_second = render_report()
hash_first = hashlib.sha256(html_first.encode()).hexdigest()
hash_second = hashlib.sha256(html_second.encode()).hexdigest()
report_path = OUTPUT_DIR / "59_monthly_report.html"
report_path.write_text(html_first, encoding="utf-8")
print("报告:", report_path)
assert hash_first == hash_second
assert report_path.exists() and chart_path.exists()
"""),
        md("""
## 4. 清单与失败闸门

空数据、未闭合期间或缺失资产应在 Validate 阶段失败，而不是发布空白报告。清单记录日期、输入哈希和产物哈希。
"""),
        code("""
# 保存可追溯交付清单。
input_path = DATA_DIR / "daily_prices.csv"
manifest = {
    "lesson": 59,
    "as_of_date": str(as_of_date.date()),
    "period_start": str(period_start.date()),
    "period_end": str(period_end.date()),
    "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
    "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
    "report": report_path.name,
    "chart": chart_path.name,
    "status": "ready-local",
}
manifest_path = OUTPUT_DIR / "59_monthly_manifest.json"
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
display(pd.Series(manifest, name="value").to_frame())
assert len(manifest["report_sha256"]) == 64
"""),
        md(end_note("""
- Cron 只负责触发；脚本本身仍需失败退出码、日志、告警和重跑机制。
- 自动排版成功不能证明指标正确，Compute 层应有独立测试和对账。
- 本课只生成本地文件；向外发送或发布需要单独授权。
""")),
    ]
    write_notebook(NOTEBOOKS / "59_自动月报流水线与幂等交付.ipynb", cells)


def build_60():
    cells = [
        md(source_note(60, "P2 工具链总结与完成度审计", "本地 P2 项目文件、环境版本和产物清单")),
        md("""
## 本节量化问题

P2 的目标不是记住库名，而是形成可替换研究链：

```text
数据适配 → 存储 → 清洗/特征 → 统计/模型 → 验证 → 报告
```

本节把工具映射到职责，并自动检查 31–60 课和 L1–L6 是否都有文件。
"""),
        code(COMMON_SETUP),
        code("""
# importlib.metadata 读取已安装版本，hashlib 生成项目清单。
import importlib.metadata as metadata
import hashlib
"""),
        md("""
## 1. 工具选择服从瓶颈类型

总耗时可拆为 `T_total = T_data + T_compute + T_validation + T_report`。先识别最大且可控的部分，再选择 asyncio、Numba、缓存或报告模板。
"""),
        code("""
# 建立课程工具与量化职责映射。
tool_map = pd.DataFrame([
    ("NumPy / pandas", "数值与标签计算", "收益、矩阵、时间对齐"),
    ("Matplotlib / Plotly / mplfinance", "诊断展示", "静态图、交互图、K线"),
    ("yfinance / AkShare adapter", "数据适配", "字段、复权、失败状态"),
    ("SQLite", "单机研究存储", "唯一键、UPSERT、查询"),
    ("SciPy / statsmodels / sklearn", "统计与模型", "厚尾、归因、时序预测"),
    ("asyncio / threads", "I/O 等待", "受控并发获取"),
    ("Numba", "数值热点", "预热后的显式循环"),
    ("pytest / Git / Docker", "质量与复现", "测试、版本、环境"),
    ("Jinja2", "交付", "本地自动月报"),
], columns=["工具", "职责", "量化使用"])
display(tool_map)
"""),
        md("""
## 2. 自动检查课程和综合实验文件

逐课 Notebook 的主键是课程编号；综合实验主键是 L1–L6。只检查文件存在不等于执行通过，完整验收还要结合 `notebook-validation.json`。
"""),
        code("""
# 检查 30 个逐课 Notebook 和 6 个实验 Notebook 的文件覆盖。
lesson_paths = sorted((PROJECT_ROOT / "notebooks").glob("*.ipynb"))
lab_paths = sorted((PROJECT_ROOT / "labs").glob("*.ipynb"))
lesson_numbers = {int(path.name.split("_", 1)[0]) for path in lesson_paths}
lab_ids = {path.name.split("_", 1)[0] for path in lab_paths}
missing_lessons = sorted(set(range(31, 61)) - lesson_numbers)
missing_labs = sorted({f"L{i}" for i in range(1, 7)} - lab_ids)

coverage = pd.Series({
    "lesson_notebooks": len(lesson_paths),
    "lab_notebooks": len(lab_paths),
    "missing_lessons": missing_lessons,
    "missing_labs": missing_labs,
})
display(coverage.to_frame("value"))
assert len(lesson_paths) == 30 and not missing_lessons
assert len(lab_paths) == 6 and not missing_labs
"""),
        md("""
## 3. 环境版本与 P2 完成清单

清单保存关键依赖版本和所有 Notebook 的 SHA-256。任何 Notebook 内容变化都会反映在下一次清单中。
"""),
        code("""
# 生成 P2 完成清单；不把文件名等同于执行通过。
packages = [
    "numpy", "pandas", "matplotlib", "scipy", "scikit-learn",
    "statsmodels", "numba", "pytest", "jinja2", "plotly", "mplfinance",
    "yfinance", "akshare",
]
versions = {package: metadata.version(package) for package in packages}
notebook_hashes = {
    str(path.relative_to(PROJECT_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in [*lesson_paths, *lab_paths]
}
validation_path = PROJECT_ROOT / "notebook-validation.json"
validation = json.loads(validation_path.read_text(encoding="utf-8")) if validation_path.exists() else {}
validation_passed = validation.get("status") == "pass" and validation.get("notebook_count") == 36
manifest = {
    "phase": "P2",
    "status": "validated-pass" if validation_passed else "notebooks-built",
    "lessons": len(lesson_paths),
    "labs": len(lab_paths),
    "validation_report": validation_path.name if validation_passed else None,
    "packages": versions,
    "notebook_sha256": notebook_hashes,
}
manifest_path = OUTPUT_DIR / "60_p2_completion_manifest.json"
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
display(pd.Series({**versions, "full_validation": validation_passed}, name="version/status").to_frame())
assert len(notebook_hashes) == 36
"""),
        md(end_note("""
- 更多工具会增加兼容和认知成本；稳定接口比工具数量重要。
- 性能优化不能优先于无未来信息、数据正确性和成本建模。
- P2 完成代表工具链学习闭环，不代表已经具备生产实盘系统。
""")),
    ]
    write_notebook(NOTEBOOKS / "60_P2工具链总结与完成度审计.ipynb", cells)


def build_l5():
    cells = [
        md("""
# L5 综合实验｜可测试的量化任务执行器

本实验整合第 51–58 课：计时与重试 → 受控并发 → 数值热点 JIT → 不变量 → pytest → 版本与容器配置清单。

- 环境：`pkm-quant`
- 数据：离线模拟任务
- 输出：`outputs/L5_engineering_audit.json`
"""),
        md("""
## 验收

1. 暂时失败可重试且次数可见；
2. 异步并发有 Semaphore 上限；
3. Numba 与 Python 参考结果一致；
4. 无未来信息和成本单调性由断言保护；
5. 产物记录依赖版本、数据哈希和部署配置状态。
"""),
        code(COMMON_SETUP),
        code("""
# 导入工程实验所需的标准库和 Numba。
import asyncio
import hashlib
import importlib.metadata as metadata
import time
from numba import njit
"""),
        md("""
## 1. 受控并发任务保留逐项状态
"""),
        code("""
# 并发执行模拟数据任务，最多 3 个同时在途。
semaphore = asyncio.Semaphore(3)
state = {"in_flight": 0, "max_in_flight": 0}

async def task(symbol):
    async with semaphore:
        state["in_flight"] += 1
        state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
        start = time.perf_counter()
        try:
            await asyncio.sleep(0.01)
            if symbol == "FAIL":
                raise TimeoutError("simulated")
            return {"symbol": symbol, "status": "ok", "elapsed_ms": (time.perf_counter() - start) * 1000}
        except TimeoutError as exc:
            return {"symbol": symbol, "status": "failed", "error": str(exc)}
        finally:
            state["in_flight"] -= 1

symbols = ["A", "B", "C", "D", "FAIL", "E"]
statuses = pd.DataFrame(await asyncio.gather(*(task(symbol) for symbol in symbols)))
display(statuses)
assert state["max_in_flight"] == 3
assert statuses["status"].value_counts().to_dict() == {"ok": 5, "failed": 1}
"""),
        md("""
## 2. 数值热点保持参考实现与 JIT 实现
"""),
        code("""
# 编译组合收益累积循环，并与 NumPy 参考结果逐项比较。
def nav_python(returns):
    output = np.empty(len(returns))
    value = 1.0
    for i, item in enumerate(returns):
        value *= 1.0 + item
        output[i] = value
    return output

@njit
def nav_numba(returns):
    output = np.empty(len(returns))
    value = 1.0
    for i in range(len(returns)):
        value *= 1.0 + returns[i]
        output[i] = value
    return output

rng = np.random.default_rng(365)
returns = rng.normal(0.0002, 0.01, 100_000)
reference = nav_python(returns)
jitted = nav_numba(returns)
np.testing.assert_allclose(jitted, reference, rtol=1e-12, atol=1e-12)
print("最终净值:", jitted[-1], "编译签名:", nav_numba.signatures)
"""),
        md("""
## 3. 量化不变量与可追溯清单
"""),
        code("""
# 验证成本单调性，并保存工程质量审计。
signal = (returns > 0).astype(float)
position = np.r_[0.0, signal[:-1]]
gross = position * returns
turnover = np.abs(np.diff(np.r_[0.0, position]))
net = gross - 0.001 * turnover
assert np.prod(1 + net) <= np.prod(1 + gross) + 1e-12

data_path = DATA_DIR / "daily_prices.csv"
audit = {
    "lab": "L5",
    "async_max_in_flight": state["max_in_flight"],
    "task_status": statuses.fillna("").to_dict(orient="records"),
    "numba_matches_reference": bool(np.allclose(jitted, reference)),
    "cost_monotonicity": True,
    "data_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
    "versions": {
        package: metadata.version(package)
        for package in ["numpy", "numba", "pytest"]
    },
    "git_manifest": "57_experiment_manifest.json",
    "dockerfile": "58_Dockerfile.example",
}
audit_path = OUTPUT_DIR / "L5_engineering_audit.json"
audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
display(pd.Series({k: v for k, v in audit.items() if k != "task_status"}, name="value").to_frame())
assert audit_path.exists()
"""),
        md(end_note("""
- L5 验证的是可测试工程骨架，不是生产调度系统。
- 并发、JIT 和容器只有在正确性测试通过后才应引入。
- 外部接口、部署、密钥和自动发布仍需独立权限与监控设计。
""")),
    ]
    write_notebook(LABS / "L5_可测试的量化计算模块.ipynb", cells)


def build_l6():
    cells = [
        md("""
# L6 综合实验｜一键生成可追溯月报

本实验整合第 59–60 课，用单一入口执行 Extract → Validate → Compute → Render → Archive，并生成 HTML、图表和 JSON 清单。

- 数据：固定模拟行情；非真实证券
- 输出：`outputs/L6_monthly_report.html/png/json`
- 发布边界：仅写本地文件，不发送、不上传
"""),
        md("""
## 验收

- 显式报告期间和数据完整性；
- 指标、图表、HTML 共享同一结果对象；
- 同一输入重复渲染字节一致；
- 清单包含数据、报告和图表哈希；
- 异常在发布前阻断。
"""),
        code(COMMON_SETUP),
        code("""
# 模板和哈希工具。
from jinja2 import Template
import hashlib
"""),
        md("""
## 1. 单一函数返回结构化结果，而不是直接散落写文件
"""),
        code("""
# Extract、Validate 和 Compute 形成纯数据结果。
def compute_monthly_bundle(as_of_date):
    daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
    prices = daily.pivot(index="date", columns="symbol", values="adj_close").sort_index()
    period = pd.Timestamp(as_of_date).to_period("M")
    sample = prices.loc[period.start_time:period.end_time]
    if len(sample) < 15 or sample.isna().any().any():
        raise ValueError("报告期数据未闭合或不完整")
    daily_return = sample.pct_change(fill_method=None).dropna()
    nav = sample / sample.iloc[0]
    drawdown = nav / nav.cummax() - 1
    metrics = pd.DataFrame({
        "return": sample.iloc[-1] / sample.iloc[0] - 1,
        "volatility": daily_return.std() * np.sqrt(252),
        "max_drawdown": drawdown.min(),
    })
    return {"period": str(period), "prices": sample, "nav": nav, "metrics": metrics}

source_dates = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])["date"]
bundle = compute_monthly_bundle(source_dates.max())
display(bundle["metrics"].style.format("{:.2%}"))
assert len(bundle["metrics"]) == 6
"""),
        md("""
## 2. Render 与 Archive 使用同一个 bundle
"""),
        code("""
# 生成图表和 HTML；不重新计算指标。
axis = bundle["nav"].plot(figsize=(9, 4), title=f"L6 {bundle['period']} 月度净值（模拟数据）")
axis.set(xlabel="日期", ylabel="月初=1")
axis.grid(alpha=0.2)
axis.figure.tight_layout()
chart_path = OUTPUT_DIR / "L6_monthly_report.png"
axis.figure.savefig(chart_path, dpi=150)
plt.close(axis.figure)

template = Template('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>L6 {{ period }} 月报</title><style>body{font:16px/1.6 -apple-system,"PingFang SC",sans-serif;max-width:980px;margin:40px auto;padding:0 24px}table{border-collapse:collapse;width:100%}th,td{padding:8px;border-bottom:1px solid #ddd;text-align:right}img{max-width:100%}</style>
<h1>{{ period }} 月报</h1><p>固定模拟数据，仅用于验证自动化交付。</p>
{{ table }}<img src="{{ chart }}" alt="月度净值"></html>''')
html = template.render(
    period=bundle["period"],
    table=bundle["metrics"].to_html(float_format=lambda value: f"{value:.2%}"),
    chart=chart_path.name,
)
report_path = OUTPUT_DIR / "L6_monthly_report.html"
report_path.write_text(html, encoding="utf-8")
assert report_path.exists() and chart_path.exists()
"""),
        md("""
## 3. 哈希清单完成本地交付
"""),
        code("""
# 记录输入与产物哈希，重复读取验证文件没有写坏。
data_path = DATA_DIR / "daily_prices.csv"
manifest = {
    "lab": "L6",
    "period": bundle["period"],
    "status": "ready-local",
    "data_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
    "report": report_path.name,
    "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
    "chart": chart_path.name,
    "chart_sha256": hashlib.sha256(chart_path.read_bytes()).hexdigest(),
}
manifest_path = OUTPUT_DIR / "L6_monthly_report.json"
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
display(pd.Series(manifest, name="value").to_frame())
assert all(len(manifest[key]) == 64 for key in ["data_sha256", "report_sha256", "chart_sha256"])
"""),
        md(end_note("""
- 自动生成不等于自动正确；数据不完整时必须在 Render 前失败。
- 本地 HTML 排版成功不替代指标单元测试和财务对账。
- 对外发布、通知接收者或写入外部系统需要另行授权。
""")),
    ]
    write_notebook(LABS / "L6_一键生成月报.ipynb", cells)


def main():
    build_51()
    build_52()
    build_53()
    build_54()
    build_55()
    build_56()
    build_57()
    build_58()
    build_59()
    build_l5()
    build_l6()
    build_60()


if __name__ == "__main__":
    main()
