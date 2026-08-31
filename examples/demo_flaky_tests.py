"""A small, intentionally flaky test file for trying out flakeradar.

Run:
    flakeradar stress examples/demo_flaky_tests.py -k test_race_condition -n 30
    flakeradar stress examples/demo_flaky_tests.py -k test_timing_sensitive -n 30
    flakeradar stress examples/demo_flaky_tests.py -k test_always_stable -n 10

Then:
    flakeradar report --open
"""

import random
import time


def test_always_stable():
    """A normal, deterministic test. Should never be flagged as flaky."""
    assert 2 + 2 == 4


def test_race_condition():
    """Simulates a race condition: shared state read/written without
    synchronization. Fails roughly 30% of the time.
    """
    shared_counter = {"value": 0}

    def increment():
        current = shared_counter["value"]
        # A tiny, realistic delay here is what causes real race conditions;
        # we simulate the effect directly for a fast, deterministic demo.
        if random.random() < 0.3:
            current -= 1  # simulate a lost update
        shared_counter["value"] = current + 1

    for _ in range(5):
        increment()

    assert shared_counter["value"] == 5


def test_timing_sensitive():
    """Simulates a test that assumes an operation completes within a fixed
    window - a very common source of real-world flakiness.
    """
    start = time.monotonic()
    # Simulate work with variable duration.
    time.sleep(random.uniform(0.0, 0.02))
    elapsed = time.monotonic() - start
    assert elapsed < 0.015


def test_nondeterministic_data():
    """Simulates asserting on data that isn't actually guaranteed to be
    stable, e.g. relying on dict/set iteration order or unseeded randomness.
    """
    value = random.randint(1, 100)
    assert value <= 80
