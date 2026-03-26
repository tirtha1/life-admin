"""
Kafka publisher for the processor service.
Publishes to life-admin.bills.extracted topic.
"""
import structlog
from datetime import date

from shared.kafka.producer import BaseProducer

log = structlog.get_logger()

TOPIC_BILLS_EXTRACTED = "life-admin.bills.extracted"


class BillPublisher(BaseProducer):
    """Publishes bill extracted events to Kafka."""

    def publish_bill_extracted(
        self,
        user_id: str,
        bill_id: str,
        provider: str,
        bill_type: str,
        amount: float | None,
        currency: str,
        due_date: date | None,
        status: str,
        needs_review: bool,
    ) -> None:
        """Publish a bill-extracted event so the agent service can pick it up."""
        payload = {
            "user_id": user_id,
            "bill_id": bill_id,
            "provider": provider,
            "bill_type": bill_type,
            "amount": amount,
            "currency": currency,
            "due_date": due_date.isoformat() if due_date else None,
            "status": status.lower() if status else status,
            "needs_review": needs_review,
        }
        self.publish(
            topic=TOPIC_BILLS_EXTRACTED,
            key=f"{user_id}:{bill_id}",
            data=payload,
        )
        log.info(
            "Bill extracted event published",
            topic=TOPIC_BILLS_EXTRACTED,
            user_id=user_id,
            bill_id=bill_id,
            provider=provider,
        )
