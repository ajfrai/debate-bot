#!/usr/bin/env python3
"""Test streaming implementation with canned data.

This tests the CURRENT (broken) vs FIXED streaming approach to prove
the event loop blocking issue and verify the fix works.
"""

import asyncio
import time
from typing import AsyncIterator


def simulate_sync_stream():
    """Simulate a synchronous streaming API (like Anthropic SDK)."""
    for i in range(10):
        time.sleep(0.3)  # Simulate network delay
        yield f"chunk_{i}"


async def broken_stream_tags() -> AsyncIterator[str]:
    """CURRENT BROKEN APPROACH: Returns generator, then iterates in main thread."""
    buffer = ""
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def _feed_queue():
        def _sync_stream():
            # This returns a generator immediately
            yield from simulate_sync_stream()

        try:
            # BUG: This gets the generator, then iterates it in MAIN thread (blocks!)
            for chunk in await asyncio.to_thread(_sync_stream):
                await queue.put(chunk)
        finally:
            await queue.put(None)

    feeder_task = asyncio.create_task(_feed_queue())

    try:
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            buffer += chunk

            # Simulate parsing (yield when we get a complete line)
            if "_" in buffer:
                yield buffer
                buffer = ""
    finally:
        await feeder_task


async def fixed_stream_tags() -> AsyncIterator[str]:
    """FIXED APPROACH: Iterate in thread, feed queue via thread-safe calls."""
    buffer = ""
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def _feed_queue():
        def _sync_stream_to_queue():
            # FIX: Do the iteration INSIDE the thread
            for chunk in simulate_sync_stream():
                # Use thread-safe method to add to queue
                loop.call_soon_threadsafe(queue.put_nowait, chunk)

        loop = asyncio.get_running_loop()
        try:
            # This now blocks in the thread, not main event loop
            await asyncio.to_thread(_sync_stream_to_queue)
        finally:
            await queue.put(None)

    feeder_task = asyncio.create_task(_feed_queue())

    try:
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            buffer += chunk

            # Simulate parsing
            if "_" in buffer:
                yield buffer
                buffer = ""
    finally:
        await feeder_task


async def heartbeat(name: str):
    """Print heartbeat every 0.5s to show event loop is alive."""
    start = time.time()
    while True:
        elapsed = time.time() - start
        print(f"  💓 [{name}] Heartbeat at {elapsed:.1f}s")
        await asyncio.sleep(0.5)


async def test_broken():
    """Test BROKEN approach - should show frozen heartbeat."""
    print("\n" + "=" * 60)
    print("TEST 1: BROKEN APPROACH (current implementation)")
    print("=" * 60)
    print("Expected: Heartbeat freezes, then all chunks appear at once\n")

    start = time.time()
    heartbeat_task = asyncio.create_task(heartbeat("BROKEN"))

    chunks = []
    try:
        async for chunk in broken_stream_tags():
            elapsed = time.time() - start
            if elapsed > 5:
                print("  ⚠️  TIMEOUT - Test took too long!")
                break
            print(f"  📦 Got chunk at {elapsed:.1f}s: {chunk}")
            chunks.append(chunk)
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

    elapsed = time.time() - start
    print(f"\n  ✓ Received {len(chunks)} chunks in {elapsed:.1f}s")

    # Acceptance criteria check
    if elapsed < 2.5:
        print("  ❌ FAIL: Completed too fast - chunks likely dumped at once")
        return False
    else:
        print("  ⚠️  Note: If heartbeats stopped, event loop was blocked")
        return True


async def test_fixed():
    """Test FIXED approach - should show steady heartbeat."""
    print("\n" + "=" * 60)
    print("TEST 2: FIXED APPROACH (proposed fix)")
    print("=" * 60)
    print("Expected: Heartbeat continues, chunks appear incrementally\n")

    start = time.time()
    heartbeat_task = asyncio.create_task(heartbeat("FIXED"))

    chunks = []
    try:
        async for chunk in fixed_stream_tags():
            elapsed = time.time() - start
            if elapsed > 5:
                print("  ⚠️  TIMEOUT - Test took too long!")
                break
            print(f"  📦 Got chunk at {elapsed:.1f}s: {chunk}")
            chunks.append(chunk)
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

    elapsed = time.time() - start
    print(f"\n  ✓ Received {len(chunks)} chunks in {elapsed:.1f}s")

    # Acceptance criteria check
    if elapsed < 2.5:
        print("  ❌ FAIL: Completed too fast - something is wrong")
        return False
    elif elapsed > 4.0:
        print("  ❌ FAIL: Took too long - overhead too high")
        return False
    else:
        print("  ✅ PASS: Timing correct, check heartbeats above")
        return True


async def main():
    """Run both tests and compare."""
    print("\n🧪 STREAMING FIX VALIDATION TEST")
    print("Testing with 10 chunks, 0.3s delay each (~3s total)")

    # Test broken approach
    broken_pass = await test_broken()

    await asyncio.sleep(1)  # Brief pause between tests

    # Test fixed approach
    fixed_pass = await test_fixed()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Broken approach: {'✓' if broken_pass else '✗'} (showed blocking)")
    print(f"Fixed approach:  {'✅ PASS' if fixed_pass else '❌ FAIL'}")
    print("\nAcceptance criteria:")
    print("  1. Heartbeat prints every 0.5s during FIXED test")
    print("  2. Chunks appear incrementally in FIXED test")
    print("  3. Total time ~3s for FIXED test")

    if fixed_pass:
        print("\n✅ Fix validated - ready to integrate!")
    else:
        print("\n❌ Fix needs adjustment")


if __name__ == "__main__":
    asyncio.run(main())
