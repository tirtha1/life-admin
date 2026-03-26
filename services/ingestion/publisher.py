"""
Kafka publisher for the ingestion service.
Publishes to life-admin.emails.raw topic.
"""
import structlog

from shared.kafka.producer import BaseProducer
from services.ingestion.gmail_client import ParsedEmail

log = structlog.get_logger()

TOPIC_EMAILS_RAW = "life-admin.emails.raw"


class EmailPublisher(BaseProducer):
    """Publishes raw email events to Kafka."""

    def publish_email(self, user_id: str, email: ParsedEmail, s3_key: str, raw_email_id: str = "") -> None:
        """
        Publish a parsed email event to life-admin.emails.raw.

        Args:
            user_id: The user's UUID
            email: ParsedEmail object
            s3_key: S3 key where the raw email JSON is stored
            raw_email_id: UUID of the raw_emails DB row
        """
        payload = {
            "user_id": user_id,
            "message_id": email.message_id,
            "thread_id": email.thread_id,
            "subject": email.subject,
            "sender": email.sender,
            "received_at": email.received_at,
            "snippet": email.snippet,
            "s3_key": s3_key,
            "raw_email_id": raw_email_id,
        }
        self.publish(
            topic=TOPIC_EMAILS_RAW,
            key=f"{user_id}:{email.message_id}",
            data=payload,
        )
        log.info(
            "Email event published",
            topic=TOPIC_EMAILS_RAW,
            user_id=user_id,
            message_id=email.message_id,
        )
