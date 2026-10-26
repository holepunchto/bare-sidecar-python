# bare-sidecar-python

Start and manage Bare sidecar processes from Python. The Python counterpart of [bare-sidecar](https://github.com/holepunchto/bare-sidecar): it runs a Bare entry point in a child process with an IPC connection to it, exposed as `Bare.IPC` inside the process. The Bare executable is shipped in platform wheels.

```
pip install bare-sidecar
```

Platform wheels are published for macOS 13 and later, Linux with glibc 2.34 and later, and Windows, each on arm64 and x64.

## Usage

```python
import asyncio

from bare_sidecar import spawn


async def main():
    async with await spawn("app.js") as sidecar:
        await sidecar.write(b"Hello world")

        async for data in sidecar:
            print(data)


asyncio.run(main())
```

Where `app.js` is a Bare entry point using `Bare.IPC`:

```js
Bare.IPC.on('data', (data) => Bare.IPC.write(data))
```

## License

Apache-2.0
