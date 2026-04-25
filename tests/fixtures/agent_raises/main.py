"""Test fixture: agent that raises RuntimeError on every call."""


def agent(obs):
    raise RuntimeError("boom")
