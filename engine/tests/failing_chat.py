"""
failing_chat.py - a fake chat() for testing the wrapper. It rejects any token older than a
simulated lifetime, and it can fail in all three shapes the real gateway may show:
    shape 1  an exception whose text mentions 401
    shape 2  a dictionary that carries a status and no answer
    shape 3  a dictionary with no "answer" at all
It reads the token from the live-values holder when it is CALLED, as the analyst's real
chat() cell does, and it counts calls per prompt so tests can prove nothing was asked twice.
"""
import json
import random
import threading
import time


class TokenIssuer:
    """Hands out test tokens and remembers when each was issued."""

    def __init__(self, lifetime_seconds):
        self.lifetime_seconds = lifetime_seconds
        self.issued = {}
        self.counter = 0

    def issue(self):
        self.counter += 1
        token = "TESTTOKEN-%04d-secret-do-not-persist" % self.counter
        self.issued[token] = time.time()
        return token

    def is_valid(self, token):
        return token in self.issued and time.time() - self.issued[token] < self.lifetime_seconds


def make_failing_chat(live, issuer, answer_with=None, jitter=0.0, break_every=0):
    """Returns (chat, calls). `calls` maps each main prompt to how often it was asked with a
    VALID token. `break_every`=n makes every n-th valid call fail like an outage."""
    calls, lock, state = {}, threading.Lock(), {"shape": 0, "valid_calls": 0}

    def chat(SystemPrompt, MainPrompt):
        if jitter:
            time.sleep(random.random() * jitter)          # randomised completion order
        token = live.get("llm_token")
        with lock:
            if not issuer.is_valid(token):
                state["shape"] += 1
                shape = state["shape"] % 3
            else:
                shape = -1
                state["valid_calls"] += 1
                outage = break_every and state["valid_calls"] % break_every == 0
                if not outage:
                    calls[MainPrompt] = calls.get(MainPrompt, 0) + 1
        if shape == 0:
            raise RuntimeError("HTTP 401 Unauthorized: token %s has expired" % token)
        if shape == 1:
            return {"status": 401, "message": "authentication failed for token %s" % token}
        if shape == 2:
            return {"detail": "credential expired", "echo": token}
        if outage:
            return {"status": 503, "message": "service overloaded"}
        if answer_with is not None:
            return answer_with(SystemPrompt, MainPrompt)
        return {"answer": json.dumps({"echo": MainPrompt[-40:]})}
    return chat, calls
