import asyncio
import os
import signal
from contextlib import suppress
from pathlib import Path

from ._host import executable_name, host
from ._ipc import open_channel

# Read by the embedder shipped with this package, which opens `Bare.IPC` from
# the descriptor, or on Windows the handle, it names.
IPC_ENV = "BARE_SIDECAR_IPC"

STDIO = {
    "inherit": None,
    "pipe": asyncio.subprocess.PIPE,
    "ignore": asyncio.subprocess.DEVNULL,
}


def executable():
    """The path of the Bare executable shipped for the running platform."""
    current = host()
    path = Path(__file__).parent / "prebuilds" / current / executable_name(current)

    if not path.is_file():
        raise FileNotFoundError(f"No Bare prebuild for {current}")

    return path


async def spawn(entry, *args, stdio="inherit", bare=None):
    """Start ``entry`` in a Bare process with an IPC connection to it and
    return its ``Sidecar``.

    ``args`` are passed to the process as ``Bare.argv``. ``stdio`` is
    ``"inherit"``, ``"pipe"``, or ``"ignore"``, either for all three standard
    streams or as a sequence of one per stream. ``bare`` is the Bare executable
    to use, defaulting to the one shipped with this package.
    """
    if isinstance(stdio, str):
        stdio = (stdio,) * 3

    stdin, stdout, stderr = (STDIO[mode] for mode in stdio)

    channel = await open_channel()

    try:
        process = await asyncio.create_subprocess_exec(
            os.fspath(bare or executable()),
            os.fspath(entry),
            *args,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            env={**os.environ, IPC_ENV: channel.value},
            **channel.options,
        )
    except BaseException:
        channel.writer.close()
        raise
    finally:
        channel.release()

    return Sidecar(process, channel.reader, channel.writer)


class Sidecar:
    """A Bare process connected to its ``Bare.IPC``.

    Iterating it with ``async for`` yields the data the process writes to
    ``Bare.IPC`` until the connection ends, and leaving ``async with`` closes
    it. Use ``spawn()`` to start one.
    """

    def __init__(self, process, reader, writer):
        self._process = process
        self._reader = reader
        self._writer = writer

    @property
    def pid(self):
        """The process ID."""
        return self._process.pid

    @property
    def returncode(self):
        """The exit code of the process, negated if killed by a signal, or
        ``None`` while it is running."""
        return self._process.returncode

    @property
    def exit_code(self):
        """The exit code of the process, or ``None`` while it is running or if
        it was killed by a signal."""
        code = self._process.returncode
        return code if code is not None and code >= 0 else None

    @property
    def signal_code(self):
        """The name of the signal that killed the process, or ``None``."""
        code = self._process.returncode
        return signal.Signals(-code).name if code is not None and code < 0 else None

    @property
    def stdin(self):
        """The standard input of the process, if spawned with ``"pipe"``."""
        return self._process.stdin

    @property
    def stdout(self):
        """The standard output of the process, if spawned with ``"pipe"``."""
        return self._process.stdout

    @property
    def stderr(self):
        """The standard error of the process, if spawned with ``"pipe"``."""
        return self._process.stderr

    async def read(self, n=65536):
        """Read up to ``n`` bytes from the process, or ``b""`` once it has
        closed its end of the connection."""
        try:
            data = await self._reader.read(n)
        except ConnectionResetError:
            # On Linux, a process that exits with data still unread resets the
            # connection rather than ending it.
            data = b""

        if not data:
            self._end()

        return data

    def _end(self):
        """Close the connection, which the process waits for before it exits
        once it has ended its side."""
        self._writer.close()

    def __aiter__(self):
        return self._chunks()

    async def _chunks(self):
        while chunk := await self.read():
            yield chunk

    async def write(self, data):
        """Write ``data`` to the process and wait for it to drain.

        Data written once the process has closed its end of the connection,
        such as while exiting, is dropped, as its exit already accounts for it.
        """
        if self._writer.is_closing():
            return

        try:
            self._writer.write(data)
            await self._writer.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_signal(self, sig):
        """Send ``sig`` to the process unless it has already exited."""
        with suppress(ProcessLookupError):
            self._process.send_signal(sig)

    def terminate(self):
        """Ask the process to exit, with ``SIGTERM`` or on Windows by
        terminating it, unless it has already exited."""
        with suppress(ProcessLookupError):
            self._process.terminate()

    def kill(self):
        """Kill the process, with ``SIGKILL`` or on Windows by terminating it,
        unless it has already exited."""
        with suppress(ProcessLookupError):
            self._process.kill()

    async def wait(self):
        """Wait for the process to exit and return its exit code, negated if it
        was killed by a signal."""
        return await self._process.wait()

    async def close(self):
        """Close the connection, terminating the process if it is still
        running, and wait for it to exit."""
        self._writer.close()

        if self._process.returncode is None:
            self.terminate()

        await self.wait()

        with suppress(OSError):
            await self._writer.wait_closed()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()
