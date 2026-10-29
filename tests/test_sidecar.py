import asyncio
import sys
from pathlib import Path

from bare_sidecar import spawn

FIXTURES = Path(__file__).parent / "fixtures"


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, 10))


def test_echoes_ipc_data():
    async def body():
        async with await spawn(FIXTURES / "echo.js") as sidecar:
            await sidecar.write(b"Hello world")
            return await sidecar.read()

    assert run(body()) == b"Hello world"


def test_passes_arguments():
    async def body():
        async with await spawn(FIXTURES / "argv.js", "foo", "bar") as sidecar:
            return b"".join([chunk async for chunk in sidecar])

    assert run(body()) == b'["foo","bar"]'


def test_reports_the_exit_code():
    async def body():
        async with await spawn(FIXTURES / "exit.js") as sidecar:
            return await sidecar.wait(), await sidecar.read()

    assert run(body()) == (3, b"")


def test_exits_after_ipc_destroy_while_writing():
    async def body():
        async with await spawn(FIXTURES / "ipc-destroy-exit.js") as sidecar:
            while sidecar.returncode is None:
                await sidecar.write(b"Hello world")
                await asyncio.sleep(0.01)

            return await sidecar.wait()

    assert run(body()) == 3


def test_pipes_stdout():
    async def body():
        stdio = ("inherit", "pipe", "inherit")

        async with await spawn(FIXTURES / "log.js", stdio=stdio) as sidecar:
            return await sidecar.stdout.read()

    assert run(body()).splitlines() == [b"Hello world"]


def test_terminate_and_kill_end_the_process():
    async def body(end):
        async with await spawn(FIXTURES / "sleep.js") as sidecar:
            end(sidecar)
            await sidecar.wait()
            return sidecar.exit_code, sidecar.signal_code

    # Windows has no signals, and terminates the process with exit code 1.
    if sys.platform == "win32":
        assert run(body(lambda sidecar: sidecar.terminate())) == (1, None)
        assert run(body(lambda sidecar: sidecar.kill())) == (1, None)
    else:
        assert run(body(lambda sidecar: sidecar.terminate())) == (None, "SIGTERM")
        assert run(body(lambda sidecar: sidecar.kill())) == (None, "SIGKILL")


def test_reports_the_exit_code_without_a_signal():
    async def body():
        async with await spawn(FIXTURES / "exit.js") as sidecar:
            await sidecar.wait()
            return sidecar.exit_code, sidecar.signal_code

    assert run(body()) == (3, None)


def test_close_waits_for_the_process_to_exit():
    async def body():
        sidecar = await spawn(FIXTURES / "sleep.js")
        await sidecar.close()
        return sidecar.returncode

    assert run(body()) is not None


def test_reading_to_the_end_releases_the_connection():
    async def body():
        sidecar = await spawn(FIXTURES / "exit.js")
        await sidecar.wait()
        return await sidecar.read()

    assert run(body()) == b""
