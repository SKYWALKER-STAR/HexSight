import asyncio
from collections import defaultdict


class EventBus:
    """Bounded per-browser queues: slow clients never block collection."""
    def __init__(self):
        self.subscribers = defaultdict(set)

    def subscribe(self, game_id):
        queue = asyncio.Queue(maxsize=32)
        self.subscribers[game_id].add(queue)
        return queue

    def unsubscribe(self, game_id, queue):
        self.subscribers[game_id].discard(queue)
        if not self.subscribers[game_id]:
            self.subscribers.pop(game_id, None)

    def publish(self, game_id, kind, data):
        for queue in self.subscribers.get(game_id, ()):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait({'type': kind, 'data': data})
