"""AI 资讯任务脚本的公共部分：路径、配置读取、HTTP 请求、链接规范化。

只依赖 Python 标准库和 PyYAML，保证在任何能运行 python3 的平台上都能直接运行。
"""
from __future__ import annotations

import http.client
import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, NamedTuple

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
TASK_DIR = SCRIPTS_DIR.parent  # AI资讯/任务
BOARD_DIR = TASK_DIR.parent  # AI资讯
REPO_DIR = BOARD_DIR.parent
WORK_DIR = pathlib.Path(os.environ.get("AI_WEEKLY_TMP", "/tmp/ai-weekly"))
# 本次运行的产出（周报、数据文件等）按仓库内的相对路径放在 OUT_DIR 下，由 coord.py 提交；
# 运行过程中不改动仓库的工作区。
OUT_DIR = WORK_DIR / "out"

USER_AGENT = (
    "Mozilla/5.0 (compatible; ai-weekly/0.1; "
    "+https://github.com/slamslammo/personal_knowledge_manager)"
)


def load_config(name: str) -> dict:
    """读取 config/{name}.yaml。"""
    import yaml  # 延迟导入：weeks.py 等不读配置的脚本不依赖 PyYAML

    with open(TASK_DIR / "config" / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_json(path: str | os.PathLike, obj) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def read_json(path: str | os.PathLike):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- HTTP


class FetchResult(NamedTuple):
    status: int  # HTTP 状态码；网络层失败为 0
    body: bytes
    error: str | None  # 重试用尽后的最后一个错误
    attempts: int = 1  # 实际请求次数（含重试）
    url: str = ""  # 跟随跳转后的最终地址
    content_type: str = ""

    @property
    def ok(self) -> bool:
        return self.status == 200

    def text(self) -> str:
        return self.body.decode("utf-8", "replace")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """不跟随跳转：Trendshift 进行中的周会 307 到 /weekly，需要原样拿到状态码。"""

    def redirect_request(self, *args, **kwargs):
        return None


class _LimitedRedirect(urllib.request.HTTPRedirectHandler):
    """跟随跳转，但只允许 http/https，次数有上限（读取文章原文时使用）。"""

    max_redirections = 3

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme not in ("http", "https"):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_NoRedirect)


def _redirect_opener(max_redirects: int):
    handler = _LimitedRedirect()
    handler.max_redirections = max_redirects
    return urllib.request.build_opener(handler)


def fetch(
    url: str,
    *,
    params: dict | None = None,
    timeout: float = 40,
    retries: int = 3,
    backoff: float = 2.0,
    give_up: Callable[[int, bytes], bool] | None = None,
    max_redirects: int = 0,
    max_bytes: int | None = None,
) -> FetchResult:
    """GET 请求。网络错误、5xx、429 按 backoff·2^n 秒间隔重试，3xx/4xx 直接返回。

    give_up(status, body) 返回 True 时不再重试，例如 OSS Insight 对不存在的仓库返回 500。
    max_redirects 为 0 时不跟随跳转（默认）；max_bytes 限制读取的字节数。
    只发 GET，不带任何本地凭证。
    """
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    opener = _redirect_opener(max_redirects) if max_redirects else _OPENER
    last_error = None
    status, body = 0, b""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with opener.open(req, timeout=timeout) as resp:
                data = resp.read(max_bytes) if max_bytes else resp.read()
                return FetchResult(resp.status, data, None, attempt + 1, resp.geturl(),
                                   resp.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read(max_bytes) if max_bytes else e.read()
            if e.code < 500 and e.code != 429:
                return FetchResult(status, body, None, attempt + 1, url)
            last_error = f"HTTP {e.code}"
            if give_up and give_up(status, body):
                return FetchResult(status, body, last_error, attempt + 1, url)
        except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
            status, body = 0, b""
            last_error = f"{type(e).__name__}: {e}"
        if attempt < retries:
            time.sleep(backoff * 2**attempt)
    return FetchResult(status, body, last_error, retries + 1, url)


# ---------------------------------------------------------------- 链接


def normalize_url(url: str) -> str:
    """用于去重的链接规范化：忽略协议、www、末尾斜杠、utm_* 参数和锚点。"""
    parts = urllib.parse.urlsplit(url.strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/")
    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_")
    ]
    q = urllib.parse.urlencode(query)
    return host + path + ("?" + q if q else "")


_GITHUB_REPO = re.compile(r"^https?://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+)(/.*)?$")
_GITHUB_RESERVED_OWNERS = {
    "orgs", "features", "blog", "topics", "sponsors", "marketplace",
    "apps", "collections", "trending", "enterprise",
}
_GITHUB_SKIP_SUBPATHS = ("issues", "pull", "pulls", "commit", "commits", "discussions", "wiki")


def github_repo_from_url(url: str | None) -> str | None:
    """从链接中提取 owner/repo；不是仓库主页类链接时返回 None。"""
    if not url:
        return None
    m = _GITHUB_REPO.match(url.strip())
    if not m:
        return None
    owner, repo, rest = m.group(1), m.group(2), m.group(3) or ""
    if owner.lower() in _GITHUB_RESERVED_OWNERS:
        return None
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not repo or repo in (".", ".."):
        return None
    sub = rest.strip("/").split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if sub in _GITHUB_SKIP_SUBPATHS:
        return None
    return f"{owner}/{repo}"


def domain_of(url: str | None) -> str:
    """链接的域名，小写，去掉 www.。"""
    if not url:
        return ""
    host = urllib.parse.urlsplit(url.strip()).netloc.lower().split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def matches_source(url: str | None, entries: list) -> bool:
    """链接是否属于 sources.yaml 中的某个来源。条目可以是域名（含子域名）、"域名/路径前缀"，或带 domain 的字典。"""
    if not url:
        return False
    host = domain_of(url)
    path = urllib.parse.urlsplit(url.strip()).path
    for entry in entries or []:
        spec = entry.get("domain", "") if isinstance(entry, dict) else str(entry)
        if not spec or " " in spec or "." not in spec:
            continue  # "个人技术博客"之类的说明文字
        d, _, prefix = spec.partition("/")
        if (host == d or host.endswith("." + d)) and path.startswith("/" + prefix if prefix else ""):
            return True
    return False


def is_homepage(url: str | None) -> bool:
    """只指向网站首页的链接（路径为空或 /，没有查询参数）。"""
    if not url:
        return False
    parts = urllib.parse.urlsplit(url.strip())
    return parts.scheme in ("http", "https") and parts.path.strip("/") == "" and not parts.query


def truncate(text: str | None, n: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"
