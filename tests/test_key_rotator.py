"""Tests for multi-key rotation."""

import pytest

from comobot.providers.key_rotator import KeyRotator


def test_round_robin():
    kr = KeyRotator(["k1", "k2", "k3"], strategy="round_robin")
    keys = [kr.next_key() for _ in range(6)]
    assert keys == ["k1", "k2", "k3", "k1", "k2", "k3"]


def test_random_strategy():
    kr = KeyRotator(["k1", "k2"], strategy="random")
    keys = {kr.next_key() for _ in range(20)}
    assert keys == {"k1", "k2"}


def test_least_used():
    kr = KeyRotator(["k1", "k2", "k3"], strategy="least_used")
    # Use k1 twice manually
    kr._usage_count[0] = 10
    key = kr.next_key()
    assert key in ("k2", "k3")


def test_no_keys_raises():
    kr = KeyRotator([])
    with pytest.raises(RuntimeError, match="No API keys"):
        kr.next_key()


def test_cooldown():
    kr = KeyRotator(["k1", "k2"], strategy="round_robin", cooldown_seconds=60)
    kr.mark_cooldown("k1")
    # k1 is in cooldown, should only get k2
    keys = {kr.next_key() for _ in range(5)}
    assert keys == {"k2"}


def test_all_keys_cooldown_raises():
    kr = KeyRotator(["k1"], cooldown_seconds=60)
    kr.mark_cooldown("k1")
    with pytest.raises(RuntimeError, match="cooldown"):
        kr.next_key()


def test_has_keys():
    assert KeyRotator(["k1"]).has_keys is True
    assert KeyRotator([]).has_keys is False
