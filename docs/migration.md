# 0.2 → 0.3 migration and rollback

1. Finish/stop all experiments and fully exit the Python app.
2. Copy the whole data root to a backup. Never run old/new owners on the same root, even with different ports: Python does not understand the ownership lock.
3. Start the new version with the same normal data root. Custom legacy state/run overrides need explicit consolidation; log paths are not guessed or moved.

An old `user_version=0` database is backed up with SQLite `VACUUM INTO` to `.pipedl/pipedl-pre-v3.db`, including committed WAL contents. The backup is never overwritten. Migration adds an index and sets schema version 1; it does not drop history or rewrite logs. Newer schemas are refused.

Old running/paused/stopping rows become `orphaned`, and the queue pauses. Verify/end old experiments externally, then use “确认旧进程已结束”. Resolution refuses while the old PID exists, including PID reuse; inherited PIDs are never killed automatically. For WSL also verify the Linux workload has ended: the Windows host PID is not sufficient evidence.

## Changed behavior

- Authenticated HTTP replaces the control CLI and its PATH entry.
- cwd must be absolute, and exist for host-native runners.
- Window close hides to tray; Quit refuses with owned active work.
- Control routes target the supplied ID.
- Queued ordering is compacted; history pagination cannot truncate scheduling.
- Windows stop terminates the owned job tree; native pause/resume replaces nonexistent PowerShell cmdlets.
- Updates open the official release page. No unsigned unattended installer execution.
- Demo x5 is replaced by reproducible short integration checks, not included as a production control.

## Rollback

Stop new-version tasks and exit. Archive the current whole data root to preserve new history. Restore the pre-upgrade backup to a separate data root. Obtain the old Python implementation from `legacy/python/` in Git tag `v0.3.2` using a separate checkout, and configure it to use the restored data root. If restoring only `pipedl-pre-v3.db`, copy it to `.pipedl/pipedl.db` in a fresh directory without WAL/SHM files, preserving logs and their absolute paths. Never overwrite a live database or automatically merge backups with newer history.

The backup/quarantine behavior is checked by `src-tauri/tests/storage.rs`. Production rollback remains an operator action.
