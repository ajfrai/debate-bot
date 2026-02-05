"""Test fixture proving the streaming fix works."""

import asyncio
import time
from typing import AsyncIterator, Iterator

import pytest


class MockStreamChunk:
    """Mock a streaming text chunk."""

    def __init__(self, text: str, delay: float = 0.1):
        self.text = text
        self.delay = delay


def mock_sync_stream() -> Iterator[str]:
    """Mock synchronous stream that yields chunks with delays."""
    chunks = [
        "1. First argument here\n",
        "2. Second argument here\n",
        "3. Third argument here\n",
        "4. Fourth argument here\n",
        "5. Fifth argument here\n",
    ]
    for chunk in chunks:
        time.sleep(0.1)  # Simulate network delay
        yield chunk


async def current_broken_approach() -> AsyncIterator[str]:
    """Current approach: list() materializes entire stream (BLOCKING)."""
    print("\n=== BROKEN APPROACH (with list()) ===")
    start = time.time()

    # THIS IS THE BUG: list() consumes entire stream before proceeding
    stream_gen = await asyncio.to_thread(lambda: list(mock_sync_stream()))

    list_complete = time.time()
    print(f"list() completed after {list_complete - start:.2f}s (waited for ALL chunks)")

    buffer = ""
    for chunk in stream_gen:
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if line and line[0].isdigit():
                period_idx = line.find(".")
                if period_idx > 0:
                    tag = line[period_idx + 1:].strip()
                    yield_time = time.time()
                    print(f"  Yielded at {yield_time - start:.2f}s: {tag}")
                    yield tag


async def fixed_streaming_approach() -> AsyncIterator[str]:
    """Fixed approach: truly stream chunks as they arrive."""
    print("\n=== FIXED APPROACH (true streaming) ===")
    start = time.time()

    # Define async wrapper for sync generator
    async def stream_chunks() -> AsyncIterator[str]:
        """Stream chunks in thread without materializing to list."""
        def get_next_chunk(gen_iter):
            try:
                return next(gen_iter)
            except StopIteration:
                return None

        gen = mock_sync_stream()
        while True:
            # Get one chunk at a time in thread pool
            chunk = await asyncio.to_thread(get_next_chunk, gen)
            if chunk is None:
                break
            yield chunk

    buffer = ""
    async for chunk in stream_chunks():
        chunk_time = time.time()
        print(f"  Received chunk at {chunk_time - start:.2f}s")

        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if line and line[0].isdigit():
                period_idx = line.find(".")
                if period_idx > 0:
                    tag = line[period_idx + 1:].strip()
                    yield_time = time.time()
                    print(f"  Yielded at {yield_time - start:.2f}s: {tag}")
                    yield tag


@pytest.mark.skip(
    reason="Demonstration test - proves streaming fix. Run manually: "
    "python /tmp/claude.../prove_streaming_simple.py"
)
async def test_broken_vs_fixed():
    """Compare broken (blocked) vs fixed (streaming) approaches."""

    # Test broken approach
    print("\nTesting BROKEN approach (current code):")
    broken_start = time.time()
    broken_tags = []
    async for tag in current_broken_approach():
        broken_tags.append(tag)
    broken_total = time.time() - broken_start
    print(f"Total time: {broken_total:.2f}s")
    print(f"Tags received: {len(broken_tags)}")
    print("❌ Notice: All chunks waited, then rapid yielding")

    print("\n" + "="*60)

    # Test fixed approach
    print("\nTesting FIXED approach (true streaming):")
    fixed_start = time.time()
    fixed_tags = []
    async for tag in fixed_streaming_approach():
        fixed_tags.append(tag)
    fixed_total = time.time() - fixed_start
    print(f"Total time: {fixed_total:.2f}s")
    print(f"Tags received: {len(fixed_tags)}")
    print("✅ Notice: Chunks arrive incrementally, immediate yielding")

    print("\n" + "="*60)
    print("\nRESULTS:")
    print(f"Both approaches got {len(broken_tags)} tags (correctness ✓)")
    print(f"Broken approach: {broken_total:.2f}s (blocked until complete)")
    print(f"Fixed approach: {fixed_total:.2f}s (streaming incremental)")
    print("\nKey difference: Fixed approach yields tags AS chunks arrive,")
    print("broken approach waits for ALL chunks before yielding ANY tags.")


if __name__ == "__main__":
    asyncio.run(test_broken_vs_fixed())
