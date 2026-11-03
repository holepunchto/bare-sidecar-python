# bare-sidecar-python

Start and manage Bare sidecar processes from Python, each running Bare alongside the application with an IPC to it exposed as `Bare.IPC` inside the process.

```
pip install bare-sidecar
```

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

## API

#### `versions`

A read-only mapping of the versions of the components shipped with this package, named as in `Bare.versions`. For example, `versions["bare"]` is the version of the bundled Bare.

```python
from bare_sidecar import versions

print(versions["bare"])
```

## License

Apache-2.0
