"""Front URL adries a zoznam uz stiahnutych URL, oboje v textovych suboroch.

data/queue.txt   - URL cakajuce na stiahnutie
data/visited.txt - URL, ktore uz boli stiahnute
"""
from collections import deque


class Frontier:
    def __init__(self, queue_file, visited_file):
        self.queue_file = queue_file
        self.visited_file = visited_file
        self.queue = deque()
        self.visited = set()
        self.queued = set()

        if visited_file.exists():
            self.visited = set(visited_file.read_text(encoding="utf-8").split())
        if queue_file.exists():
            for url in queue_file.read_text(encoding="utf-8").split():
                self.add(url)

    def add(self, url, front=False):
        """Prida URL do frontu, ak este nebola stiahnuta ani nie je vo fronte."""
        if url in self.visited or url in self.queued:
            return False
        if front:
            self.queue.appendleft(url)
        else:
            self.queue.append(url)
        self.queued.add(url)
        return True

    def pop(self):
        url = self.queue.popleft()
        self.queued.discard(url)
        return url

    def mark_visited(self, url):
        self.visited.add(url)
        with self.visited_file.open("a", encoding="utf-8") as f:
            f.write(url + "\n")

    def save(self):
        self.queue_file.write_text("".join(url + "\n" for url in self.queue), encoding="utf-8")

    def __len__(self):
        return len(self.queue)
