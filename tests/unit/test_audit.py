def test_audit_chain_verifies_and_detects_tampering(app):
    app.db.audit("A", "read", "J-1", "ALLOWED", {"x": 1}, "T-1")
    app.db.audit("B", "write", "J-1", "DENIED", {"reason": "test"}, "T-2")
    assert app.db.verify_audit_chain() is True
    app.db.connection.execute("UPDATE audit SET outcome='ALTERED' WHERE audit_id=1")
    assert app.db.verify_audit_chain() is False


def test_audit_service_appends_hash_chained_records(app, principals):
    first = app.audit.record(principals["viewer"], "read", "P-A", "ALLOWED", {"endpoint": "/api/governance/audit"}, "T-GOV-1")
    second = app.audit.record(principals["quality"], "quality:release", "BATCH-100", "ALLOWED", {"decision": "RELEASED"}, "T-GOV-2")
    snapshot = app.audit.snapshot(limit=10)
    assert first["previous_hash"] == "GENESIS"
    assert second["previous_hash"] == first["record_hash"]
    assert snapshot["chain_valid"] is True
    assert snapshot["entries"] == 2
    assert snapshot["records"][0]["audit_id"] == second["audit_id"]
    app.db.connection.execute("UPDATE audit SET outcome='ALTERED' WHERE audit_id=?", (first["audit_id"],))
    assert app.audit.verify()["chain_valid"] is False
