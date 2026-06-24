"""Tests for automatic CLI run-id allocation."""



from __future__ import annotations



import threading

from pathlib import Path



from harness.cli.run_id_allocator import (

    _cross_process_lock,

    _sequence_root,

    allocate_automatic_run_id,

)





def _multiprocess_allocate_worker(result_queue, harness_root_str: str) -> None:

    import config.paths as paths_mod



    paths_mod.harness_cli_artifacts_root = lambda: Path(harness_root_str)

    try:

        allocated = allocate_automatic_run_id(run_collection="deed_to_ir")

        result_queue.put(("ok", allocated.run_id))

    except Exception as exc:

        result_queue.put(("err", repr(exc)))





def test_automatic_run_ids_are_sequential_per_collection(isolated_harness_root) -> None:

    first = allocate_automatic_run_id(run_collection="deed_to_ir")

    second = allocate_automatic_run_id(run_collection="deed_to_ir")

    assert first.run_id == "deed-to-ir-live-r00000001"

    assert second.run_id == "deed-to-ir-live-r00000002"

    assert first.run_dir.is_dir()

    assert second.run_dir.is_dir()

    assert first.run_dir != second.run_dir





def test_automatic_run_ids_are_independent_across_collections(isolated_harness_root) -> None:

    deed = allocate_automatic_run_id(run_collection="deed_to_ir")

    transcript = allocate_automatic_run_id(run_collection="transcript_edit")

    assert deed.run_id == "deed-to-ir-live-r00000001"

    assert transcript.run_id == "transcript-edit-live-r00000001"

    assert deed.run_collection == "deed_to_ir"

    assert transcript.run_collection == "transcript_edit"





def test_allocator_recovers_counter_from_existing_run_dirs(isolated_harness_root) -> None:

    collection_root = isolated_harness_root / "cli_runs" / "by_loop_kind" / "deed_to_ir"

    existing = collection_root / "deed-to-ir-live-r00000007"

    existing.mkdir(parents=True)

    allocated = allocate_automatic_run_id(run_collection="deed_to_ir")

    assert allocated.run_id == "deed-to-ir-live-r00000008"

    counter_path = collection_root / ".run_id_sequences" / "counter.json"

    assert counter_path.is_file()





def test_allocated_run_exposes_human_timeline_path(isolated_harness_root) -> None:

    allocated = allocate_automatic_run_id(run_collection="deed_to_ir")

    assert allocated.human_timeline_path == Path(allocated.run_dir) / "audit" / "human" / "timeline.md"





def test_legacy_stale_lock_file_does_not_block_allocation(isolated_harness_root) -> None:

    lock_path = _sequence_root("deed_to_ir") / "allocate.lock"

    lock_path.parent.mkdir(parents=True, exist_ok=True)

    lock_path.write_text("99999999:dead-legacy-token", encoding="ascii")

    allocated = allocate_automatic_run_id(run_collection="deed_to_ir")

    assert allocated.run_id == "deed-to-ir-live-r00000001"

    assert lock_path.is_file()





def test_cross_process_lock_releases_without_unlinking(tmp_path) -> None:

    lock_path = tmp_path / "allocate.lock"

    with _cross_process_lock(lock_path) as first_lock:

        first_token = first_lock._lock_token

        assert first_token

    assert lock_path.is_file()

    with _cross_process_lock(lock_path) as second_lock:

        second_token = second_lock._lock_token

    assert second_token

    assert first_token != second_token





def test_concurrent_allocations_receive_distinct_ids(isolated_harness_root) -> None:

    results: list[str] = []

    errors: list[Exception] = []



    def _worker() -> None:

        try:

            allocated = allocate_automatic_run_id(run_collection="deed_to_ir")

            results.append(allocated.run_id)

        except Exception as exc:

            errors.append(exc)



    threads = [threading.Thread(target=_worker) for _ in range(6)]

    for thread in threads:

        thread.start()

    for thread in threads:

        thread.join(timeout=30.0)

        assert not thread.is_alive()



    assert not errors, errors

    assert len(results) == 6

    assert len(set(results)) == 6





def test_multiprocess_concurrent_allocations_receive_distinct_ids(isolated_harness_root) -> None:

    import multiprocessing as mp



    ctx = mp.get_context("spawn")

    result_queue = ctx.Queue()

    root_str = str(isolated_harness_root)

    processes = [

        ctx.Process(target=_multiprocess_allocate_worker, args=(result_queue, root_str))

        for _ in range(4)

    ]

    for process in processes:

        process.start()

    for process in processes:

        process.join(timeout=60.0)

        assert process.exitcode == 0, f"worker exited with code {process.exitcode}"



    outcomes = [result_queue.get(timeout=5.0) for _ in range(4)]

    errors = [value for kind, value in outcomes if kind == "err"]

    assert not errors, errors

    run_ids = [value for kind, value in outcomes if kind == "ok"]

    assert len(run_ids) == 4

    assert len(set(run_ids)) == 4





def test_multiprocess_allocation_with_legacy_stale_lock_file(isolated_harness_root) -> None:

    import multiprocessing as mp



    lock_path = _sequence_root("deed_to_ir") / "allocate.lock"

    lock_path.parent.mkdir(parents=True, exist_ok=True)

    lock_path.write_text("99999999:dead-legacy-token", encoding="ascii")



    ctx = mp.get_context("spawn")

    result_queue = ctx.Queue()

    root_str = str(isolated_harness_root)

    processes = [

        ctx.Process(target=_multiprocess_allocate_worker, args=(result_queue, root_str))

        for _ in range(2)

    ]

    for process in processes:

        process.start()

    for process in processes:

        process.join(timeout=60.0)

        assert process.exitcode == 0, f"worker exited with code {process.exitcode}"



    outcomes = [result_queue.get(timeout=5.0) for _ in range(2)]

    errors = [value for kind, value in outcomes if kind == "err"]

    assert not errors, errors

    run_ids = sorted(value for kind, value in outcomes if kind == "ok")

    assert run_ids == ["deed-to-ir-live-r00000001", "deed-to-ir-live-r00000002"]

    assert lock_path.is_file()


