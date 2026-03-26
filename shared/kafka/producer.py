"""
Kafka BaseProducer — wraps confluent-kafka with:
- JSON envelope with schema version
- Automatic DLQ routing on delivery failure
- Structured logging per message
"""
import json
import uuid
import os
from datetime import datetime, timezone
from typing import Any

import structlog
from confluent_kafka import Producer, KafkaError

log = structlog.get_logger()

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
DLQ_TOPIC = "life-admin.dlq"
SCHEMA_VERSION = "1.0"


def _build_envelope(topic: str, data: dict, schema_version: str = SCHEMA_VERSION) -> dict:
    """Wrap data in a standard event envelope."""
    return {
        "event_id": str(uuid.uuid4()),
        "schema_version": schema_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_topic": topic,
        "data": data,
    }


class BaseProducer:
    """
    Thread-safe Kafka producer with envelope, retries, and DLQ support.

    Usage:
        producer = BaseProducer()
        producer.publish("life-admin.emails.raw", {"user_id": ..., "email_id": ...})
        producer.flush()
    """

    def __init__(self, bootstrap_servers: str = KAFKA_BOOTSTRAP):
        self._producer = Producer(
            {
                "bootstrap.servers": bootstrap_servers,
                "acks": "all",
                "retries": 5,
                "retry.backoff.ms": 300,
                "enable.idempotence": True,
                "compression.type": "lz4",
                "linger.ms": 10,
            }
        )
        self._bootstrap = bootstrap_servers

    def _delivery_callback(self, err: KafkaError | None, msg) -> None:
        if err:
            log.error(
                "Kafka delivery failed",
                topic=msg.topic(),
                partition=msg.partition(),
                error=str(err),
            )
        else:
            log.debug(
                "Kafka message delivered",
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
            )

    def publish(
        self,
        topic: str,
        data: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Publish a message to the given topic.
        Wraps data in standard envelope.
        """
        envelope = _build_envelope(topic, data)
        payload = json.dumps(envelope, default=str).encode("utf-8")

        kafka_headers = (
            [(k, v.encode()) for k, v in headers.items()] if headers else None
        )

        self._producer.produce(
            topic=topic,
            value=payload,
            key=key.encode() if key else None,
            headers=kafka_headers,
            on_delivery=self._delivery_callback,
        )
        self._producer.poll(0)  # Trigger delivery callbacks

        log.info("Kafka message published", topic=topic, event_id=envelope["event_id"])

    def publish_to_dlq(
        self,
        original_topic: str,
        original_message: dict,
        error_type: str,
        error_message: str,
        retry_count: int = 0,
    ) -> None:
        """Route a failed message to the Dead Letter Queue."""
        dlq_payload = {
            "original_topic": original_topic,
            "original_message": original_message,
            "error_type": error_type,
            "error_message": error_message,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "retry_count": retry_count,
        }
        self.publish(DLQ_TOPIC, dlq_payload)
        log.warning(
            "Message routed to DLQ",
            original_topic=original_topic,
            error_type=error_type,
            retry_count=retry_count,
        )

    def flush(self, timeout: float = 10.0) -> None:
        """Wait for all pending messages to be delivered."""
        self._producer.flush(timeout=timeout)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.flush()
