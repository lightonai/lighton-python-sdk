"""Batch ingestion, upload many files into a workspace, sync or as a background job.

`Workspace.ingest_many()` coerces paths/Files (expanding glob-pattern strings),
validates every local path **up front** (fail fast, before any upload), then uploads
concurrently. Rate limiting and the 429
cooldown are handled centrally by the client (`LightOnConfiguration.
max_requests_per_minute` / `rate_limit_retries`), so a large batch stays under the cap
across uploads *and* status polls without any per-call work here.

SYNC (default) blocks and returns a `BatchIngest`. ASYNC returns a `BatchIngestJob`
you poll for live progress and inspect for failures while it's still running.
"""

from __future__ import annotations

import glob
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from lighton.file import File
from lighton.types.batch import BatchIngest, BatchProgress, FailedIngest

_GLOB_CHARS = "*?["  # a string item with any of these is expanded as a glob pattern

if TYPE_CHECKING:
    from lighton._client import LightOn


class BatchIngestJob:
    """A running (or finished) batch ingestion.

    Returned by `Workspace.ingest_many(mode=ExecMode.ASYNC)`. Uploads (and, when
    `wait=True`, ingestion polls) run in a background thread; read `progress`,
    `succeeded`, and `failed` at any time, or block with `wait()`.
    """

    def __init__(
        self,
        client: LightOn,
        workspace_id: int,
        files: list[File],
        prefailed: list[FailedIngest],
        *,
        wait: bool,
        timeout: float,
        max_workers: int,
        tags: list[int] | None,
        ignore_errors: bool,
    ) -> None:
        self._client = client
        self._workspace_id = workspace_id
        self._files = files
        self._wait = wait
        self._timeout = timeout
        self._max_workers = max_workers
        self._tags = tags
        self._ignore_errors = ignore_errors

        self._lock = threading.Lock()
        self._succeeded: list[File] = []
        self._failed: list[FailedIngest] = list(prefailed)
        self._uploaded = 0
        self._ingested = 0
        self._total = len(files) + len(prefailed)
        self._finished = threading.Event()
        self._error: Exception | None = None
        self._thread: threading.Thread | None = None

    # --- public read surface ----------------------------------------------
    @property
    def done(self) -> bool:
        """True once every file has reached a terminal state (ok or failed)."""
        return self._finished.is_set()

    @property
    def progress(self) -> BatchProgress:
        """A consistent snapshot of counts (safe to read while the batch runs)."""
        with self._lock:
            return BatchProgress(
                total=self._total,
                uploaded=self._uploaded,
                ingested=self._ingested,
                failed=len(self._failed),
                done=self._finished.is_set(),
            )

    @property
    def succeeded(self) -> list[File]:
        """Files that have succeeded so far (a copy, safe to iterate)."""
        with self._lock:
            return list(self._succeeded)

    @property
    def failed(self) -> list[FailedIngest]:
        """Failures so far (a copy, safe to iterate), available mid-run."""
        with self._lock:
            return list(self._failed)

    @property
    def result(self) -> BatchIngest:
        """Current succeeded/failed as a `BatchIngest` (terminal once `done`)."""
        with self._lock:
            return BatchIngest(
                succeeded=list(self._succeeded), failed=list(self._failed)
            )

    def poll(self) -> BatchProgress:
        """Return the current progress. Mirror of the parse/extract job's poll();
        state updates itself in the background thread, so this just snapshots it."""
        return self.progress

    def wait(self, timeout: float | None = None) -> BatchIngest:
        """Block until the batch finishes, then return its result.

        Args:
            timeout: Max seconds to wait for the whole batch; None waits forever.

        Returns:
            The terminal `BatchIngest`.

        Raises:
            TimeoutError: If the batch doesn't finish within `timeout`.
            Exception: The first upload/ingestion error, re-raised, when the batch
                ran with `ignore_errors=False`.
        """
        if not self._finished.wait(timeout):
            raise TimeoutError("batch ingestion did not finish in time")
        if self._error is not None:
            raise self._error
        return self.result

    # --- execution --------------------------------------------------------
    def _start_background(self) -> None:
        self._thread = threading.Thread(target=self._run_background, daemon=True)
        self._thread.start()

    def _run_background(self) -> None:
        try:
            self._execute()
        except Exception as e:  # not ignore_errors → surfaced by wait()
            self._error = e
        finally:
            self._finished.set()

    def _execute(self) -> None:
        """Upload every file, then (if wait) poll each to a terminal state.

        Runs inline for SYNC (errors propagate directly) or in the background thread
        for ASYNC (errors are stored on `_error`).
        """
        with ThreadPoolExecutor(max_workers=self._max_workers) as ex:
            uploaded = self._run_phase(ex, self._files, self._upload_one)
            if self._wait and uploaded:
                self._run_phase(ex, uploaded, self._wait_one)

    def _run_phase(
        self,
        ex: ThreadPoolExecutor,
        items: list[File],
        fn: Callable[[File], File | None],
    ) -> list[File]:
        """Run `fn` over `items` concurrently; return the ones that succeeded.

        On the first error when `ignore_errors=False`, stop early: cancel whatever
        hasn't started and re-raise. ponytail: already-running uploads still finish
        (the executor drains on shutdown), we don't hard-kill in-flight requests.
        """
        done_ok: list[File] = []
        futures: dict[Future[File | None], File] = {
            ex.submit(fn, it): it for it in items
        }
        try:
            for fut in as_completed(futures):
                res = fut.result()  # re-raises if fn raised (ignore_errors=False)
                if res is not None:
                    done_ok.append(res)
        except Exception:
            for f in futures:
                f.cancel()
            raise
        return done_ok

    def _upload_one(self, file: File) -> File | None:
        try:
            file.workspace_id = self._workspace_id
            created = file.create(self._client, tags=self._tags)
        except Exception as e:
            self._record_failure(file.path, e, None)
            if not self._ignore_errors:
                raise
            return None
        with self._lock:
            self._uploaded += 1
            if not self._wait:  # no ingestion wait → uploaded counts as succeeded
                self._succeeded.append(created)
        return created

    def _wait_one(self, file: File) -> File | None:
        try:
            file.wait(self._timeout)
        except Exception as e:
            self._record_failure(file.path, e, file)
            if not self._ignore_errors:
                raise
            return None
        with self._lock:
            self._ingested += 1
            self._succeeded.append(file)
        return file

    def _record_failure(
        self, source: Path | None, error: Exception, file: File | None
    ) -> None:
        with self._lock:
            self._failed.append(
                FailedIngest(source=source or Path(""), error=error, file=file)
            )


def _prepare(
    items: list[File | str | Path], ignore_errors: bool
) -> tuple[list[File], list[FailedIngest]]:
    """Coerce items to Files and split into (uploadable, pre-failed missing paths).

    Validates every local path exists *before* any upload. With ignore_errors=False a
    missing path raises immediately; with True it goes straight into the failed list.

    A **string** item containing glob characters (`*?[`) is expanded via
    `glob.glob(..., recursive=True)`, matches are filtered to existing files, and a
    pattern matching nothing is treated like a missing path. `File`/`Path` items are
    always literal. Results are deduped by resolved path so overlapping patterns (or a
    file listed both explicitly and by a glob) upload only once.
    """
    files: list[File] = []
    missing: list[Path] = []
    seen: set[Path] = set()

    def take(f: File) -> None:
        assert f.path is not None
        key = f.path.resolve()
        if key not in seen:  # dedupe by resolved path, no double uploads
            seen.add(key)
            files.append(f)

    for item in items:
        if isinstance(item, File):
            if item.path is None:
                raise ValueError(f"cannot ingest a File with no path: {item!r}")
            if item.path.is_file():
                take(item)
            else:
                missing.append(item.path)
        elif isinstance(item, str) and any(c in item for c in _GLOB_CHARS):
            hits = sorted(
                p for p in map(Path, glob.glob(item, recursive=True)) if p.is_file()
            )
            if not hits:
                missing.append(
                    Path(item)
                )  # zero-match glob, surfaced like a missing path
            for p in hits:
                take(File(path=p))
        else:
            p = Path(item)
            if p.is_file():
                take(File(path=p))
            else:
                missing.append(p)

    if missing and not ignore_errors:
        listed = ", ".join(str(p) for p in missing)
        raise FileNotFoundError(
            f"{len(missing)} path(s)/pattern(s) matched no file: {listed}"
        )
    prefailed = [
        FailedIngest(source=p, error=FileNotFoundError(str(p))) for p in missing
    ]
    return files, prefailed


def run(
    client: LightOn,
    workspace_id: int,
    items: list[File | str | Path],
    *,
    async_: bool,
    ignore_errors: bool,
    wait: bool,
    timeout: float,
    max_workers: int,
    tags: list[int] | None,
) -> BatchIngest | BatchIngestJob:
    """Validate, then run the batch inline (sync) or in a background thread (async).

    Validation runs in the caller's thread either way, so a bad path raises at the
    call site rather than inside a background thread.
    """
    files, prefailed = _prepare(items, ignore_errors)
    job = BatchIngestJob(
        client,
        workspace_id,
        files,
        prefailed,
        wait=wait,
        timeout=timeout,
        max_workers=max_workers,
        tags=tags,
        ignore_errors=ignore_errors,
    )
    if async_:
        job._start_background()
        return job
    job._execute()  # inline; raises directly when ignore_errors=False
    job._finished.set()
    return job.result
