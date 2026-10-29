from datetime import datetime, UTC, timedelta


def test_local_backup_expiry_keeps_fresh_unrelated_files_and_symlinks(tmp_path):
    import os
    from email_agentic.platform.retention import prune_local_dumps

    now = datetime.now(UTC)
    old = tmp_path / "before-retention-old.sql"
    fresh = tmp_path / "before-retention-fresh.sql"
    unrelated = tmp_path / "manual.sql"
    for path in (old, fresh, unrelated):
        path.write_bytes(b"backup")
    past = (now - timedelta(days=8)).timestamp()
    os.utime(old, (past, past))
    os.utime(unrelated, (past, past))
    link = tmp_path / "before-linked.sql"
    link.symlink_to(unrelated)
    prune_local_dumps(tmp_path, now)
    assert not old.exists() and fresh.exists() and unrelated.exists() and link.is_symlink()
