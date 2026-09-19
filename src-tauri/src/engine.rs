use crate::{
    process::{pid_exists, Process},
    store::{err, terminal, Create, Result, Store},
};
use serde_json::{json, Value};
use std::{
    fs::File,
    io::Write,
    path::Path,
    sync::mpsc,
    time::{Duration, Instant},
};
use tokio::sync::broadcast;

pub enum Op {
    Activate,
    Snapshot {
        offset: usize,
        limit: usize,
        filter: String,
    },
    Get(String),
    Create(Create),
    DeleteCompleted,
    Action(String, String, usize),
    Queue(bool),
    Shutdown,
}
type Request = (Op, mpsc::Sender<Result<Value>>);
#[derive(Clone)]
pub struct Engine {
    sender: mpsc::Sender<Request>,
    pub events: broadcast::Sender<u64>,
}
struct Running {
    id: String,
    process: Process,
    deadline: Option<Instant>,
    delete: bool,
}

impl Engine {
    pub fn start(root: &Path, lock: File) -> Result<Self> {
        let (sender, receiver) = mpsc::channel::<Request>();
        let (events, _) = broadcast::channel(64);
        let events_worker = events.clone();
        let root = root.to_path_buf();
        let (ready_tx, ready_rx) = mpsc::channel();
        std::thread::Builder::new()
            .name("pipedl-queue".into())
            .spawn(move || {
                let _lock = lock;
                let mut store = match Store::open(&root) {
                    Ok(s) => s,
                    Err(e) => {
                        let _ = ready_tx.send(Err(e));
                        return;
                    }
                };
                let _ = ready_tx.send(Ok(()));
                let mut running: Option<Running> = None;
                let mut revision = 0u64;
                let mut schedule = false;
                let mut activated = false;
                loop {
                    let request = if running.is_some() || schedule {
                        receiver.recv_timeout(Duration::from_millis(100))
                    } else {
                        receiver
                            .recv()
                            .map_err(|_| mpsc::RecvTimeoutError::Disconnected)
                    };
                    match request {
                        Ok((Op::Activate, reply)) => {
                            activated = true;
                            schedule = true;
                            let _ = reply.send(Ok(json!({"ok": true})));
                        }
                        Ok((Op::Shutdown, reply)) => {
                            // Normal exit is refused with active work; closing the window only hides it.
                            if running.is_some() {
                                let _ = reply
                                    .send(Err("Active experiment: stop it before quitting".into()));
                                continue;
                            }
                            let _ = reply.send(Ok(json!({"ok":true})));
                            break;
                        }
                        Ok((op, reply)) => {
                            let changes = matches!(
                                op,
                                Op::Create(_) | Op::DeleteCompleted | Op::Action(..) | Op::Queue(_)
                            );
                            let result = handle(&mut store, &mut running, op);
                            if changes && result.is_ok() {
                                schedule = true;
                                revision += 1;
                                let _ = events_worker.send(revision);
                            }
                            let _ = reply.send(result);
                        }
                        Err(mpsc::RecvTimeoutError::Disconnected) => break,
                        Err(mpsc::RecvTimeoutError::Timeout) => {}
                    }
                    if !activated {
                        continue;
                    }
                    match tick(&mut store, &mut running, &mut schedule) {
                        Ok(true) => {
                            revision += 1;
                            let _ = events_worker.send(revision);
                        }
                        Ok(false) => {}
                        Err(e) => {
                            eprintln!("queue: {e}");
                            let _ = store.pause(true);
                            schedule = false;
                            revision += 1;
                            let _ = events_worker.send(revision);
                        }
                    }
                }
            })
            .map_err(err)?;
        ready_rx.recv().map_err(err)??;
        Ok(Self { sender, events })
    }
    pub fn call(&self, op: Op) -> Result<Value> {
        let (tx, rx) = mpsc::channel();
        self.sender.send((op, tx)).map_err(err)?;
        rx.recv().map_err(err)?
    }
    pub async fn request(&self, op: Op) -> Result<Value> {
        let engine = self.clone();
        tokio::task::spawn_blocking(move || engine.call(op))
            .await
            .map_err(err)?
    }
}

fn handle(store: &mut Store, running: &mut Option<Running>, op: Op) -> Result<Value> {
    match op {
        Op::Snapshot {
            offset,
            limit,
            filter,
        } => {
            let all = store.list()?;
            let mut summary = json!({"running":0,"paused_processes":0,"queued":0,"succeeded":0,"failed":0,"stopped":0,"cancelled":0,"stopping":0,"orphaned":0,"paused":store.paused()?});
            for e in &all {
                let key = if e.status == "paused" {
                    "paused_processes"
                } else {
                    &e.status
                };
                summary[key] = json!(summary[key].as_u64().unwrap_or(0) + 1);
            }
            let filtered: Vec<_> = all
                .into_iter()
                .filter(|e| match filter.as_str() {
                    "active" => !terminal(&e.status),
                    "history" => terminal(&e.status),
                    "" | "all" => true,
                    s => e.status == s,
                })
                .collect();
            let total = filtered.len();
            let rows: Vec<_> = filtered.into_iter().skip(offset).take(limit).collect();
            Ok(
                json!({"experiments":rows,"total":total,"summary":summary,"offset":offset,"limit":limit}),
            )
        }
        Op::Get(id) => serde_json::to_value(store.get(&id)?).map_err(err),
        Op::Create(data) => serde_json::to_value(store.add(data)?).map_err(err),
        Op::DeleteCompleted => {
            let completed = store
                .list()?
                .into_iter()
                .filter(|e| e.status == "succeeded");
            let mut deleted = 0;
            let mut failures = Vec::new();
            for e in completed {
                match store.delete(&e.id) {
                    Ok(()) => deleted += 1,
                    Err(error) => failures.push(json!({"id": e.id, "error": error})),
                }
            }
            Ok(json!({"deleted": deleted, "failures": failures}))
        }
        Op::Queue(paused) => {
            if !paused && store.list()?.iter().any(|e| e.status == "orphaned") {
                return Err("Resolve interrupted experiments before resuming the queue".into());
            }
            store.pause(paused)?;
            Ok(json!({"ok":true,"paused":paused}))
        }
        Op::Action(id, action, position) => {
            let e = store.get(&id)?;
            match action.as_str() {
                "stop" | "pause" | "resume" => {
                    let r = running
                        .as_mut()
                        .filter(|r| r.id == id)
                        .ok_or("This experiment is not the owned active process")?;
                    let next = match (action.as_str(), e.status.as_str()) {
                        ("stop", "running" | "paused") => "stopping",
                        ("pause", "running") => "paused",
                        ("resume", "paused") => "running",
                        _ => return Err("Invalid action for current state".into()),
                    };
                    r.process.signal(&action)?;
                    store.status(&id, next)?;
                    if action == "stop" {
                        r.deadline = Some(Instant::now() + Duration::from_secs(8));
                    }
                }
                "cancel" => {
                    if e.status != "queued" {
                        return Err("only queued experiments can be cancelled".into());
                    }
                    store.finish(&id, "cancelled", None)?;
                }
                "delete" => {
                    if e.status == "orphaned" {
                        return Err("Resolve this interrupted experiment before deleting it".into());
                    }
                    if let Some(r) = running.as_mut().filter(|r| r.id == id) {
                        r.process.signal("stop")?;
                        store.status(&id, "stopping")?;
                        r.delete = true;
                        r.deadline = Some(Instant::now() + Duration::from_secs(8));
                    } else {
                        store.delete(&id)?;
                    }
                }
                "retry" => {
                    if !terminal(&e.status) {
                        return Err("retry is only available for finished experiments".into());
                    }
                    return serde_json::to_value(store.add(Create {
                        name: format!("{} retry", e.name.trim_end_matches(" retry")),
                        command: e.command,
                        shell: e.shell,
                        cwd: e.cwd,
                        created_by: format!("retry:{}", e.id),
                        tags: e.tags,
                        notes: e.notes,
                    })?)
                    .map_err(err);
                }
                "move" => store.reorder(&id, position)?,
                "resolve" => {
                    if e.status != "orphaned" {
                        return Err("only interrupted experiments can be resolved".into());
                    }
                    if e.pid.is_some_and(pid_exists) {
                        return Err("Previous PID is still alive. End/verify that process outside PipeDL first; it will not be signalled automatically".into());
                    }
                    store.finish(&id, "failed", None)?;
                }
                _ => return Err("not found".into()),
            }
            Ok(json!({"ok":true}))
        }
        Op::Shutdown | Op::Activate => unreachable!(),
    }
}
fn tick(store: &mut Store, running: &mut Option<Running>, schedule: &mut bool) -> Result<bool> {
    let mut changed = false;
    if let Some(r) = running.as_mut() {
        if r.deadline.is_some_and(|d| Instant::now() >= d) {
            r.process.signal("kill")?;
            r.deadline = None;
        }
        if let Some(exit) = r.process.child.try_wait().map_err(err)? {
            r.process.cleanup();
            let status = store.get(&r.id)?.status;
            store.finish(
                &r.id,
                if status == "stopping" {
                    "stopped"
                } else if exit.success() {
                    "succeeded"
                } else {
                    "failed"
                },
                exit.code(),
            )?;
            if r.delete {
                store.delete(&r.id)?;
            }
            *running = None;
            *schedule = true;
            changed = true;
        }
    }
    if running.is_none() && *schedule {
        *schedule = false;
        if !store.paused()? {
            let all = store.list()?;
            if all.iter().any(|e| e.status == "orphaned") {
                return Ok(changed);
            }
            if let Some(e) = all.into_iter().find(|e| e.status == "queued") {
                match Process::start(&e) {
                    Ok(process) => {
                        store.running(&e.id, process.child.id())?;
                        *running = Some(Running {
                            id: e.id,
                            process,
                            deadline: None,
                            delete: false,
                        });
                    }
                    Err(error) => {
                        store.finish(&e.id, "failed", Some(-1))?;
                        let mut f = std::fs::OpenOptions::new()
                            .create(true)
                            .append(true)
                            .open(e.stderr_path)
                            .map_err(err)?;
                        writeln!(f, "PipeDL: {error}").map_err(err)?;
                        *schedule = true;
                    }
                }
                changed = true;
            }
        }
    }
    Ok(changed)
}
