"""Optional Mnemosyne mirror (HERAMA_MEMORY_BACKEND=mnemosyne).

SQLite stays the source of truth (ids, delete); Mnemosyne only adds semantic recall.
UNVERIFIED against the real package: written from its documented
`from mnemosyne import remember, recall` API. Falls back to None if unavailable.
"""
import logging

log = logging.getLogger("herama.memory")


class Mirror:
    def __init__(self, remember, recall):
        self._remember, self._recall = remember, recall

    def remember(self, text: str):
        try:
            self._remember(text, importance=0.5, source="herama")
        except Exception as e:  # never break chat over the mirror
            log.warning("mnemosyne remember failed: %s", e)

    def recall(self, query: str, k: int) -> list[str]:
        try:
            res = self._recall(query, top_k=k) or []
        except Exception as e:
            log.warning("mnemosyne recall failed: %s", e)
            return []
        out = []
        for r in res:
            if isinstance(r, str):
                out.append(r)
            elif isinstance(r, dict):
                t = r.get("content") or r.get("text") or r.get("memory")
                if t:
                    out.append(t)
        return out


def load():
    try:
        from mnemosyne import recall, remember
    except Exception as e:
        log.warning("mnemosyne unavailable (%s); using sqlite only", e)
        return None
    return Mirror(remember, recall)
