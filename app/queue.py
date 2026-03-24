"""SQS queue client — initialized at Lambda cold start."""

import json


_sqs = None
_queue_url = None


def init(sqs_client, queue_url: str):
    global _sqs, _queue_url
    _sqs = sqs_client
    _queue_url = queue_url


def enqueue_generation(charge_id: str, session_id: str):
    _sqs.send_message(
        QueueUrl=_queue_url,
        MessageBody=json.dumps({"charge_id": charge_id, "session_id": session_id}),
    )
