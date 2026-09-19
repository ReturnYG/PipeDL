use crate::store::{err, Experiment, Result};
use std::{
    fs::OpenOptions,
    process::{Child, Command, Stdio},
};

pub struct Process {
    pub child: Child,
    #[cfg(windows)]
    job: windows::Job,
    #[cfg(windows)]
    wsl_id: Option<String>,
}
impl Process {
    pub fn start(exp: &Experiment) -> Result<Self> {
        let mut command = match exp.shell.as_str() {
            "bash" => {
                let mut c = Command::new("bash");
                c.args(["-lc", &exp.command]);
                c
            }
            "powershell" => {
                let mut c = Command::new("powershell.exe");
                let script = format!(
                    "$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); {}",
                    exp.command
                );
                c.args(["-NoProfile", "-NonInteractive", "-Command", &script]);
                c
            }
            "cmd" => {
                let mut c = Command::new("cmd.exe");
                let script = format!("chcp 65001 >nul & {}", exp.command);
                c.args(["/D", "/S", "/C"]);
                #[cfg(windows)]
                {
                    use std::os::windows::process::CommandExt;
                    // The authenticated input is shell source; cmd uses its own quoting rules.
                    c.raw_arg(format!("\"{script}\""));
                }
                #[cfg(not(windows))]
                c.arg(script);
                c
            }
            "wsl" => {
                let mut c = Command::new("wsl.exe");
                let script = format!("export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1; echo $$ > /tmp/pipedl-{}.pid; eval \"$1\"", exp.id);
                c.args([
                    "--cd",
                    &exp.cwd,
                    "--exec",
                    "setsid",
                    "--wait",
                    "bash",
                    "-lc",
                    &script,
                    "pipedl",
                    &exp.command,
                ]);
                c
            }
            _ => return Err("unsupported shell".into()),
        };
        if exp.shell != "wsl" {
            command.current_dir(&exp.cwd);
        }
        command
            .env("PYTHONIOENCODING", "utf-8")
            .env("PYTHONUNBUFFERED", "1")
            .stdin(Stdio::null())
            .stdout(
                OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(&exp.stdout_path)
                    .map_err(err)?,
            )
            .stderr(
                OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(&exp.stderr_path)
                    .map_err(err)?,
            );
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            command.process_group(0);
        }
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000 | 0x00000004); // hidden, suspended until owned by job
        }
        let mut child = command.spawn().map_err(err)?;
        #[cfg(windows)]
        {
            match windows::Job::new(&child) {
                Ok(job) => Ok(Self {
                    child,
                    job,
                    wsl_id: (exp.shell == "wsl").then(|| exp.id.clone()),
                }),
                Err(e) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    Err(e)
                }
            }
        }
        #[cfg(not(windows))]
        {
            let _ = &mut child;
            Ok(Self { child })
        }
    }
    pub fn signal(&self, action: &str) -> Result<()> {
        #[cfg(unix)]
        {
            let sig = match action {
                "pause" => libc::SIGSTOP,
                "resume" => libc::SIGCONT,
                "stop" => libc::SIGTERM,
                _ => libc::SIGKILL,
            };
            // A stopped process must be continued to receive a graceful termination signal.
            if action == "stop" {
                unsafe {
                    libc::kill(-(self.child.id() as i32), libc::SIGCONT);
                }
            }
            if unsafe { libc::kill(-(self.child.id() as i32), sig) } != 0 {
                let e = std::io::Error::last_os_error();
                if e.raw_os_error() != Some(libc::ESRCH) {
                    return Err(err(e));
                }
            }
            Ok(())
        }
        #[cfg(windows)]
        {
            if let Some(id) = &self.wsl_id {
                return wsl_signal(id, action);
            }
            self.job.signal(action)
        }
    }
    pub fn cleanup(&self) {
        let _ = self.signal("kill");
        #[cfg(windows)]
        if let Some(id) = &self.wsl_id {
            let _ = run_wsl(&["rm", "-f", &format!("/tmp/pipedl-{id}.pid")]);
        }
    }
}
impl Drop for Process {
    fn drop(&mut self) {
        self.cleanup();
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

pub fn pid_exists(pid: u32) -> bool {
    #[cfg(unix)]
    {
        unsafe {
            libc::kill(pid as i32, 0) == 0
                || std::io::Error::last_os_error().raw_os_error() == Some(libc::EPERM)
        }
    }
    #[cfg(windows)]
    {
        windows::exists(pid)
    }
}

#[cfg(windows)]
fn run_wsl(args: &[&str]) -> Result<()> {
    use std::{
        os::windows::process::CommandExt,
        time::{Duration, Instant},
    };
    let mut child = Command::new("wsl.exe")
        .arg("--exec")
        .args(args)
        .creation_flags(0x08000000)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(err)?;
    let deadline = Instant::now() + Duration::from_secs(4);
    loop {
        if let Some(status) = child.try_wait().map_err(err)? {
            return if status.success() {
                Ok(())
            } else {
                Err("WSL process control failed; state was not changed".into())
            };
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err("WSL control timed out".into());
        }
        std::thread::sleep(Duration::from_millis(20));
    }
}
#[cfg(windows)]
fn wsl_signal(id: &str, action: &str) -> Result<()> {
    let sig = match action {
        "pause" => "STOP",
        "resume" => "CONT",
        "stop" => "TERM",
        _ => "KILL",
    };
    run_wsl(&["bash","-c","p=$(cat \"$1\") || exit 1; case $p in ''|*[!0-9]*) exit 1;; esac; if [ \"$2\" = TERM ]; then kill -CONT -- -\"$p\"; fi; kill -\"$2\" -- -\"$p\"", "pipedl", &format!("/tmp/pipedl-{id}.pid"),sig])
}

#[cfg(windows)]
mod windows {
    use super::*;
    use std::{
        mem::{size_of, zeroed},
        os::windows::io::AsRawHandle,
    };
    use windows_sys::Win32::{
        Foundation::{CloseHandle, HANDLE},
        System::{JobObjects::*, Threading::*},
    };
    #[link(name = "ntdll")]
    extern "system" {
        fn NtSuspendProcess(process: HANDLE) -> i32;
        fn NtResumeProcess(process: HANDLE) -> i32;
    }
    pub struct Job(HANDLE);
    impl Job {
        pub fn new(child: &Child) -> Result<Self> {
            unsafe {
                let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
                if handle.is_null() {
                    return Err(err(std::io::Error::last_os_error()));
                }
                let job = Self(handle);
                let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = zeroed();
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                if SetInformationJobObject(
                    handle,
                    JobObjectExtendedLimitInformation,
                    &info as *const _ as _,
                    size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                ) == 0
                    || AssignProcessToJobObject(handle, child.as_raw_handle() as HANDLE) == 0
                {
                    return Err(err(std::io::Error::last_os_error()));
                }
                if NtResumeProcess(child.as_raw_handle() as HANDLE) < 0 {
                    return Err("Cannot resume owned process".into());
                }
                Ok(job)
            }
        }
        pub fn signal(&self, action: &str) -> Result<()> {
            unsafe {
                if matches!(action, "stop" | "kill") {
                    if TerminateJobObject(self.0, 1) == 0 {
                        return Err(err(std::io::Error::last_os_error()));
                    }
                    return Ok(());
                }
                // Query all currently owned PIDs. Re-query after suspension catches children born during the first pass.
                let mut suspended = Vec::new();
                let rollback = |pids: &[usize]| {
                    for &pid in pids {
                        let p = OpenProcess(PROCESS_SUSPEND_RESUME, 0, pid as u32);
                        if !p.is_null() {
                            if action == "pause" {
                                NtResumeProcess(p);
                            } else {
                                NtSuspendProcess(p);
                            }
                            CloseHandle(p);
                        }
                    }
                };
                for _ in 0..8 {
                    let mut size = 1024usize;
                    let pids = loop {
                        let mut buffer = vec![0usize; size];
                        if QueryInformationJobObject(
                            self.0,
                            JobObjectBasicProcessIdList,
                            buffer.as_mut_ptr() as _,
                            (buffer.len() * size_of::<usize>()) as u32,
                            std::ptr::null_mut(),
                        ) != 0
                        {
                            let list =
                                &*(buffer.as_ptr() as *const JOBOBJECT_BASIC_PROCESS_ID_LIST);
                            break std::slice::from_raw_parts(
                                list.ProcessIdList.as_ptr(),
                                list.NumberOfProcessIdsInList as usize,
                            )
                            .to_vec();
                        }
                        if std::io::Error::last_os_error().raw_os_error() != Some(234)
                            || size >= 131072
                        {
                            let error = err(std::io::Error::last_os_error());
                            rollback(&suspended);
                            return Err(error);
                        }
                        size *= 2;
                    };
                    let mut changed = false;
                    for pid in pids {
                        if suspended.contains(&pid) {
                            continue;
                        }
                        let p = OpenProcess(PROCESS_SUSPEND_RESUME, 0, pid as u32);
                        if p.is_null() {
                            if !exists(pid as u32) {
                                continue;
                            }
                            rollback(&suspended);
                            return Err("Cannot control an owned Windows process".into());
                        } // A child may have just exited.
                        let result = if action == "pause" {
                            NtSuspendProcess(p)
                        } else {
                            NtResumeProcess(p)
                        };
                        CloseHandle(p);
                        if result < 0 {
                            rollback(&suspended);
                            return Err("Windows process control failed".into());
                        }
                        suspended.push(pid);
                        changed = true;
                    }
                    if action == "resume" || !changed {
                        return Ok(());
                    }
                }
                // Avoid reporting a successful pause if a spawning tree never quiesces.
                rollback(&suspended);
                Err("Process tree is still changing; pause was rolled back".into())
            }
        }
    }
    impl Drop for Job {
        fn drop(&mut self) {
            unsafe {
                CloseHandle(self.0);
            }
        }
    }
    pub fn exists(pid: u32) -> bool {
        unsafe {
            let p = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
            if p.is_null() {
                return std::io::Error::last_os_error().raw_os_error() == Some(5);
            }
            let mut code = 0;
            let ok = GetExitCodeProcess(p, &mut code);
            CloseHandle(p);
            ok != 0 && code == 259
        }
    }
}
