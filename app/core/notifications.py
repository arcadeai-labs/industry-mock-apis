"""Mock notification outbox (common.notifications). Messages are recorded, never delivered."""
import psycopg

from app.core.query import new_id


def queue_notification(
    conn: psycopg.Connection,
    *,
    channel: str,
    recipient: str,
    body: str,
    created_by: str,
    subject: str | None = None,
    domain: str | None = None,
    related_resource_type: str | None = None,
    related_resource_id: str | None = None,
) -> dict:
    """Record an email/sms/chat/push message in the outbox and return the stored row."""
    return conn.execute(
        """
        INSERT INTO common.notifications (id, channel, recipient, subject, body, domain, related_resource_type,
                                          related_resource_id, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *
        """,
        [new_id("NTF"), channel, recipient, subject, body, domain, related_resource_type, related_resource_id, created_by],
    ).fetchone()
