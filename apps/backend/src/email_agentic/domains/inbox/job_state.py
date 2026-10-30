async def fail_intake(connection, job, error, retry=False):
    if job["kind"] == "email_intake":
        await connection.execute(
            """UPDATE email_triage SET status=%s,error_code=%s,updated_at=now()
            WHERE input_id=%s AND owner=%s AND status IN ('queued','failed')""",
            ("queued" if retry else "failed", error, job["entity_id"], job["owner"]),
        )
    elif job["kind"] == "calendar_intake":
        await connection.execute(
            """UPDATE calendar_triage SET status=%s,error_code=%s,updated_at=now()
            WHERE id=%s AND owner=%s AND status IN ('queued','failed')""",
            ("queued" if retry else "failed", error, job["entity_id"], job["owner"]),
        )
