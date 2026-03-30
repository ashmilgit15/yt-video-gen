import asyncio
import audio_gen


async def test():
    tasks = [audio_gen.generate_audio("Hello", i, "test", "Sarah") for i in range(6)]
    results = await asyncio.gather(*tasks)
    print(results)


asyncio.run(test())
