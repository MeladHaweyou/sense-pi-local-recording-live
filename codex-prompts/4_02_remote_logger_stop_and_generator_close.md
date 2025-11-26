# Prompt: Make remote logger stopping explicit (close generator, avoid SSH zombies)

You are an AI coding assistant working on the **sensepi** project.
Your task is to make the **remote streaming stop behaviour** more explicit,
so that SSH channels are closed cleanly and remote logger processes do not linger.

Focus on **integration changes** in the existing streaming pipeline.

---

## Context: how streaming works today

The main pieces involved in starting/stopping a remote stream:

- `sensepi/remote/ssh_client.py` – provides `exec_stream` which returns a generator.
- `sensepi/remote/pi_recorder.py` – wraps the logger commands and returns that generator.
- `sensepi/gui/tabs/tab_recorder.py` – owns the worker thread that consumes the generator.
- `sensepi/core/streaming.py` – defines `stream_lines`, `_StopStreaming`, etc.

### `SSHClient.exec_stream` (current shape)

```python
class SSHClient:
    ...

    def exec_stream(
        self,
        command: str,
        *,
        cwd: str | None = None,
        on_stdout: Callable[[str], None] | None = None,
        on_stderr: Callable[[str], None] | None = None,
    ) -> Iterable[str]:
        stdin, stdout, stderr = self._client.exec_command(
            command,
            get_pty=True,
            timeout=self._timeout,
        )
        if cwd:
            # ensure we run inside cwd
            channel = stdout.channel
            channel.send(f"cd {cwd}\n")
        def _iter_lines() -> Iterable[str]:
            for raw in iter(lambda: stdout.readline(), ""):
                line = raw.rstrip("\n")
                if not line:
                    continue
                if on_stdout:
                    on_stdout(line)
                yield line
            if on_stderr:
                for raw in iter(lambda: stderr.readline(), ""):
                    line = raw.rstrip("\n")
                    if line:
                        on_stderr(line)
        return _iter_lines()
```

### `PiRecorder.stream_mpu6050` (simplified)

```python
class PiRecorder:
    ...

    def _stream_logger(
        self,
        *,
        config_path: Path,
        extra_args: list[str],
        recording: bool,
        on_stderr: Callable[[str], None] | None = None,
    ) -> Iterable[str]:
        args = ["python", "mpu6050_multi_logger.py", "--config", str(config_path)]
        if not recording:
            args.append("--no-record")
        args.extend(extra_args)
        cmd = " ".join(args)
        return self.client.exec_stream(cmd, cwd=str(self.base_path), on_stderr=on_stderr)

    def stream_mpu6050(
        self,
        *,
        config_path: Path,
        extra_args: list[str],
        recording: bool,
        on_stderr: Callable[[str], None] | None = None,
    ) -> Iterable[str]:
        return self._stream_logger(
            config_path=config_path,
            extra_args=extra_args,
            recording=recording,
            on_stderr=on_stderr,
        )
```

### `RecorderTab` worker and stopping logic (simplified)

```python
class RecorderTab(QWidget):
    def __init__(...):
        ...
        self._stop_flag = threading.Event()
        self._worker_thread: threading.Thread | None = None
        ...

    def _start_stream(...):
        if self._worker_thread is not None:
            return

        self._stop_flag.clear()
        recorder = self._current_recorder   # wraps PiRecorder
        config_path = ...

        def _worker():
            try:
                parser = JsonLineParser(...)
                rate_ctrl = StreamRateController(...)

                def _on_sample(sample: Sample):
                    if self._stop_flag.is_set():
                        raise _StopStreaming()
                    rate_ctrl.on_sample(sample)
                    self.sample_received.emit(sample)

                def _on_stderr(line: str):
                    self.error_reported.emit(line)

                lines = recorder.stream_mpu6050(
                    config_path=config_path,
                    extra_args=extra_args,
                    recording=self._recording_mode,
                    on_stderr=_on_stderr,
                )
                stream_lines(lines, parser, _on_sample)
            except _StopStreaming:
                pass
            finally:
                self._worker_thread = None
                self.stream_stopped.emit()

        self._worker_thread = threading.Thread(target=_worker, daemon=True)
        self._worker_thread.start()

    def _stop_stream(self):
        self._stop_flag.set()
        # generator is just abandoned; eventually channel should close
```

The current stop behaviour relies on:
- Setting `_stop_flag`, which causes `_StopStreaming` to be raised from the callback.
- The worker thread exits; the generator from `exec_stream` is left to be GC'd eventually.

We want to **explicitly close the generator / SSH channel** instead of waiting for GC.

---

## What you must implement

1. **Keep a reference to the active streaming generator in `RecorderTab`**

   - Add an attribute like `self._active_stream: Iterable[str] | None = None` (or a more precise `Generator[str, None, None] | None`).
   - When starting the stream in `_start_stream`, do **not** hide the generator inside the worker closure only.
   - Instead:
     - Call `recorder.stream_mpu6050(...)` in `_start_stream` and store it on `self._active_stream` **before** starting the worker thread.
     - Pass that same generator into the worker.

   Example pattern (you will integrate it properly):

   ```python
   self._active_stream = recorder.stream_mpu6050(
       config_path=config_path,
       extra_args=extra_args,
       recording=self._recording_mode,
       on_stderr=_on_stderr,
   )

   def _worker(stream: Iterable[str]):
       ...
       stream_lines(stream, parser, _on_sample)
       ...

   self._worker_thread = threading.Thread(
       target=_worker, args=(self._active_stream,), daemon=True
   )
   ```

   In the worker's `finally`, make sure to clear `self._active_stream = None`.

2. **Explicitly close the generator when stopping**

   - In `_stop_stream`, after `self._stop_flag.set()`, check whether `self._active_stream` has a `.close()` method.
   - If it does, call it inside a `try/except Exception` block, ignoring any errors (but optionally logging them via `error_reported`).
   - Then set `self._active_stream = None`.

   ```python
   def _stop_stream(self):
       self._stop_flag.set()
       stream = self._active_stream
       self._active_stream = None
       if stream is not None:
           close = getattr(stream, "close", None)
           if callable(close):
               try:
                   close()
               except Exception as exc:
                   self.error_reported.emit(f"Error while closing stream: {exc}")
   ```

3. **Ensure `exec_stream` cleans up SSH channels in a `finally`**

   - Update `SSHClient.exec_stream` so that the generator's `finally` block
     explicitly closes the underlying channel and/or the `stdout`/`stderr` file‑like objects.

   For example (adapt the names to the actual code):

   ```python
   def exec_stream(...):
       stdin, stdout, stderr = self._client.exec_command(...)
       channel = stdout.channel

       def _iter_lines():
           try:
               for raw in iter(lambda: stdout.readline(), ""):
                   ...
                   yield line
               if on_stderr:
                   for raw in iter(lambda: stderr.readline(), ""):
                       ...
           finally:
               try:
                   stdout.close()
               except Exception:
                   pass
               try:
                   stderr.close()
               except Exception:
                   pass
               try:
                   channel.close()
               except Exception:
                   pass

       return _iter_lines()
   ```

   This ensures that when the generator is closed (via `.close()`), the remote command is torn down properly.

4. **(Optional, if straightforward) Send a polite stop signal to the remote logger**

   Only if it can be done cleanly with the existing code:

   - Add a method on `PiRecorder` like `stop_logger()` that sends `pkill -f mpu6050_multi_logger.py`
     (or a more targeted command) over SSH.
   - Call that method from `RecorderTab._stop_stream` **after** closing the generator.

   This is optional; focus first on the generator closing behaviour.

---

## Behaviour and testing expectations

After your changes:

- Clicking **Stop** in the GUI should:
  - Set the stop flag so callbacks stop processing new samples.
  - Close the generator, which closes the SSH channel deterministically.
- The remote Pi should not accumulate zombie `mpu6050_multi_logger.py` processes after repeated start/stop cycles.
- Existing start/stop semantics and GUI behaviour must remain the same for users.

---

## Constraints & style

- Keep changes minimal and local:
  - `SSHClient.exec_stream`
  - `PiRecorder` stream helpers (if needed)
  - `RecorderTab` start/stop streaming logic
- Do **not** introduce new external dependencies.
- Preserve thread‑safety: do not touch Qt widgets from the worker thread; use signals already in place.
