use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

pub type Result<T> = std::result::Result<T, String>;
pub fn err(e: impl std::fmt::Display) -> String {
    e.to_string()
}

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Experiment {
    pub id: String,
    pub name: String,
    pub command: String,
    pub shell: String,
    pub cwd: String,
    pub status: String,
    pub queue_position: i64,
    pub pid: Option<u32>,
    pub process_group: Option<i64>,
    pub exit_code: Option<i32>,
    pub created_by: String,
    pub tags: String,
    pub notes: String,
    pub stdout_path: String,
    pub stderr_path: String,
    pub created_at: String,
    pub started_at: Option<String>,
    pub ended_at: Option<String>,
    pub updated_at: String,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Create {
    #[serde(default)]
    pub name: String,
    pub command: String,
    #[serde(default = "default_shell")]
    pub shell: String,
    pub cwd: String,
    #[serde(default = "api_source")]
    pub created_by: String,
    #[serde(default)]
    pub tags: String,
    #[serde(default)]
    pub notes: String,
}
pub fn default_shell() -> String {
    if cfg!(windows) { "powershell" } else { "bash" }.into()
}
fn api_source() -> String {
    "api".into()
}
pub fn terminal(s: &str) -> bool {
    matches!(s, "succeeded" | "failed" | "stopped" | "cancelled")
}

pub struct Store {
    pub conn: Connection,
    pub runs: PathBuf,
}
impl Store {
    pub fn open(root: &Path) -> Result<Self> {
        let state = root.join(".pipedl");
        std::fs::create_dir_all(&state).map_err(err)?;
        let runs = root.join("runs");
        std::fs::create_dir_all(&runs).map_err(err)?;
        let path = state.join("pipedl.db");
        let existed = path.exists();
        let conn = Connection::open(&path).map_err(err)?;
        conn.busy_timeout(std::time::Duration::from_secs(3))
            .map_err(err)?;
        let version: i64 = conn
            .query_row("PRAGMA user_version", [], |r| r.get(0))
            .map_err(err)?;
        if version > 1 {
            return Err("Database is newer than this application; refusing to downgrade".into());
        }
        if existed && version == 0 {
            // VACUUM INTO includes committed WAL contents; never overwrite the rollback copy.
            let backup = state.join("pipedl-pre-v3.db");
            if !backup.exists() {
                conn.execute("VACUUM INTO ?1", [backup.to_string_lossy().as_ref()])
                    .map_err(err)?;
            }
        }
        conn.execute_batch(
            "PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;
          CREATE TABLE IF NOT EXISTS experiments (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, command TEXT NOT NULL, shell TEXT NOT NULL,
            cwd TEXT NOT NULL, status TEXT NOT NULL, queue_position INTEGER NOT NULL,
            pid INTEGER, process_group INTEGER, exit_code INTEGER, created_by TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', stdout_path TEXT,
            stderr_path TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, started_at TEXT,
            ended_at TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
          CREATE TABLE IF NOT EXISTS queue_state (id INTEGER PRIMARY KEY CHECK(id=1),
            paused INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
          INSERT OR IGNORE INTO queue_state(id,paused) VALUES(1,0);
          CREATE INDEX IF NOT EXISTS experiments_queue ON experiments(status,queue_position);
          PRAGMA user_version=1;",
        )
        .map_err(err)?;
        // Never signal a PID inherited from another application lifetime (PID reuse).
        let recovered = conn
            .execute(
                "UPDATE experiments SET status='orphaned', updated_at=CURRENT_TIMESTAMP
            WHERE status IN ('running','paused','stopping')",
                [],
            )
            .map_err(err)?;
        if recovered > 0 {
            conn.execute("UPDATE queue_state SET paused=1 WHERE id=1", [])
                .map_err(err)?;
        }
        Ok(Self { conn, runs })
    }
    pub fn list(&self) -> Result<Vec<Experiment>> {
        self.query(None)
    }
    fn query(&self, id: Option<&str>) -> Result<Vec<Experiment>> {
        let predicate = if id.is_some() { "id=?1" } else { "?1 IS NULL" };
        let sql = format!("SELECT id,name,command,shell,cwd,status,queue_position,pid,process_group,
          exit_code,created_by,tags,notes,COALESCE(stdout_path,''),COALESCE(stderr_path,''),created_at,
          started_at,ended_at,updated_at FROM experiments WHERE {predicate} ORDER BY
          CASE status WHEN 'running' THEN 0 WHEN 'paused' THEN 0 WHEN 'stopping' THEN 0 WHEN 'orphaned' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END,
          CASE WHEN status='queued' THEN queue_position ELSE 0 END, created_at DESC, rowid DESC");
        let mut q = self.conn.prepare(&sql).map_err(err)?;
        let rows = q
            .query_map([id], |r| {
                Ok(Experiment {
                    id: r.get(0)?,
                    name: r.get(1)?,
                    command: r.get(2)?,
                    shell: r.get(3)?,
                    cwd: r.get(4)?,
                    status: r.get(5)?,
                    queue_position: r.get(6)?,
                    pid: r.get(7)?,
                    process_group: r.get(8)?,
                    exit_code: r.get(9)?,
                    created_by: r.get(10)?,
                    tags: r.get(11)?,
                    notes: r.get(12)?,
                    stdout_path: r.get(13)?,
                    stderr_path: r.get(14)?,
                    created_at: r.get(15)?,
                    started_at: r.get(16)?,
                    ended_at: r.get(17)?,
                    updated_at: r.get(18)?,
                })
            })
            .map_err(err)?;
        rows.collect::<std::result::Result<Vec<_>, _>>()
            .map_err(err)
    }
    pub fn get(&self, id: &str) -> Result<Experiment> {
        self.query(Some(id))?
            .into_iter()
            .next()
            .ok_or_else(|| "not found".into())
    }
    pub fn paused(&self) -> Result<bool> {
        self.conn
            .query_row("SELECT paused FROM queue_state WHERE id=1", [], |r| {
                r.get(0)
            })
            .map_err(err)
    }
    pub fn pause(&self, paused: bool) -> Result<()> {
        self.conn
            .execute(
                "UPDATE queue_state SET paused=?1,updated_at=CURRENT_TIMESTAMP WHERE id=1",
                [paused],
            )
            .map_err(err)?;
        Ok(())
    }
    pub fn add(&mut self, mut data: Create) -> Result<Experiment> {
        if data.command.trim().is_empty()
            || data.command.len() > 65536
            || data.command.contains('\0')
        {
            return Err("command must contain 1–65536 bytes without NUL".into());
        }
        if data.name.len() > 256
            || data.notes.len() > 16384
            || data.tags.len() > 4096
            || data.created_by.len() > 256
        {
            return Err("metadata too long".into());
        }
        if !matches!(data.shell.as_str(), "bash" | "wsl" | "powershell" | "cmd") {
            return Err("unsupported shell".into());
        }
        if !cfg!(windows) && data.shell != "bash" {
            return Err("this host supports bash; Windows runners require the Windows app".into());
        }
        if data.cwd.contains('\0') || data.cwd.is_empty() {
            return Err("cwd is required".into());
        }
        if data.shell == "wsl" {
            if !data.cwd.starts_with('/') {
                return Err("WSL cwd must be an absolute Linux path".into());
            }
        } else if !Path::new(&data.cwd).is_absolute() || !Path::new(&data.cwd).is_dir() {
            return Err("cwd must be an existing absolute directory on the execution host".into());
        }
        if data.name.trim().is_empty() {
            let n = self
                .list()?
                .iter()
                .filter_map(|e| e.name.strip_prefix("Exp.")?.parse::<u64>().ok())
                .max()
                .unwrap_or(0)
                + 1;
            data.name = format!("Exp.{n:02}");
        }
        let id = uuid::Uuid::new_v4().simple().to_string();
        let dir = self.runs.join(&id);
        std::fs::create_dir(&dir).map_err(err)?;
        let result = self.conn.execute("INSERT INTO experiments (id,name,command,shell,cwd,status,queue_position,created_by,tags,notes,stdout_path,stderr_path)
          VALUES(?1,?2,?3,?4,?5,'queued',(SELECT COALESCE(MAX(queue_position),0)+1 FROM experiments WHERE status='queued'),?6,?7,?8,?9,?10)",
          params![id,data.name.trim(),data.command,data.shell,data.cwd,data.created_by,data.tags,data.notes,
          dir.join("stdout.log").to_string_lossy(),dir.join("stderr.log").to_string_lossy()]);
        if let Err(e) = result {
            let _ = std::fs::remove_dir(&dir);
            return Err(err(e));
        }
        self.get(&id)
    }
    pub fn status(&self, id: &str, status: &str) -> Result<()> {
        self.conn
            .execute(
                "UPDATE experiments SET status=?2,updated_at=CURRENT_TIMESTAMP WHERE id=?1",
                params![id, status],
            )
            .map_err(err)?;
        Ok(())
    }
    pub fn running(&self, id: &str, pid: u32) -> Result<()> {
        self.conn.execute("UPDATE experiments SET status='running',pid=?2,process_group=?2,started_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?1", params![id,pid]).map_err(err)?;
        self.compact()
    }
    pub fn finish(&self, id: &str, status: &str, code: Option<i32>) -> Result<()> {
        self.conn.execute("UPDATE experiments SET status=?2,exit_code=?3,ended_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?1", params![id,status,code]).map_err(err)?;
        self.compact()
    }
    pub fn delete(&self, id: &str) -> Result<()> {
        let exp = self.get(id)?;
        // Delete only this application's own run directory, never an arbitrary legacy path.
        if let Some(dir) = Path::new(&exp.stdout_path).parent() {
            if let (Ok(dir), Ok(root)) = (dir.canonicalize(), self.runs.canonicalize()) {
                if dir.parent() == Some(root.as_path())
                    && dir.file_name().and_then(|v| v.to_str()) == Some(id)
                {
                    std::fs::remove_dir_all(dir).map_err(err)?;
                }
            }
        }
        self.conn
            .execute("DELETE FROM experiments WHERE id=?1", [id])
            .map_err(err)?;
        self.compact()
    }
    fn compact(&self) -> Result<()> {
        self.conn.execute("WITH positions AS (SELECT id,ROW_NUMBER() OVER (ORDER BY queue_position,created_at,id) AS pos FROM experiments WHERE status='queued') UPDATE experiments SET queue_position=(SELECT pos FROM positions WHERE positions.id=experiments.id) WHERE status='queued'", []).map_err(err)?;
        Ok(())
    }
    pub fn reorder(&mut self, id: &str, position: usize) -> Result<()> {
        if self.get(id)?.status != "queued" {
            return Err("only queued tasks can be reordered".into());
        }
        let mut ids: Vec<_> = self
            .list()?
            .into_iter()
            .filter(|e| e.status == "queued" && e.id != id)
            .map(|e| e.id)
            .collect();
        if position == 0 || position > ids.len() + 1 {
            return Err("position outside queue".into());
        }
        ids.insert(position - 1, id.into());
        let tx = self.conn.transaction().map_err(err)?;
        for (i, id) in ids.iter().enumerate() {
            tx.execute(
                "UPDATE experiments SET queue_position=?2,updated_at=CURRENT_TIMESTAMP WHERE id=?1",
                params![id, i + 1],
            )
            .map_err(err)?;
        }
        tx.commit().map_err(err)
    }
}
