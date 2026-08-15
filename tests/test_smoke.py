import asyncio


async def test_async_smoke():
    await asyncio.sleep(0)
    assert True
