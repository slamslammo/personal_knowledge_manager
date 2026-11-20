"""Read-only evidence for credentials across cloud instances and token refresh.

The receipt contains only public identifiers, hashes, dates and booleans. It does
not move credentials or create a persistent volume. Different Linux boot IDs are
evidence of different execution instances, not authoritative platform task IDs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import tempfile

import feishu_sync as fs
from common import WORK_DIR

SCHEMA = 1
MAX_OBSERVATIONS = 12
UTC = dt.timezone.utc
APP_ID = "cli_a92390bc96f9dbb4"


def state_path() -> pathlib.Path:
    root = os.environ.get("AI_WEEKLY_STATE_DIR")
    if root:
        return pathlib.Path(root).expanduser() / "credential-probe.json"
    base = pathlib.Path(os.environ.get("XDG_STATE_HOME", pathlib.Path.home() / ".local/state"))
    return base / "ai-weekly/credential-probe.json"


def parse_time(value) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except ValueError:
        return None


def iso(value) -> str | None:
    parsed = parse_time(value)
    return parsed.isoformat() if parsed else None


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def auth_metadata(out: dict) -> dict:
    """Allowlist fields; never persist the raw CLI auth/config response."""
    data = out.get("data") if isinstance(out.get("data"), dict) else out
    user = (data.get("identities") or {}).get("user") or {}
    app = data.get("appId") or data.get("app_id")
    open_id = user.get("openId") or user.get("open_id")
    app = app if isinstance(app, str) and re.fullmatch(r"cli_[A-Za-z0-9]+", app) else None
    identity = digest(app + ":" + open_id) if app and isinstance(open_id, str) and open_id else None
    status = user.get("tokenStatus") or user.get("token_status") or user.get("status")
    dpop = data.get("dpopKeyStatus") or data.get("dpop_key_status")
    return {
        "app_id": app,
        "identity_hash": identity,
        "available": user.get("available") is True,
        "token_status": status if status in {"valid", "needs_refresh", "expired", "missing", "invalid"} else None,
        "expires_at": iso(user.get("expiresAt") or user.get("expires_at")),
        "refresh_expires_at": iso(user.get("refreshExpiresAt") or user.get("refresh_expires_at")),
        "granted_at": iso(user.get("grantedAt") or user.get("granted_at")),
        "dpop_key_status": dpop if dpop in {"available", "missing", "invalid", "unavailable"} else None,
    }


def instance_hash(identity: str) -> str | None:
    try:
        boot = pathlib.Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return None
    return digest(boot + ":" + identity) if boot else None


def safe_error(out: dict) -> dict:
    err = out.get("error") or {}
    return {key: value for key in ("type", "subtype", "code")
            if isinstance(value := err.get(key), (str, int))
            and re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", str(value))}


def state_paths() -> dict:
    """Hints only: a wrapper may override these inside the child process."""
    home = pathlib.Path.home()
    config = os.environ.get("LARKSUITE_CLI_CONFIG_DIR", str(home / ".lark-cli"))
    data = os.environ.get("LARKSUITE_CLI_DATA_DIR", str(pathlib.Path(
        os.environ.get("XDG_DATA_HOME", str(home / ".local/share"))) / "lark-cli"))
    logs = os.environ.get("LARKSUITE_CLI_LOG_DIR")
    return {"config_hint": config, "data_hint": data, "logs_hint": logs,
            "paths_confirmed": False,
            "note": "确认有效 CLI 的实际 config/data/logs 路径及加密、DPoP 密钥；wrapper 可能重设路径。"}


def read_state(path: pathlib.Path, identity: str) -> dict | None:
    value = read_receipt(path)
    return value if value and value.get("identity_hash") == identity else None


def read_receipt(path: pathlib.Path) -> dict | None:
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict) or value.get("schema") != SCHEMA:
            return None
        return value
    except (OSError, ValueError):
        return None


def atomic_write(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".credential-probe-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _observation(value: dict) -> dict:
    """Also allowlist old receipts so unknown fields cannot be copied forward."""
    if not isinstance(value, dict):
        value = {}
    instance = value.get("instance")
    return {"instance": instance if isinstance(instance, str) and re.fullmatch(r"[0-9a-f]{64}", instance) else None,
            "checked_at": iso(value.get("checked_at")),
            "expires_at": iso(value.get("expires_at")),
            "refresh_expires_at": iso(value.get("refresh_expires_at")),
            "refreshed": value.get("refreshed") is True}


def observe(before: dict, after: dict, previous: dict | None, instance: str | None,
            now: dt.datetime, max_idle_hours: float) -> tuple[dict, dict]:
    def authorization_hash(metadata: dict) -> str | None:
        granted = iso(metadata.get("granted_at"))
        identity = metadata.get("identity_hash")
        return digest(identity + ":" + granted) if identity and granted else None

    previous_seen = previous is not None
    before_authorization, authorization = authorization_hash(before), authorization_hash(after)
    prior_authorization = (previous or {}).get("authorization_hash")
    reauthorized = bool((prior_authorization and authorization and prior_authorization != authorization)
                        or (before_authorization and authorization and before_authorization != authorization))
    if (not authorization or prior_authorization != authorization
            or (previous or {}).get("identity_hash") != after.get("identity_hash")):
        previous = None
    same_authorization = bool(authorization and before_authorization == authorization)
    before_expiry, after_expiry = parse_time(before.get("expires_at")), parse_time(after.get("expires_at"))
    refresh_expiry = parse_time(after.get("refresh_expires_at"))
    observations = [_observation(x) for x in (previous or {}).get("observations", []) if isinstance(x, dict)]
    old_refresh = _observation((previous or {}).get("refresh") or {})
    cross_instance = bool(same_authorization and instance
                          and any(x["instance"] and x["instance"] != instance for x in observations))
    refreshed = bool(same_authorization and before_expiry and after_expiry and before_expiry <= now < after_expiry
                     and after_expiry > before_expiry)
    refresh_state_seen = bool(not refreshed and same_authorization and instance
                             and old_refresh["instance"] and old_refresh["instance"] != instance
                             and (old_expiry := parse_time(old_refresh["expires_at"]))
                             and before_expiry and before_expiry >= old_expiry)
    # A later observation may be on the same boot as the last one; preserve only
    # an already observed fact, never turn a copied receipt into a new read.
    seen_before = bool((previous or {}).get("refresh_state_seen_in_later_instance") is True)
    current = {"instance": instance, "checked_at": now.isoformat(), "expires_at": after.get("expires_at"),
               "refresh_expires_at": after.get("refresh_expires_at"), "refreshed": refreshed}
    refresh = current if refreshed else old_refresh
    remaining_hours = (refresh_expiry - now).total_seconds() / 3600 if refresh_expiry else None
    renewal_margin_ok = remaining_hours is not None and remaining_hours > max_idle_hours + 1
    receipt = {"schema": SCHEMA, "identity_hash": after["identity_hash"], "app_id": after["app_id"],
               "authorization_hash": authorization, "granted_at": iso(after.get("granted_at")),
               "observations": (observations + [current])[-MAX_OBSERVATIONS:],
               "refresh": refresh if refresh.get("instance") else None,
               "cross_instance_read_observed": cross_instance or bool((previous or {}).get("cross_instance_read_observed") is True),
               "refresh_state_seen_in_later_instance": False if refreshed else refresh_state_seen or seen_before}
    complete = bool(same_authorization and instance and receipt["cross_instance_read_observed"] and receipt["refresh"]
                    and receipt["refresh_state_seen_in_later_instance"] and renewal_margin_ok
                    and after.get("dpop_key_status") == "available")
    report = {"previous_receipt_seen": previous_seen, "previous_receipt_usable": previous is not None,
              "authorization_session_known": authorization is not None,
              "reauthorization_detected": reauthorized, "different_instance_read": cross_instance,
              "refresh_observed_this_call": refreshed,
              "refresh_state_seen_in_later_instance": receipt["refresh_state_seen_in_later_instance"],
              "refresh_observed": receipt["refresh"] is not None,
              "renewal_margin_ok": renewal_margin_ok, "max_idle_hours": max_idle_hours,
              "refresh_remaining_hours": round(remaining_hours, 2) if remaining_hours is not None else None,
              "c9": "observed" if complete else "pending",
              "storage_writeback_verified": False,
              "note": "观测不等于平台持久化保证；发布快照不能证明刷新状态自动回写。需核对实际存储机制。"}
    if not renewal_margin_ok:
        report["renewal_action"] = "刷新凭据到期余量不足；应在过期前保活，不能保证仅每周运行足够。"
    return receipt, report


def default_document() -> str | None:
    try:
        sync = json.loads((WORK_DIR / fs.RESULT_FILE).read_text())
        value = sync.get("document_id")
        return value if sync.get("action") in {"created", "updated"} and isinstance(value, str) else None
    except (OSError, ValueError):
        return None


def run_probe(doc: str | None = None, state_file: pathlib.Path | None = None,
              max_idle_hours: float = 168, resume: bool = False) -> tuple[dict, int]:
    path = state_file or state_path()
    report = {"api_read": "failed", "c9": "pending", "state_file": str(path), "paths": state_paths()}
    saved = read_receipt(path)
    doc = doc or default_document()
    from_receipt = not doc
    if not doc and saved:
        doc = saved.get("document_id")
    if not isinstance(doc, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", doc):
        if resume:
            return dict(report, api_read="not_run", reason="no_previous_document"), 0
        return dict(report, error={"type": "input", "subtype": "document_required"}), 1
    cli = fs.find_cli(fs.cfg_load() or {})
    if not cli:
        return dict(report, error={"type": "environment", "subtype": "cli_missing"}), 1
    before_raw = fs.run_cli(cli, "auth", "status")
    before = auth_metadata(before_raw)
    if before.get("app_id") != APP_ID:
        return dict(report, error={"type": "identity", "subtype": "app_binding_mismatch"}), 1
    if from_receipt and (not saved or saved.get("identity_hash") != before.get("identity_hash")):
        return dict(report, api_read="not_run", reason="previous_identity_unavailable"), 0
    fetched = fs.run_cli(cli, "docs", "+fetch", "--doc", doc, "--as", "user")
    if fetched.get("error") or fetched.get("ok") is False:
        return dict(report, error=safe_error(fetched)), 1
    if fs._business_failure(fetched):
        return dict(report, error={"type": "business", "subtype": "incomplete_read"}), 1
    document = (fetched.get("data") or {}).get("document") or {}
    if document.get("document_id") != doc or not isinstance(document.get("content"), str):
        return dict(report, error={"type": "business", "subtype": "unexpected_document"}), 1
    after_raw = fs.run_cli(cli, "auth", "status")
    after = auth_metadata(after_raw)
    report.update(api_read="ok", document_id=doc, before=before, after=after,
                  document_content_hash=digest(document["content"]))
    if after_raw.get("error") or not after.get("identity_hash") or not after.get("available"):
        return dict(report, metadata="unavailable"), 0
    if before.get("identity_hash") != after["identity_hash"]:
        return dict(report, metadata="identity_changed_during_probe"), 0
    previous = read_state(path, after["identity_hash"])
    instance = instance_hash(after["identity_hash"])
    receipt, facts = observe(before, after, previous, instance, dt.datetime.now(UTC), max_idle_hours)
    receipt["document_id"] = doc
    try:
        atomic_write(path, receipt)
    except OSError:
        return dict(report, error={"type": "storage", "subtype": "receipt_write_failed"}), 1
    report.update(facts)
    return report, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doc", help="读取已存在的测试文档；缺省取本次成功同步的 document_id")
    parser.add_argument("--resume", action="store_true",
                        help="优先恢复上次文档探测；无历史文档时只报告待验，不调用API")
    parser.add_argument("--max-idle-hours", type=float, default=168,
                        help="拟议最长空闲时间；仅检查续期余量，不会创建保活任务（缺省168小时）")
    args = parser.parse_args(argv)
    if args.max_idle_hours <= 0:
        parser.error("--max-idle-hours 必须大于0")
    report, code = run_probe(args.doc, max_idle_hours=args.max_idle_hours, resume=args.resume)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"API_READ={report['api_read']}")
    print(f"C9={report['c9']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
