"""检查 pkm-quant 是否具备课程所需的本地运行能力。

用法：
    conda activate pkm-quant
    python 实验/scripts/check_environment.py

本脚本只做本地导入和绘图检查，不请求外部行情接口。
"""

# %% 导入课程依赖
import importlib
import sys


PACKAGES = {
    "numpy": "numpy",
    "pandas": "pandas",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "scikit-learn": "sklearn",
    "yfinance": "yfinance",
    "akshare": "akshare",
    "jupyterlab": "jupyterlab",
}


def package_version(import_name: str) -> str:
    module = importlib.import_module(import_name)
    return getattr(module, "__version__", "已导入，未暴露版本号")


print(f"Python: {sys.version.split()[0]}")
for label, import_name in PACKAGES.items():
    print(f"{label}: {package_version(import_name)}")


# %% 使用无界面后端验证 Matplotlib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

figure, axis = plt.subplots()
axis.plot([1, 2, 3], [1, 4, 9])
axis.set_title("pkm-quant environment check")
plt.close(figure)

print("本地导入与绘图检查通过。")
