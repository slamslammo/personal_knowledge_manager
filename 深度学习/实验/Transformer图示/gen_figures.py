# -*- coding: utf-8 -*-
"""
注意力 → Transformer 加厚 · 配图复现
====================================

配套知识点:
  - 知识库/04-深度学习/05a-输入表示.md      (词元 / 嵌入 / 位置编码)
  - 知识库/04-深度学习/05b-掩码自注意力.md   (因果掩码)
  - 知识库/04-深度学习/05c-语言建模.md       (下一个 token 预测 + 交叉熵)

生成 4 张图到 ./figures/:
  - pos-encoding.png    正弦位置编码热图 + 频率随维度变化     —— 真实计算
  - embed-pipeline.png  文本 → 词元 → id → 嵌入 → 加位置      —— 示意图
  - causal-mask.png     原始分数 → 加因果掩码 → softmax 权重   —— 真实计算
  - lm-next-token.png   自回归下一个 token 预测 + 交叉熵       —— 示意 + 真实 softmax

其中位置编码与因果掩码两图为真实数值计算(公式直接算出),可逐像素复现;
输入流水线与自回归两图为解释性示意图(标注「示意」),数值仅为演示。

运行: python gen_figures.py        # 生成全部图到 ./figures/
依赖: numpy, matplotlib(中文标签需系统装有 CJK 字体,见 README)
"""

# %% 全局设置 -----------------------------------------------------------------
import os
import numpy as np
import matplotlib
matplotlib.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang SC", "Heiti TC", "STHeiti", "Microsoft YaHei", "sans-serif"]
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

C0, C1, BG = "#2f74d0", "#d04a3a", "#ffffff"     # 蓝 / 红 / 背景(与本库其它图一致)
INK, SUB, LINE = "#23211c", "#6b6860", "#cccccc"
FIG_DIR = "figures"
os.makedirs(FIG_DIR, exist_ok=True)


def box(ax, cx, cy, text, fc, ec, w=1.05, h=0.66, fs=11, tc=INK):
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                                boxstyle="round,pad=0.015,rounding_size=0.10",
                                fc=fc, ec=ec, lw=1.2, zorder=3))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, color=tc, zorder=4)


def arrow(ax, x0, y0, x1, y1, color=SUB, lw=1.4):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, shrinkA=2, shrinkB=2), zorder=2)


def cell_strip(ax, cx, cy, vals, cmap, cw=0.30, ch=0.30, vmin=-1.0, vmax=1.0, ec="white"):
    """在 (cx,cy) 居中画一条 len(vals) 个格子的横向色条(表示一个向量)。"""
    cm = plt.get_cmap(cmap)
    nb = len(vals); x0 = cx - nb * cw / 2
    for k, v in enumerate(vals):
        ax.add_patch(Rectangle((x0 + k * cw, cy - ch / 2), cw, ch,
                               fc=cm((v - vmin) / (vmax - vmin)), ec=ec, lw=0.8, zorder=3))


# %% 图1:正弦位置编码(真实计算) ---------------------------------------------
def positional_encoding(n_pos, d_model):
    pos = np.arange(n_pos)[:, None]
    i = np.arange(d_model)[None, :]
    angle = pos / np.power(10000.0, (2 * (i // 2)) / d_model)   # 每一对 (2k,2k+1) 维共用一个频率
    return np.where(i % 2 == 0, np.sin(angle), np.cos(angle))

NP, DM = 50, 64
PE = positional_encoding(NP, DM)

fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.7), gridspec_kw={"width_ratios": [1.2, 1]})
fig.patch.set_facecolor(BG)
im = a1.imshow(PE, aspect="auto", cmap="RdBu_r", vmin=-1, vmax=1)
a1.set_xlabel("编码维度 i  (0 … %d)" % (DM - 1)); a1.set_ylabel("位置 pos  (0 … %d)" % (NP - 1))
a1.set_title("① 正弦位置编码矩阵 PE[pos, i]\n每一行就是该位置的一个固定编码向量", fontsize=11)
fig.colorbar(im, ax=a1, fraction=0.046, pad=0.04)
for d, lab in [(0, "i=0(高频/短波长)"), (8, "i=8"), (24, "i=24"), (48, "i=48(低频/长波长)")]:
    a2.plot(np.arange(NP), PE[:, d], lw=2, label=lab)
a2.set_xlabel("位置 pos"); a2.set_ylabel("PE 值"); a2.set_ylim(-1.25, 1.25)
a2.set_title("② 低维用高频、高维用低频\n不同维度以不同波长编码「第几个」", fontsize=11)
a2.legend(fontsize=8.3, loc="lower right"); a2.grid(alpha=0.25)
plt.tight_layout(); plt.savefig(f"{FIG_DIR}/pos-encoding.png", dpi=130, facecolor=BG); plt.close(fig)
print("✓ pos-encoding.png")


# %% 图2:输入流水线 文本→词元→id→嵌入→加位置(示意图) -----------------------
toks = ["深度", "学习", "真有趣"]
ids = [1024, 88, 530]
xs = [1.4, 4.0, 6.6]
rng = np.random.default_rng(7)
emb = {t: rng.uniform(-1, 1, 4) for t in toks}                # 演示用嵌入向量(示意)
pe3 = positional_encoding(3, 4)                               # 前 3 个位置、4 维的真实位置编码

fig = plt.figure(figsize=(11.5, 6.6)); fig.patch.set_facecolor(BG)
ax = fig.add_subplot(111); ax.axis("off"); ax.set_xlim(-1.2, 8.6); ax.set_ylim(-0.2, 8.7)
# 阶段标签(左侧)
for y, lab in [(8.0, "文本"), (6.7, "① 分词 → 词元"), (5.3, "② 查词表 → id"),
               (3.9, "③ 查嵌入表(可学习)"), (2.4, "④ 加位置编码"), (0.7, "= 输入向量")]:
    ax.text(-1.1, y, lab, ha="left", va="center", fontsize=10, color=SUB)
# 文本
box(ax, 4.0, 8.0, "“深度学习真有趣”", fc="#f6edcf", ec="#c9a84a", w=3.4, h=0.62, fs=12)
for x in xs: arrow(ax, 4.0, 7.68, x, 7.02)
# 词元 / id
for t, i, x in zip(toks, ids, xs):
    box(ax, x, 6.7, t, fc="#dbe6f5", ec="#5b7aa6", w=1.25, fs=11)
    arrow(ax, x, 6.37, x, 5.62)
    box(ax, x, 5.3, "id %d" % i, fc="#eef1f5", ec="#9aa6b4", w=1.25, fs=10)
    arrow(ax, x, 4.97, x, 4.30)
    cell_strip(ax, x, 3.9, emb[t], "RdBu_r")                  # 嵌入向量
# 加位置编码 → 输入向量
for k, x in enumerate(xs):
    ax.text(x, 3.42, "＋", ha="center", va="center", fontsize=13, color=SUB)
    cell_strip(ax, x, 2.4, pe3[k], "PuOr")                    # 位置编码(真实计算)
    arrow(ax, x, 2.02, x, 1.18)
    cell_strip(ax, x, 0.7, emb[toks[k]] + pe3[k], "RdBu_r", vmin=-2, vmax=2)  # 输入 = 嵌入 + 位置
ax.text(8.5, 2.4, "位置编码\n(正弦,真实)", ha="right", va="center", fontsize=8, color="#9a7b2a")
ax.set_title("把文本变成「带位置的向量序列」—— 注意力才有向量可算(示意图)", fontsize=12)
plt.tight_layout(); plt.savefig(f"{FIG_DIR}/embed-pipeline.png", dpi=130, facecolor=BG); plt.close(fig)
print("✓ embed-pipeline.png")


# %% 图3:因果掩码(真实计算) -------------------------------------------------
seq = ["我", "爱", "深度", "学习", "。"]
n = len(seq)
rng = np.random.default_rng(0)
scores = rng.normal(0, 1.0, (n, n)).round(1)                 # 演示用 QKᵀ/√d 分数
future = np.triu(np.ones((n, n)), k=1).astype(bool)          # 上三角 = 未来位置
masked = scores.copy(); masked[future] = -np.inf

def softmax_rows(M):
    e = np.exp(M - M.max(axis=1, keepdims=True))             # 被掩掉处 = exp(-inf) = 0
    return e / e.sum(axis=1, keepdims=True)
weights = softmax_rows(masked)

fig, axes = plt.subplots(1, 3, figsize=(14, 4.8)); fig.patch.set_facecolor(BG)

def heat(ax, M, title, cmap, vmin, vmax, blocked=None, weights=False):
    disp = np.array(M, float)
    if blocked is not None: disp = np.where(blocked, np.nan, disp)
    ax.imshow(disp, cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_xticks(range(n)); ax.set_yticks(range(n))
    ax.set_xticklabels(seq); ax.set_yticklabels(seq)
    ax.set_xlabel("被关注的位置 (key)"); ax.set_ylabel("当前位置 (query)")
    for i in range(n):
        for j in range(n):
            if blocked is not None and blocked[i, j]:
                ax.add_patch(Rectangle((j - 0.5, i - 0.5), 1, 1, fc="#e8e6e0", ec="white", lw=0.6))
                ax.text(j, i, "−∞", ha="center", va="center", color=SUB, fontsize=10)
            else:
                v = M[i, j]
                hot = (weights and v > 0.45)
                ax.text(j, i, ("%.2f" % v) if weights else ("%.1f" % v),
                        ha="center", va="center", color="white" if hot else INK, fontsize=8.5)
    ax.set_title(title, fontsize=10.3)

heat(axes[0], scores, "① 原始注意力分数(Q 与 K 点积)\n每个位置都看到了所有位置", "Blues", -2.5, 2.5)
heat(axes[1], scores, "② 加因果掩码:未来位置 → −∞\n屏蔽右上三角", "Blues", -2.5, 2.5, blocked=future)
heat(axes[2], weights, "③ softmax 后的注意力权重\n每行只在「自己及左侧」分配,和为 1", "Greens", 0, 1, weights=True)
plt.tight_layout(); plt.savefig(f"{FIG_DIR}/causal-mask.png", dpi=130, facecolor=BG); plt.close(fig)
print("✓ causal-mask.png  (每行权重和 =", np.round(weights.sum(1), 3), ")")


# %% 图4:自回归下一个 token 预测 + 交叉熵(示意 + 真实 softmax) ---------------
fig = plt.figure(figsize=(13, 4.9)); fig.patch.set_facecolor(BG)

# 左:自回归展开
axL = fig.add_subplot(1, 2, 1); axL.axis("off"); axL.set_xlim(0, 9.2); axL.set_ylim(0, 6.2)
inp = ["<s>", "我", "爱", "学"]
nxt = ["我", "爱", "学", "习"]
px = [1.0, 3.0, 5.0, 7.0]
box(axL, 4.0, 3.1, "多层「掩码」自注意力块", fc="#eaf3ec", ec="#6f9c78", w=7.2, h=0.8, fs=11)
for x, ti, to in zip(px, inp, nxt):
    box(axL, x, 1.1, ti, fc="#dbe6f5", ec="#5b7aa6", w=1.1, fs=11)      # 输入
    arrow(axL, x, 1.45, x, 2.68)
    arrow(axL, x, 3.52, x, 4.75)
    box(axL, x, 5.1, to, fc="#f7dfdc", ec="#b56a5e", w=1.1, fs=11)      # 预测的下一个 token
axL.text(0.1, 5.1, "预测\n下一个", ha="left", va="center", fontsize=8.5, color=SUB)
axL.text(0.1, 1.1, "输入", ha="left", va="center", fontsize=8.5, color=SUB)
axL.set_title("自回归:位置 t 只看 ≤ t 的输入,输出「下一个 token」的分布(示意)", fontsize=10.3)

# 右:某一步的 softmax 分布 + 交叉熵(真实计算)
axR = fig.add_subplot(1, 2, 2)
vocab = ["习", "课", "你", "的", "。"]
logits = np.array([2.6, 0.9, 0.1, -0.4, 0.6])
p = np.exp(logits - logits.max()); p /= p.sum()
true_i = 0                                                   # 输入「我爱学」后,真实下一个 token = 习
colors = [C0 if k == true_i else "#c8cdd4" for k in range(len(vocab))]
axR.bar(range(len(vocab)), p, color=colors, edgecolor="white")
axR.set_xticks(range(len(vocab))); axR.set_xticklabels(vocab, fontsize=11)
axR.set_ylabel("预测概率"); axR.set_ylim(0, 1)
for k, pv in enumerate(p):
    axR.text(k, pv + 0.02, "%.2f" % pv, ha="center", fontsize=9, color=INK)
ce = -np.log(p[true_i])
axR.set_title("输入「我 爱 学」→ 预测下一个 token\n真实=「习」  交叉熵 = −ln %.2f = %.2f" % (p[true_i], ce), fontsize=10.3)
axR.text(0, p[true_i] - 0.12, "真实\n下一个", ha="center", va="top", fontsize=8.5, color="white", fontweight="bold")
plt.tight_layout(); plt.savefig(f"{FIG_DIR}/lm-next-token.png", dpi=130, facecolor=BG); plt.close(fig)
print("✓ lm-next-token.png  (交叉熵 = %.3f)" % ce)

print("全部图已生成到 ./%s/" % FIG_DIR)
