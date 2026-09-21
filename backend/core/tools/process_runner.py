"""Bounded, cancellable subprocesses for request handlers (no shell parsing)."""
import asyncio
import os
import signal
import subprocess


async def run_process(args, *, cwd=None, capture_output=True, text=False, check=False, timeout=30):
    options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
               if os.name == "nt" else {"start_new_session": True})
    process = await asyncio.create_subprocess_exec(
        *args, cwd=cwd, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **options)

    async def read(stream):
        output = bytearray()
        while chunk := await stream.read(65536):
            output.extend(chunk)
            if len(output) > 2 * 1024 * 1024:
                raise RuntimeError("Command output exceeds the 2 MiB response limit")
        return bytes(output)

    readers = [asyncio.create_task(read(process.stdout)), asyncio.create_task(read(process.stderr))]
    try:
        async with asyncio.timeout(timeout):
            stdout, stderr = await asyncio.gather(*readers)
            await process.wait()
    except BaseException:
        if process.returncode is None:
            if os.name == "nt":
                try:
                    await asyncio.to_thread(subprocess.run, ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                                            capture_output=True, timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.wait()
        for reader in readers:
            reader.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
        raise
    if text:
        stdout, stderr = stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
    result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
    if check:
        result.check_returncode()
    return result
