import asyncio
import os
import secrets
import socket
import sys

# Not exposed by `_winapi`.
PIPE_REJECT_REMOTE_CLIENTS = 0x00000008

BUFSIZE = 65536


class Channel:
    """An IPC connection between this process and a child yet to be spawned.

    ``value`` names the child's end, as a descriptor or on Windows a handle, and
    ``options`` are the subprocess options that pass it to the child.
    ``release()`` closes this process' copy of it once the child is spawned.
    """

    def __init__(self, reader, writer, value, options, release):
        self.reader = reader
        self.writer = writer
        self.value = value
        self.options = options
        self.release = release


async def open_channel():
    if sys.platform == "win32":
        return await _open_pipe()

    return await _open_socketpair()


async def _open_socketpair():
    parent, child = socket.socketpair()

    try:
        reader, writer = await asyncio.open_unix_connection(sock=parent)
    except BaseException:
        parent.close()
        child.close()
        raise

    fd = child.fileno()

    return Channel(reader, writer, str(fd), {"pass_fds": (fd,)}, child.close)


async def _open_pipe():
    import _winapi
    import subprocess

    name = rf"\\.\pipe\bare-sidecar-{os.getpid()}-{secrets.token_hex(8)}"

    # A single instance that this process connects to before the child exists,
    # so that no other process can connect in its place.
    child = _winapi.CreateNamedPipe(
        name,
        _winapi.PIPE_ACCESS_DUPLEX
        | _winapi.FILE_FLAG_OVERLAPPED
        | _winapi.FILE_FLAG_FIRST_PIPE_INSTANCE,
        _winapi.PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
        1,
        BUFSIZE,
        BUFSIZE,
        _winapi.NMPWAIT_WAIT_FOREVER,
        _winapi.NULL,
    )

    try:
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        transport, _ = await loop.create_pipe_connection(lambda: protocol, name)
        writer = asyncio.StreamWriter(transport, protocol, reader, loop)
        os.set_handle_inheritable(child, True)
    except BaseException:
        _winapi.CloseHandle(child)
        raise

    startupinfo = subprocess.STARTUPINFO(lpAttributeList={"handle_list": [child]})

    return Channel(
        reader,
        writer,
        str(child),
        {"startupinfo": startupinfo},
        lambda: _winapi.CloseHandle(child),
    )
