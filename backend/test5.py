import asyncio


async def test():
    try:
        await asyncio.create_subprocess_exec("C:\\invalid\\path.exe", "arg")
    except Exception as e:
        print(repr(e))
        print("STRING", str(e))


asyncio.run(test())
