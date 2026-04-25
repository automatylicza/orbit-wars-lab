"""Test fixture: agent that crashes with sys.exit(1) on first call."""
import sys


def agent(obs):
    sys.exit(1)
