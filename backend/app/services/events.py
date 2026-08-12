"""In-process registry of SSE listeners, keyed by lesson id.

The voice pipeline (app/bot/handlers/voice.py) is the producer: when a draft
is ready it pushes an event here. The Mini App's SSE endpoint
(app/api/lessons.py) is the consumer: it registers a queue while a browser
is streaming and pops it when the stream ends.

This module exists so the API layer never has to import a bot handler.

Single teacher, single browser tab in practice, so one queue per lesson is
enough: a second listener for the same lesson replaces the first, and the
first then only sees its own 90s timeout.
"""
import asyncio

sse_queues: dict[int, asyncio.Queue] = {}
