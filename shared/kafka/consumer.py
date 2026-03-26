"""
Kafka BaseConsumer — wraps confluent-kafka with:
- Manual offset commit (only after successful processing)
- DLQ routing after max_retries
- Graceful shutdown on SIGTERM/SIGINT
- Rebalance handling
"""
import json
import os
import signal
import structlog
from typing import Callable, Any
from confluent_kafka import Consumer, KafkaError, KafkaException, TopicPartition

from shared.kafka.producer import BaseProducer

log = structlog.get_logger()

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


class BaseConsumer:
    """
    Kafka consumer with manual commit, retry, and DLQ support.

    Subclass and implement `process_message(data: dict) -> None`.
    Call `run()` to start the blocking event loop.

    Usage:
        class MyConsumer(BaseConsumer):
            def process_message(self, data: dict):
                # your logic here
                pass

        consumer = MyConsumer(topics=["life-admin.emails.raw"], group_id="processor-group")
        consumer.run()
    """

    MAX_RETRIES = 3
    POLL_TIMEOUT = 1.0  # seconds

    def __init__(
        self,
        topics: list[str],
        group_id: str,
        bootstrap_servers: str = KAFKA_BOOTSTRAP,
        auto_offset_reset: str = "earliest",
    ):
        self.topics = topics
        self.group_id = group_id
        self._running = True
        self._dlq_producer = BaseProducer(bootstrap_servers)

        self._consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": group_id,
                "auto.offset.reset": auto_offset_reset,
                "enable.auto.commit": False,      # Manual commit only
                "enable.auto.offset.store": False,
                "max.poll.interval.ms": 300_000,
                "session.timeout.ms": 45_000,
                "on_commit": self._on_commit,
            }
        )
        self._consumer.subscribe(topics, on_assign=self._on_assign, on_revoke=self._on_revoke)

        # Graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    # ─── Override in subclass ─────────────────────────────────────────────────

    def process_message(self, data: dict[str, Any]) -> None:
        """Process a single message payload. Override in subclass."""
        raise NotImplementedError

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _on_assign(self, consumer, partitions):
        log.info("Partitions assigned", partitions=[str(p) for p in partitions])

    def _on_revoke(self, consumer, partitions):
        log.info("Partitions revoked", partitions=[str(p) for p in partitions])

    def _on_commit(self, err, partitions):
        if err:
            log.error("Commit failed", error=str(err))
        else:
            log.debug("Offsets committed", partitions=[str(p) for p in partitions])

    def _handle_shutdown(self, signum, frame):
        log.info("Shutdown signal received, stopping consumer loop")
        self._running = False

    def run(self) -> None:
        """
        Blocking consumer loop.
        - Polls for messages
        - Calls process_message()
        - Commits offset on success
        - Routes to DLQ after MAX_RETRIES failures
        """
        log.info(
            "Consumer started",
            topics=self.topics,
            group_id=self.group_id,
        )

        retry_counts: dict[tuple, int] = {}  # (topic, partition, offset) → retry count

        try:
            while self._running:
                msg = self._consumer.poll(self.POLL_TIMEOUT)

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        log.debug("End of partition", topic=msg.topic(), partition=msg.partition())
                        continue
                    raise KafkaException(msg.error())

                msg_key = (msg.topic(), msg.partition(), msg.offset())

                try:
                    envelope = json.loads(msg.value().decode("utf-8"))
                    data = envelope.get("data", envelope)  # Support both envelope and raw

                    log.info(
                        "Processing message",
                        topic=msg.topic(),
                        partition=msg.partition(),
                        offset=msg.offset(),
                        event_id=envelope.get("event_id", "unknown"),
                    )

                    self.process_message(data)

                    # Success — commit offset
                    self._consumer.store_offsets(msg)
                    self._consumer.commit(asynchronous=True)
                    retry_counts.pop(msg_key, None)

                    log.info(
                        "Message processed",
                        topic=msg.topic(),
                        offset=msg.offset(),
                    )

                except Exception as e:
                    retries = retry_counts.get(msg_key, 0) + 1
                    retry_counts[msg_key] = retries

                    log.error(
                        "Message processing failed",
                        topic=msg.topic(),
                        offset=msg.offset(),
                        error=str(e),
                        retry=retries,
                        max_retries=self.MAX_RETRIES,
                    )

                    if retries >= self.MAX_RETRIES:
                        log.error("Max retries reached, routing to DLQ", msg_key=msg_key)
                        try:
                            raw_data = json.loads(msg.value().decode("utf-8"))
                        except Exception:
                            raw_data = {"raw": msg.value().decode("utf-8", errors="replace")}

                        self._dlq_producer.publish_to_dlq(
                            original_topic=msg.topic(),
                            original_message=raw_data,
                            error_type=type(e).__name__,
                            error_message=str(e),
                            retry_count=retries,
                        )
                        # Commit even on DLQ route (don't reprocess dead messages)
                        self._consumer.store_offsets(msg)
                        self._consumer.commit(asynchronous=True)
                        retry_counts.pop(msg_key, None)

        finally:
            self._consumer.close()
            self._dlq_producer.flush()
            log.info("Consumer stopped cleanly")
