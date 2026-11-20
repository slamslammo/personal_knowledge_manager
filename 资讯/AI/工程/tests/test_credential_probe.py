"""Credential evidence without network calls or real credentials."""
import datetime as dt
import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest
from unittest import mock

_ROOT = pathlib.Path(__file__).resolve().parent.parent  # 工程根
for _d in ("core", "weekly"):
    if str(_ROOT / _d) not in sys.path:
        sys.path.insert(0, str(_ROOT / _d))
import credential_probe as cp

NOW = dt.datetime(2026, 11, 16, 4, tzinfo=dt.timezone.utc)
IDENTITY = cp.digest(cp.APP_ID + ":user")
A, B, C = (cp.digest(x) for x in ("boot-a", "boot-b", "boot-c"))


def metadata(expiry=2, refresh=240, identity=IDENTITY, granted=-24):
    return {"identity_hash": identity, "app_id": cp.APP_ID, "available": True,
            "expires_at": (NOW + dt.timedelta(hours=expiry)).isoformat(),
            "refresh_expires_at": (NOW + dt.timedelta(hours=refresh)).isoformat(),
            "granted_at": (NOW + dt.timedelta(hours=granted)).isoformat() if granted is not None else None,
            "token_status": "valid", "dpop_key_status": "available"}


def raw(expiry=2, secret="DO_NOT_STORE_THIS"):
    m = metadata(expiry)
    return {"ok": True, "appId": cp.APP_ID, "appSecret": secret, "refresh_token": secret,
            "identities": {"user": {"available": True, "openId": "user", "tokenStatus": "valid",
                                      "expiresAt": m["expires_at"], "refreshExpiresAt": m["refresh_expires_at"],
                                      "grantedAt": m["granted_at"],
                                      "accessToken": secret}}, "dpopKeyStatus": "available"}


def document():
    return {"ok": True, "data": {"document": {"content": "PRIVATE DOCUMENT", "document_id": "Doc123"}}}


class ObserveTest(unittest.TestCase):
    def observe(self, before, after, previous=None, instance=A, idle=168):
        return cp.observe(before, after, previous, instance, NOW, idle)

    def test_missing_receipt_is_pending(self):
        receipt, report = self.observe(metadata(), metadata())
        self.assertEqual(report["c9"], "pending")
        self.assertFalse(report["previous_receipt_seen"])
        self.assertFalse(report["different_instance_read"])

    def test_same_boot_other_call_is_not_independent(self):
        first, _ = self.observe(metadata(), metadata())
        second, report = self.observe(metadata(), metadata(), first)
        self.assertFalse(second["cross_instance_read_observed"])
        self.assertFalse(report["different_instance_read"])

    def test_expiry_then_refresh_and_later_instance_read(self):
        first, _ = self.observe(metadata(-1), metadata(), instance=A)
        self.assertIsNotNone(first["refresh"])
        second, report = self.observe(metadata(), metadata(), first, instance=B)
        self.assertTrue(report["different_instance_read"])
        self.assertTrue(report["refresh_state_seen_in_later_instance"])
        self.assertEqual(report["c9"], "observed")
        self.assertFalse(report["storage_writeback_verified"])

    def test_refreshed_state_is_not_readback_on_same_instance(self):
        first, _ = self.observe(metadata(), metadata(), instance=A)
        second, report = self.observe(metadata(-1), metadata(), first, instance=B)
        self.assertTrue(report["refresh_observed_this_call"])
        self.assertFalse(report["refresh_state_seen_in_later_instance"])
        third, report = self.observe(metadata(), metadata(), second, instance=C)
        self.assertEqual(report["c9"], "observed")

    def test_different_machine_with_stale_token_cannot_prove_readback(self):
        first, _ = self.observe(metadata(-1), metadata(), instance=A)
        second, report = self.observe(metadata(-2), metadata(), first, instance=B)
        self.assertFalse(report["refresh_state_seen_in_later_instance"])
        self.assertEqual(report["c9"], "pending")

    def test_short_refresh_lifetime_requires_keepalive(self):
        first, _ = self.observe(metadata(-1, 167), metadata(2, 167), instance=A)
        _, report = self.observe(metadata(2, 167), metadata(2, 167), first, instance=B)
        self.assertEqual(report["c9"], "pending")
        self.assertFalse(report["renewal_margin_ok"])
        self.assertIn("保活", report["renewal_action"])

    def test_missing_boot_id_does_not_prove_independence(self):
        first, _ = self.observe(metadata(), metadata(), instance=A)
        _, report = self.observe(metadata(), metadata(), first, instance=None)
        self.assertFalse(report["different_instance_read"])

    def test_observations_are_bounded_and_unknown_fields_removed(self):
        previous, _ = self.observe(metadata(), metadata())
        previous["observations"] = [dict(instance=A, checked_at=NOW.isoformat(), secret="bad")] * 40
        receipt, _ = self.observe(metadata(), metadata(), previous)
        self.assertEqual(len(receipt["observations"]), cp.MAX_OBSERVATIONS)
        self.assertNotIn("bad", json.dumps(receipt))

    def test_same_user_reauthorization_clears_all_inheritance_evidence(self):
        first, _ = self.observe(metadata(-1), metadata(), instance=A)
        inherited, proven = self.observe(metadata(), metadata(), first, instance=B)
        self.assertEqual(proven["c9"], "observed")
        receipt, report = self.observe(metadata(4, granted=-1), metadata(4, granted=-1), inherited, instance=C)
        self.assertTrue(report["reauthorization_detected"])
        self.assertFalse(report["previous_receipt_usable"])
        self.assertFalse(report["different_instance_read"])
        self.assertFalse(receipt["cross_instance_read_observed"])
        self.assertFalse(receipt["refresh_state_seen_in_later_instance"])
        self.assertIsNone(receipt["refresh"])
        self.assertEqual(len(receipt["observations"]), 1)
        self.assertEqual(report["c9"], "pending")

    def test_unknown_authorization_time_cannot_prove_inheritance(self):
        first, _ = self.observe(metadata(-1), metadata(), instance=A)
        inherited, _ = self.observe(metadata(), metadata(), first, instance=B)
        receipt, report = self.observe(metadata(granted=None), metadata(granted=None), inherited, instance=C)
        self.assertFalse(report["authorization_session_known"])
        self.assertFalse(report["previous_receipt_usable"])
        self.assertFalse(receipt["refresh_state_seen_in_later_instance"])
        self.assertEqual(report["c9"], "pending")

    def test_new_refresh_cycle_resets_prior_readback_proof(self):
        first, _ = self.observe(metadata(-1), metadata(), instance=A)
        inherited, proven = self.observe(metadata(), metadata(), first, instance=B)
        self.assertTrue(proven["refresh_state_seen_in_later_instance"])
        receipt, report = self.observe(metadata(-1), metadata(4), inherited, instance=C)
        self.assertTrue(report["refresh_observed_this_call"])
        self.assertEqual(receipt["refresh"]["instance"], C)
        self.assertFalse(report["refresh_state_seen_in_later_instance"])
        self.assertEqual(report["c9"], "pending")

    def test_reauthorization_during_fetch_is_not_automatic_refresh(self):
        receipt, report = self.observe(metadata(-1), metadata(4, granted=-1), instance=A)
        self.assertTrue(report["reauthorization_detected"])
        self.assertFalse(report["refresh_observed_this_call"])
        self.assertIsNone(receipt["refresh"])
        self.assertEqual(report["c9"], "pending")


class ProbeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = pathlib.Path(self.tmp.name) / "probe.json"
        self.patches = [mock.patch.object(cp.fs, "find_cli", return_value="/mock/lark-cli"),
                        mock.patch.object(cp.fs, "cfg_load", return_value={}),
                        mock.patch.object(cp, "instance_hash", return_value=A)]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_success_only_saves_allowlisted_fields_and_explicit_user(self):
        with mock.patch.object(cp.fs, "run_cli", side_effect=[raw(-1), document(), raw()]) as cli:
            report, code = cp.run_probe("Doc123", self.path)
        self.assertEqual(code, 0)
        self.assertEqual(report["api_read"], "ok")
        cli.assert_any_call("/mock/lark-cli", "docs", "+fetch", "--doc", "Doc123", "--as", "user")
        text = self.path.read_text() + json.dumps(report)
        self.assertNotIn("DO_NOT_STORE_THIS", text)
        self.assertNotIn("PRIVATE DOCUMENT", text)
        self.assertNotIn('"openId"', text)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_failure_does_not_overwrite_previous_success(self):
        self.path.write_text('{"previous":"success"}')
        error = {"ok": False, "error": {"type": "network", "subtype": "timeout", "detail": "DO_NOT_STORE_THIS"}}
        with mock.patch.object(cp.fs, "run_cli", side_effect=[raw(), error]):
            report, code = cp.run_probe("Doc123", self.path)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(self.path.read_text()), {"previous": "success"})
        self.assertNotIn("DO_NOT_STORE_THIS", json.dumps(report))

    def test_business_failure_is_not_recorded(self):
        with mock.patch.object(cp.fs, "run_cli", side_effect=[raw(), {"ok": True, "data": {"result": "partial_success"}}]):
            report, code = cp.run_probe("Doc123", self.path)
        self.assertEqual(code, 1)
        self.assertFalse(self.path.exists())

    def test_other_identity_receipt_is_not_reused(self):
        cp.atomic_write(self.path, {"schema": cp.SCHEMA, "identity_hash": "other", "observations": [{"instance": B}]})
        with mock.patch.object(cp.fs, "run_cli", side_effect=[raw(), document(), raw()]):
            report, code = cp.run_probe("Doc123", self.path)
        self.assertEqual(code, 0)
        self.assertFalse(report["previous_receipt_seen"])
        self.assertFalse(report["different_instance_read"])

    def test_identity_changed_mid_call_cannot_make_receipt(self):
        after = raw()
        after["identities"]["user"]["openId"] = "another-user"
        with mock.patch.object(cp.fs, "run_cli", side_effect=[raw(), document(), after]):
            report, code = cp.run_probe("Doc123", self.path)
        self.assertEqual(code, 0)
        self.assertEqual(report["c9"], "pending")
        self.assertFalse(self.path.exists())

    def test_configured_state_dir_is_used(self):
        with mock.patch.dict(os.environ, {"AI_WEEKLY_STATE_DIR": self.tmp.name}):
            self.assertEqual(cp.state_path(), pathlib.Path(self.tmp.name) / "credential-probe.json")

    def test_wrong_application_rejects_before_fetch(self):
        wrong = raw()
        wrong["appId"] = "cli_wrong"
        with mock.patch.object(cp.fs, "run_cli", return_value=wrong) as cli:
            report, code = cp.run_probe("Doc123", self.path)
        self.assertEqual(code, 1)
        self.assertEqual(cli.call_count, 1)
        self.assertFalse(self.path.exists())

    def test_resume_without_history_does_not_call_cli(self):
        with mock.patch.object(cp, "default_document", return_value=None), \
             mock.patch.object(cp.fs, "run_cli") as cli:
            report, code = cp.run_probe(state_file=self.path, resume=True)
        self.assertEqual(code, 0)
        self.assertEqual(report["api_read"], "not_run")
        cli.assert_not_called()

    def test_malformed_saved_document_is_pending_without_api(self):
        cp.atomic_write(self.path, {"schema": cp.SCHEMA, "identity_hash": IDENTITY,
                                   "document_id": {"bad": "value"}, "refresh": "bad"})
        with mock.patch.object(cp, "default_document", return_value=None), \
             mock.patch.object(cp.fs, "run_cli") as cli:
            report, code = cp.run_probe(state_file=self.path, resume=True)
        self.assertEqual(code, 0)
        self.assertEqual(report["api_read"], "not_run")
        cli.assert_not_called()

    def test_resume_reads_saved_document_after_tmp_is_gone(self):
        cp.atomic_write(self.path, {"schema": cp.SCHEMA, "identity_hash": IDENTITY,
                                   "document_id": "Doc123", "observations": []})
        with mock.patch.object(cp, "default_document", return_value=None), \
             mock.patch.object(cp.fs, "run_cli", side_effect=[raw(), document(), raw()]) as cli:
            report, code = cp.run_probe(state_file=self.path, resume=True)
        self.assertEqual(code, 0)
        self.assertEqual(report["api_read"], "ok")
        cli.assert_any_call("/mock/lark-cli", "docs", "+fetch", "--doc", "Doc123", "--as", "user")

    def test_resume_does_not_read_old_identity_document(self):
        cp.atomic_write(self.path, {"schema": cp.SCHEMA, "identity_hash": "other",
                                   "document_id": "Doc123", "observations": []})
        with mock.patch.object(cp, "default_document", return_value=None), \
             mock.patch.object(cp.fs, "run_cli", return_value=raw()) as cli:
            report, code = cp.run_probe(state_file=self.path, resume=True)
        self.assertEqual(code, 0)
        self.assertEqual(report["api_read"], "not_run")
        self.assertEqual(cli.call_count, 1)

    def test_document_defaults_only_to_successful_sync(self):
        sync = pathlib.Path(self.tmp.name) / cp.fs.RESULT_FILE
        sync.write_text(json.dumps({"document_id": "Doc123", "action": "unknown"}))
        with mock.patch.object(cp, "WORK_DIR", pathlib.Path(self.tmp.name)):
            self.assertIsNone(cp.default_document())
            sync.write_text(json.dumps({"document_id": "Doc123", "action": "created"}))
            self.assertEqual(cp.default_document(), "Doc123")


if __name__ == "__main__":
    unittest.main()
