from concurrent.futures import ProcessPoolExecutor

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
