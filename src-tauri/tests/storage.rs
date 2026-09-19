use pipedl::{
    engine::{Engine, Op},
    lock_and_token,
    store::{Create, Store},
};

#[test]
fn migration_queue_and_history_are_preserved() {
    let root = tempfile::tempdir().unwrap();
    let (lock, token) = lock_and_token(root.path()).unwrap();
    assert!(token.len() >= 32);
    assert!(
        lock_and_token(root.path()).is_err(),
        "a second queue owner must be refused"
    );
    let mut s = Store::open(root.path()).unwrap();
    let create = Create {
        name: "".into(),
        command: "echo test".into(),
        shell: if cfg!(windows) { "cmd" } else { "bash" }.into(),
        cwd: root.path().to_str().unwrap().into(),
        created_by: "test".into(),
        tags: "baseline".into(),
        notes: "preserve".into(),
    };
    let first = s.add(create.clone()).unwrap();
    assert_eq!(first.name, "Exp.01");
    let mut last = first.clone();
    for _ in 0..205 {
        last = s.add(create.clone()).unwrap();
    }
    s.reorder(&last.id, 1).unwrap();
    assert_eq!(s.list().unwrap()[0].id, last.id);
    assert_eq!(s.get(&first.id).unwrap().queue_position, 2);
    s.finish(&first.id, "succeeded", Some(0)).unwrap();
    assert!(s.reorder(&first.id, 1).is_err());
    let mut invalid = create;
    invalid.cwd = "relative/path".into();
    assert!(s.add(invalid).is_err());
    // Simulate a legacy database: restart must back up WAL and quarantine unowned PIDs.
    s.running(&last.id, 999999).unwrap();
    s.conn.execute_batch("PRAGMA user_version=0").unwrap();
    drop(s);
    let s = Store::open(root.path()).unwrap();
    assert!(root.path().join(".pipedl/pipedl-pre-v3.db").exists());
    assert_eq!(s.get(&first.id).unwrap().status, "succeeded");
    assert_eq!(s.get(&last.id).unwrap().status, "orphaned");
    assert!(s.paused().unwrap());
    let backup = rusqlite::Connection::open(root.path().join(".pipedl/pipedl-pre-v3.db")).unwrap();
    assert_eq!(
        backup
            .query_row("SELECT count(*) FROM experiments", [], |r| r
                .get::<_, i64>(0))
            .unwrap(),
        206
    );
    assert_eq!(
        backup
            .query_row(
                "SELECT status FROM experiments WHERE id=?1",
                [&last.id],
                |r| r.get::<_, String>(0)
            )
            .unwrap(),
        "running"
    );
    drop(lock);
}

#[test]
fn bulk_cleanup_spans_pages_and_preserves_other_states() {
    let root = tempfile::tempdir().unwrap();
    let (lock, _) = lock_and_token(root.path()).unwrap();
    let mut store = Store::open(root.path()).unwrap();
    let data = Create {
        name: "cleanup".into(),
        command: "echo test".into(),
        shell: if cfg!(windows) { "cmd" } else { "bash" }.into(),
        cwd: root.path().to_str().unwrap().into(),
        created_by: "test".into(),
        tags: "".into(),
        notes: "".into(),
    };
    let mut completed = Vec::new();
    for _ in 0..205 {
        let e = store.add(data.clone()).unwrap();
        store.finish(&e.id, "succeeded", Some(0)).unwrap();
        completed.push(e);
    }
    let mut retained = Vec::new();
    for status in ["failed", "stopped", "cancelled", "queued"] {
        let e = store.add(data.clone()).unwrap();
        if status != "queued" {
            store.finish(&e.id, status, Some(1)).unwrap();
        }
        retained.push((e.id, status));
    }
    drop(store);
    let engine = Engine::start(root.path(), lock).unwrap();
    let result = engine.call(Op::DeleteCompleted).unwrap();
    assert_eq!(result["deleted"], 205);
    assert_eq!(result["failures"], serde_json::json!([]));
    for e in completed {
        assert!(engine.call(Op::Get(e.id)).is_err());
        assert!(!std::path::Path::new(&e.stdout_path)
            .parent()
            .unwrap()
            .exists());
    }
    for (id, status) in retained {
        assert_eq!(engine.call(Op::Get(id)).unwrap()["status"], status);
    }
    assert_eq!(engine.call(Op::DeleteCompleted).unwrap()["deleted"], 0);
    engine.call(Op::Shutdown).unwrap();
}
