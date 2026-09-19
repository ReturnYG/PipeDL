import React, { memo, useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Code2,
  Copy,
  Folder,
  GripVertical,
  History,
  Layers3,
  LoaderCircle,
  Pause,
  Play,
  Plus,
  Power,
  RefreshCw,
  Search,
  Settings2,
  Square,
  Terminal,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import {
  request,
  subscribe,
  type Connection,
  type Experiment,
  type Info,
  type Snapshot,
} from "./api";
import "./style.css";

const isDesktop = "__TAURI_INTERNALS__" in window;
const finished = (s: string) =>
  ["succeeded", "failed", "stopped", "cancelled"].includes(s);
const labels: Record<string, string> = {
  running: "运行中",
  paused: "已暂停",
  queued: "等待中",
  stopping: "正在停止",
  succeeded: "已完成",
  failed: "失败",
  stopped: "已停止",
  cancelled: "已取消",
  orphaned: "需要处理",
};
const empty: Snapshot = {
  experiments: [],
  summary: { paused: false },
  total: 0,
};
const date = (s: string | null) =>
  s
    ? new Date(s.replace(" ", "T") + "Z").toLocaleString("zh-CN", {
        hour12: false,
      })
    : "—";
function Status({ status }: { status: string }) {
  return (
    <span className={`status ${status}`}>
      <i />
      {labels[status] || status}
    </span>
  );
}
function IconButton({
  label,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button className="icon-button" title={label} aria-label={label} {...props}>
      {children}
    </button>
  );
}
function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: React.ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={close}
      onClick={(e) => {
        if (e.target === ref.current) close();
      }}
    >
      <div className="modal-head">
        <h2>{title}</h2>
        <IconButton label="关闭" onClick={close}>
          <X size={20} />
        </IconButton>
      </div>
      {children}
    </dialog>
  );
}
function App() {
  const [connection, setConnection] = useState<Connection | null>(null),
    [info, setInfo] = useState<Info | null>(null),
    [error, setError] = useState(""),
    [connected, setConnected] = useState(false);
  const [snapshot, setSnapshot] = useState(empty),
    [tab, setTab] = useState("active"),
    [offset, setOffset] = useState(0),
    [search, setSearch] = useState(""),
    [selected, setSelected] = useState<string | null>(null),
    [detail, setDetail] = useState<Experiment | null>(null);
  const [modal, setModal] = useState<"create" | "settings" | null>(null),
    [busy, setBusy] = useState<string | null>(null),
    [confirm, setConfirm] = useState<Experiment | null>(null),
    [confirmCompleted, setConfirmCompleted] = useState(false),
    [revision, setRevision] = useState(0),
    [notice, setNotice] = useState("");
  const [loginUrl, setLoginUrl] = useState("http://127.0.0.1:48127"),
    [loginToken, setLoginToken] = useState("");
  const refresh = useCallback(() => setRevision((v) => v + 1), []);
  useEffect(() => {
    if (isDesktop) {
      import("@tauri-apps/api/core")
        .then((m) => m.invoke<Connection>("bootstrap"))
        .then(setConnection)
        .catch((e) => setError(String(e)));
      const listening = import("@tauri-apps/api/event").then((m) =>
        m.listen<string>("quit-error", (e) => setError(e.payload)),
      );
      return () => {
        listening.then((off) => off());
      };
    }
  }, []);
  useEffect(() => {
    if (!connection) return;
    const controller = new AbortController();
    request<Info>(connection, "/info", undefined, controller.signal)
      .then(setInfo)
      .catch((e) => {
        if (!controller.signal.aborted) setError(String(e));
      });
    subscribe(connection, controller.signal, refresh, setConnected);
    return () => controller.abort();
  }, [connection, refresh]);
  useEffect(() => {
    if (!connection) return;
    const controller = new AbortController();
    request<Snapshot>(
      connection,
      `/experiments?status=${tab}&offset=${offset}&limit=50`,
      undefined,
      controller.signal,
    )
      .then((data) => {
        setSnapshot(data);
        if (offset >= data.total && offset > 0)
          setOffset(Math.max(0, Math.floor((data.total - 1) / 50) * 50));
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(String(e));
      });
    return () => controller.abort();
  }, [connection, tab, offset, revision]);
  useEffect(() => {
    if (!connection || !selected) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    request<Experiment>(
      connection,
      `/experiments/${selected}`,
      undefined,
      controller.signal,
    )
      .then(setDetail)
      .catch((e) => {
        if (!controller.signal.aborted) {
          setDetail(null);
          if (!String(e).includes("not found")) setError(String(e));
        }
      });
    return () => controller.abort();
  }, [connection, selected, revision]);
  useEffect(() => {
    if (!notice) return;
    const id = setTimeout(() => setNotice(""), 3500);
    return () => clearTimeout(id);
  }, [notice]);
  async function act(path: string, body: unknown = {}, selectResult = false) {
    if (!connection) return;
    setBusy(path);
    setError("");
    try {
      const result = await request<Experiment>(connection, path, body);
      if (selectResult) setSelected(result.id);
      refresh();
      return true;
    } catch (e) {
      setError(String(e));
      return false;
    } finally {
      setBusy(null);
    }
  }
  const action = useCallback(
    (id: string, name: string, position?: number) => {
      void act(
        `/experiments/${id}/${name}`,
        position ? { position } : {},
        name === "retry",
      );
    },
    [connection],
  );
  const summary = snapshot.summary;
  const active =
    Number(summary.running || 0) +
    Number(summary.paused_processes || 0) +
    Number(summary.stopping || 0);
  async function login(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const c = { url: loginUrl.replace(/\/$/, ""), token: loginToken.trim() };
    if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(c.url)) {
      setError("请输入本机 127.0.0.1 地址");
      return;
    }
    try {
      await request(c, "/info");
      setConnection(c);
    } catch (e) {
      setError(String(e));
    }
  }
  if (!connection)
    return (
      <div className="login">
        <div className="brand large">
          <Layers3 /> PipeDL<span>WORKSPACE</span>
        </div>
        <form onSubmit={login}>
          <h1>连接实验工作台</h1>
          <p>桌面应用会自动连接。浏览器预览请使用本地 API 凭据。</p>
          <label>
            API 地址
            <input
              value={loginUrl}
              onChange={(e) => setLoginUrl(e.target.value)}
              required
            />
          </label>
          <label>
            API Token
            <input
              type="password"
              value={loginToken}
              onChange={(e) => setLoginToken(e.target.value)}
              required
              autoComplete="off"
            />
          </label>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button className="primary" type="submit">
            连接工作台 <ArrowUpRight size={16} />
          </button>
        </form>
      </div>
    );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Layers3 size={26} />
          PipeDL<span>LOCAL</span>
        </div>
        <div className="workspace-label">WORKSPACE</div>
        <nav>
          <button
            className={tab === "active" ? "nav active" : "nav"}
            onClick={() => {
              setTab("active");
              setOffset(0);
            }}
          >
            <Layers3 size={18} />
            实验队列
            <span>
              {Number(summary.queued || 0) +
                active +
                Number(summary.orphaned || 0)}
            </span>
          </button>
          <button
            className={tab === "history" ? "nav active" : "nav"}
            onClick={() => {
              setTab("history");
              setOffset(0);
            }}
          >
            <History size={18} />
            运行历史
          </button>
        </nav>
        <div className="sidebar-note">
          <div className="pulse-dot" />
          本地运行，专注实验
          <p>
            管理每一次运行，
            <br />
            让下一个想法有序开始。
          </p>
          <div className="rail-graphic">
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
        </div>
        <div className="sidebar-bottom">
          <button className="nav" onClick={() => setModal("settings")}>
            <Settings2 size={18} />
            工作台设置
          </button>
          <div className="connection">
            <i className={connected ? "online" : ""} />
            {connected ? "API 已连接" : "正在重新连接…"}
            <span>v{info?.version || "0.3"}</span>
          </div>
        </div>
      </aside>
      <main>
        <header>
          <div className="breadcrumb">
            工作台 <span>/</span> {tab === "active" ? "实验队列" : "运行历史"}
          </div>
          <div className="header-right">
            <span>
              <span className="tiny-dot" /> LOCAL ENGINE
            </span>
            <IconButton label="刷新" onClick={refresh}>
              <RefreshCw size={17} />
            </IconButton>
          </div>
        </header>
        <section className="page-heading">
          <div className="eyebrow">YOUR EXPERIMENTS, IN ORDER.</div>
          <div className="heading-row">
            <div>
              <h1>
                {tab === "active" ? "实验队列" : "运行历史"}
                <span className="heading-dot">.</span>
              </h1>
              <p>
                {tab === "active"
                  ? "从一个命令，到下一个结果。让实验有序运行。"
                  : "每次运行都有迹可循，继续探索新的可能。"}
              </p>
            </div>
            <button className="primary" onClick={() => setModal("create")}>
              <Plus size={18} />
              新建实验
            </button>
          </div>
        </section>
        <section className="stats" aria-label="队列统计">
          <Stat
            label="正在执行"
            value={active}
            icon={<Activity />}
            foot={active ? "实验正在进行" : "等待新的实验"}
            tone="green"
          />
          <Stat
            label="等待运行"
            value={Number(summary.queued || 0)}
            icon={<Layers3 />}
            foot={summary.paused ? "队列已暂停" : "按顺序自动执行"}
            tone="amber"
          />
          <Stat
            label="已完成"
            value={Number(summary.succeeded || 0)}
            icon={<CheckCircle2 />}
            foot="每一步都算数"
            tone="success"
          />
          <Stat
            label="失败或中断"
            value={Number(summary.failed || 0) + Number(summary.orphaned || 0)}
            icon={<XCircle />}
            foot="查看日志，继续尝试"
            tone="red"
          />
        </section>
        {error && (
          <div className="banner error" role="alert">
            <XCircle size={18} />
            <span>{error}</span>
            <IconButton label="关闭错误" onClick={() => setError("")}>
              <X size={16} />
            </IconButton>
          </div>
        )}
        {!connected && (
          <div className="banner warning" role="status">
            连接中断，正在重连。已显示的数据可能不是最新状态。
          </div>
        )}
        {!!summary.orphaned && (
          <div className="banner warning">
            检测到上次中断的任务。为避免重复训练，队列已暂停；请在详情中确认旧进程已结束，再恢复队列。
          </div>
        )}
        <section className="workspace">
          <div className="queue-panel">
            <div className="panel-toolbar">
              <div className="panel-title">
                {tab === "active" ? "运行列表" : "历史记录"}
                <span>{snapshot.total}</span>
              </div>
              {tab === "history" && (
                <button
                  className="danger-button small"
                  disabled={!!busy || !summary.succeeded}
                  onClick={() => {
                    setError("");
                    setConfirmCompleted(true);
                  }}
                >
                  <Trash2 size={14} /> 删除所有已完成
                </button>
              )}
              <button
                className="secondary small"
                disabled={!!busy}
                onClick={() =>
                  void act(`/queue/${summary.paused ? "resume" : "pause"}`)
                }
              >
                {summary.paused ? <Play size={14} /> : <Pause size={14} />}{" "}
                {summary.paused ? "恢复队列" : "暂停队列"}
              </button>
            </div>
            <div className="list-tools">
              <label className="search">
                <Search size={16} />
                <input
                  aria-label="搜索本页实验"
                  placeholder="搜索本页实验…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </label>
              <span className="serial">
                <i /> 串行执行
              </span>
            </div>
            <div className="experiment-list">
              {snapshot.experiments
                .filter((e) =>
                  (e.name + " " + e.command + " " + e.tags)
                    .toLowerCase()
                    .includes(search.toLowerCase()),
                )
                .map((e) => (
                  <Card
                    key={e.id}
                    exp={e}
                    selected={selected === e.id}
                    select={setSelected}
                    action={action}
                    disabled={!!busy}
                    remove={setConfirm}
                  />
                ))}
              {snapshot.experiments.length === 0 && (
                <div className="empty-state">
                  <div className="empty-icon">
                    <Terminal size={28} />
                  </div>
                  <h3>
                    {tab === "active"
                      ? "准备好下一次实验了吗？"
                      : "还没有运行记录"}
                  </h3>
                  <p>
                    {tab === "active"
                      ? "添加命令，或通过 API 提交实验。"
                      : "完成的实验会出现在这里。"}
                  </p>
                  {tab === "active" && (
                    <button
                      className="secondary"
                      onClick={() => setModal("create")}
                    >
                      <Plus size={15} />
                      创建第一个实验
                    </button>
                  )}
                </div>
              )}
            </div>
            <div className="list-footer">
              <span>
                {snapshot.total
                  ? `${offset + 1}–${Math.min(offset + 50, snapshot.total)} / ${snapshot.total}`
                  : "0 个实验"}
              </span>
              <div>
                <IconButton
                  label="上一页"
                  disabled={offset === 0}
                  onClick={() => setOffset((v) => Math.max(0, v - 50))}
                >
                  <ChevronLeft size={16} />
                </IconButton>
                <IconButton
                  label="下一页"
                  disabled={offset + 50 >= snapshot.total}
                  onClick={() => setOffset((v) => v + 50)}
                >
                  <ChevronRight size={16} />
                </IconButton>
              </div>
            </div>
          </div>
          <div className="inspector">
            {detail ? (
              <>
                <div className="detail-heading">
                  <div className="eyebrow">EXPERIMENT DETAILS</div>
                  <Status status={detail.status} />
                  <h2>{detail.name}</h2>
                  <div className="id-line">
                    {detail.id.slice(0, 12)}
                    <IconButton
                      label="复制任务 ID"
                      onClick={() => {
                        navigator.clipboard
                          .writeText(detail.id)
                          .then(() => setNotice("已复制任务 ID"))
                          .catch((e) => setError(String(e)));
                      }}
                    >
                      <Copy size={13} />
                    </IconButton>
                  </div>
                </div>
                <div className="detail-fields">
                  <div>
                    <span>执行环境</span>
                    <strong>{detail.shell}</strong>
                  </div>
                  <div>
                    <span>进程 PID</span>
                    <strong>{detail.pid || "—"}</strong>
                  </div>
                  <div>
                    <span>退出码</span>
                    <strong>{detail.exit_code ?? "—"}</strong>
                  </div>
                  <div>
                    <span>提交来源</span>
                    <strong>{detail.created_by}</strong>
                  </div>
                </div>
                <div className="path">
                  <Folder size={14} />
                  <span>{detail.cwd}</span>
                </div>
                <div className="command">
                  <span>COMMAND</span>
                  <pre>{detail.command}</pre>
                </div>
                {detail.tags && (
                  <div className="tags">
                    {detail.tags.split(",").map((t, i) => (
                      <span key={i}>{t.trim()}</span>
                    ))}
                  </div>
                )}
                {detail.notes && <p className="notes">{detail.notes}</p>}
                <details className="timestamps">
                  <summary>
                    时间与日志位置 <ChevronDown size={14} />
                  </summary>
                  <p>
                    创建：{date(detail.created_at)}
                    <br />
                    开始：{date(detail.started_at)}
                    <br />
                    结束：{date(detail.ended_at)}
                  </p>
                  <p>
                    {detail.stdout_path}
                    <br />
                    {detail.stderr_path}
                  </p>
                </details>
                {detail.status === "orphaned" && (
                  <button
                    className="secondary resolve"
                    disabled={!!busy}
                    onClick={() => action(detail.id, "resolve")}
                  >
                    确认旧进程已结束
                  </button>
                )}
                <Logs connection={connection} exp={detail} />
              </>
            ) : (
              <div className="detail-empty">
                <Code2 size={32} />
                <h3>运行细节，一目了然</h3>
                <p>
                  选择左侧实验，查看命令、
                  <br />
                  状态与实时日志。
                </p>
                <span>STDOUT / STDERR</span>
              </div>
            )}
          </div>
        </section>
        <footer>
          PipeDL <span>让计算有序，让探索自由。</span>
          <span className="footer-right">所有实验数据保存在本机</span>
        </footer>
      </main>
      {modal === "create" && (
        <CreateModal
          error={error}
          info={info}
          close={() => setModal(null)}
          submit={async (data) => {
            if (await act("/experiments", data, true)) {
              setModal(null);
              setTab("active");
              setOffset(0);
            }
          }}
          busy={!!busy}
        />
      )}
      {modal === "settings" && (
        <Modal title="工作台设置" close={() => setModal(null)}>
          <div className="settings">
            <p className="muted">关闭窗口后，队列会继续在托盘中运行。</p>
            <label>
              本地 API
              <input readOnly value={connection.url} />
            </label>
            <label>
              数据目录
              <input readOnly value={info?.root || ""} />
            </label>
            <label>
              API 凭据
              <div className="token-row">
                <input type="password" readOnly value={connection.token} />
                <button
                  className="secondary"
                  onClick={() =>
                    navigator.clipboard
                      .writeText(connection.token)
                      .then(() => setNotice("已复制 API Token"))
                      .catch((e) => setError(String(e)))
                  }
                >
                  复制
                </button>
              </div>
            </label>
            <p className="muted">
              脚本通过 Authorization: Bearer &lt;token&gt;
              调用。凭据保存在数据目录的 .pipedl/api-token。
            </p>
            <div className="settings-actions">
              <button
                className="secondary"
                onClick={() => {
                  if (isDesktop)
                    import("@tauri-apps/api/core")
                      .then((m) => m.invoke("open_releases"))
                      .catch((e) => setError(String(e)));
                  else
                    window.open(
                      "https://github.com/ReturnYG/PipeDL/releases",
                      "_blank",
                      "noopener",
                    );
                }}
              >
                下载更新 <ArrowUpRight size={15} />
              </button>
              {isDesktop && (
                <button
                  className="danger-button"
                  onClick={() =>
                    import("@tauri-apps/api/core")
                      .then((m) => m.invoke("quit"))
                      .catch((e) => {
                        setModal(null);
                        setError(String(e));
                      })
                  }
                >
                  <Power size={15} />
                  退出应用
                </button>
              )}
            </div>
          </div>
        </Modal>
      )}
      {confirmCompleted && (
        <Modal
          title="删除所有已完成实验？"
          close={() => {
            if (!busy) setConfirmCompleted(false);
          }}
        >
          <div className="confirm-body">
            {error && (
              <p className="banner error" role="alert">
                {error}
              </p>
            )}
            <p>
              当前有 <strong>{Number(summary.succeeded || 0)}</strong>{" "}
              个成功完成的实验。确认后，将删除所有成功完成的实验记录及其日志，包括其他分页中的记录，此操作无法撤销。
            </p>
            <p>失败、已停止、已取消和仍在队列中的实验会保留。</p>
            <div className="modal-actions">
              <button
                className="secondary"
                disabled={!!busy}
                onClick={() => setConfirmCompleted(false)}
              >
                保留实验
              </button>
              <button
                className="danger-button"
                disabled={!!busy || !summary.succeeded}
                onClick={async () => {
                  if (!connection) return;
                  setBusy("delete-completed");
                  setError("");
                  try {
                    const result = await request<{
                      deleted: number;
                      failures: { id: string; error: string }[];
                    }>(connection, "/experiments/delete-completed", {
                      confirm: true,
                    });
                    setSelected(null);
                    setOffset(0);
                    refresh();
                    setNotice(`已删除 ${result.deleted} 个已完成实验`);
                    if (result.failures.length)
                      setError(
                        `${result.failures.length} 个实验删除失败：${result.failures[0].error}`,
                      );
                    else setConfirmCompleted(false);
                  } catch (e) {
                    setError(String(e));
                  } finally {
                    setBusy(null);
                  }
                }}
              >
                {busy === "delete-completed"
                  ? "正在删除…"
                  : "确认删除所有已完成"}
              </button>
            </div>
          </div>
        </Modal>
      )}
      {confirm && (
        <Modal title="删除实验？" close={() => setConfirm(null)}>
          <div className="confirm-body">
            {error && (
              <p className="banner error" role="alert">
                {error}
              </p>
            )}
            <p>
              将删除「{confirm.name}
              」及其日志。运行中的任务会先停止，此操作无法撤销。
            </p>
            <div className="modal-actions">
              <button className="secondary" onClick={() => setConfirm(null)}>
                保留实验
              </button>
              <button
                className="danger-button"
                disabled={!!busy}
                onClick={async () => {
                  if (await act(`/experiments/${confirm.id}/delete`)) {
                    if (selected === confirm.id) setSelected(null);
                    setConfirm(null);
                  }
                }}
              >
                删除实验
              </button>
            </div>
          </div>
        </Modal>
      )}
      {notice && (
        <div className="toast" role="status">
          <Check size={16} />
          {notice}
        </div>
      )}
    </div>
  );
}
function Stat({
  label,
  value,
  icon,
  foot,
  tone,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  foot: string;
  tone: string;
}) {
  return (
    <div className={`stat ${tone}`}>
      <div className="stat-label">
        {label}
        <span>{icon}</span>
      </div>
      <strong>{String(value).padStart(2, "0")}</strong>
      <p>{foot}</p>
    </div>
  );
}
const Card = memo(function Card({
  exp: e,
  selected,
  select,
  action,
  disabled,
  remove,
}: {
  exp: Experiment;
  selected: boolean;
  select: (id: string) => void;
  action: (id: string, a: string, p?: number) => void;
  disabled: boolean;
  remove: (e: Experiment) => void;
}) {
  return (
    <article
      className={`experiment-card state-${e.status} ${selected ? "selected" : ""} ${e.status === "running" ? "is-running" : ""}`}
      draggable={e.status === "queued" && !disabled}
      onDragStart={(event) => {
        event.dataTransfer.setData("text/plain", e.id);
        event.dataTransfer.effectAllowed = "move";
      }}
      onDragOver={(event) => {
        if (e.status === "queued") event.preventDefault();
      }}
      onDrop={(event) => {
        event.preventDefault();
        const id = event.dataTransfer.getData("text/plain");
        if (
          e.status === "queued" &&
          id !== e.id &&
          /^[a-f0-9]{12,32}$/.test(id)
        )
          action(id, "move", e.queue_position);
      }}
    >
      <button
        className="card-select"
        onClick={() => select(e.id)}
        aria-label={`查看 ${e.name}`}
        aria-pressed={selected}
      >
        <div className="card-top">
          <span className={`task-icon ${e.status}`}>
            {e.status === "running" ? (
              <Activity size={18} />
            ) : e.status === "succeeded" ? (
              <CheckCircle2 size={18} />
            ) : e.status === "failed" ? (
              <XCircle size={18} />
            ) : e.status === "stopped" || e.status === "cancelled" ? (
              <Square size={18} />
            ) : (
              <Terminal size={18} />
            )}
          </span>
          <h3>{e.name}</h3>
          <Status status={e.status} />
        </div>
        <div className="card-command">{e.command}</div>
        <div className="card-meta">
          <span>{e.shell}</span>
          <span>
            <Folder size={12} />
            {e.cwd}
          </span>
        </div>
      </button>
      <div className="card-bottom">
        <span className="queue-order">
          {e.status === "queued" ? (
            <>
              <GripVertical size={14} /> 队列 #{e.queue_position}
            </>
          ) : (
            <>
              <span className="tiny-dot" />
              {e.created_by}
            </>
          )}
        </span>
        <div className="card-actions">
          {e.status === "queued" && (
            <>
              <IconButton
                label={`上移 ${e.name}`}
                disabled={disabled || e.queue_position <= 1}
                onClick={() => action(e.id, "move", e.queue_position - 1)}
              >
                <ArrowUp size={14} />
              </IconButton>
              <IconButton
                label={`下移 ${e.name}`}
                disabled={disabled}
                onClick={() => action(e.id, "move", e.queue_position + 1)}
              >
                <ArrowDown size={14} />
              </IconButton>
              <IconButton
                label={`取消 ${e.name}`}
                disabled={disabled}
                onClick={() => action(e.id, "cancel")}
              >
                <X size={14} />
              </IconButton>
            </>
          )}
          {e.status === "running" && (
            <IconButton
              label={`暂停 ${e.name}`}
              disabled={disabled}
              onClick={() => action(e.id, "pause")}
            >
              <Pause size={14} />
            </IconButton>
          )}
          {e.status === "paused" && (
            <IconButton
              label={`继续 ${e.name}`}
              disabled={disabled}
              onClick={() => action(e.id, "resume")}
            >
              <Play size={14} />
            </IconButton>
          )}
          {["running", "paused"].includes(e.status) && (
            <IconButton
              label={`停止 ${e.name}`}
              disabled={disabled}
              onClick={() => action(e.id, "stop")}
            >
              <Square size={13} />
            </IconButton>
          )}
          {finished(e.status) && (
            <IconButton
              label={`重试 ${e.name}`}
              disabled={disabled}
              onClick={() => action(e.id, "retry")}
            >
              <RefreshCw size={14} />
            </IconButton>
          )}
          {!["orphaned", "stopping"].includes(e.status) && (
            <IconButton
              label={`删除 ${e.name}`}
              disabled={disabled}
              onClick={() => remove(e)}
            >
              <Trash2 size={14} />
            </IconButton>
          )}
        </div>
      </div>
    </article>
  );
});
function CreateModal({
  info,
  close,
  submit,
  busy,
  error,
}: {
  error: string;
  info: Info | null;
  close: () => void;
  submit: (data: unknown) => void;
  busy: boolean;
}) {
  return (
    <Modal title="新建实验" close={close}>
      <form
        className="create-form"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          submit(
            Object.fromEntries([...f.entries(), ["created_by", "desktop"]]),
          );
        }}
      >
        <p className="muted">添加到队列后，将在前一个实验结束时自动运行。</p>
        <div className="form-grid">
          <label>
            实验名称 <span>可选</span>
            <input
              name="name"
              placeholder="例如：resnet50_baseline"
              maxLength={256}
            />
          </label>
          <label>
            执行环境
            <select name="shell" defaultValue={info?.default_shell || "bash"}>
              {(info?.shells || ["bash"]).map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
        </div>
        <label>
          工作目录
          <input
            name="cwd"
            required
            placeholder={
              info?.platform === "windows"
                ? "D:\\project 或 /mnt/d/project（WSL）"
                : "/home/user/project"
            }
            autoComplete="off"
          />
        </label>
        <label>
          运行命令
          <textarea
            name="command"
            required
            rows={4}
            maxLength={65536}
            placeholder="python -u train.py --config configs/baseline.yaml"
            spellCheck={false}
          />
        </label>
        <div className="form-grid">
          <label>
            标签 <span>逗号分隔</span>
            <input name="tags" placeholder="baseline, gpu0" />
          </label>
          <label>
            备注 <span>可选</span>
            <input name="notes" placeholder="记录这次实验的目的" />
          </label>
        </div>
        {error && (
          <p className="banner error" role="alert">
            {error}
          </p>
        )}
        <div className="form-hint">
          <Terminal size={15} />
          命令在所选 Shell 中执行，输出自动保存到本机。
        </div>
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={close}>
            取消
          </button>
          <button className="primary" disabled={busy} type="submit">
            {busy ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <Plus size={16} />
            )}
            加入队列
          </button>
        </div>
      </form>
    </Modal>
  );
}
function Logs({
  connection,
  exp,
}: {
  connection: Connection;
  exp: Experiment;
}) {
  const [stream, setStream] = useState("stdout"),
    [text, setText] = useState(""),
    [error, setError] = useState(""),
    [tail, setTail] = useState(true),
    [wrap, setWrap] = useState(false);
  const view = useRef<HTMLPreElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    let offset: number | undefined;
    let timer: ReturnType<typeof setTimeout>;
    setText("");
    setError("");
    const load = async () => {
      try {
        if (document.visibilityState === "hidden") {
          timer = setTimeout(load, 1000);
          return;
        }
        const log = await request<{
          text: string;
          offset: number;
          reset: boolean;
          more: boolean;
        }>(
          connection,
          `/experiments/${exp.id}/logs?stream=${stream}${offset === undefined ? "" : `&offset=${offset}`}`,
          undefined,
          controller.signal,
        );
        offset = log.offset;
        setText((old) => ((log.reset ? "" : old) + log.text).slice(-200000));
        setError("");
        if (!controller.signal.aborted && (log.more || !finished(exp.status)))
          timer = setTimeout(load, log.more ? 50 : 500);
      } catch (e) {
        if (!controller.signal.aborted) {
          setError(String(e));
          timer = setTimeout(load, 2000);
        }
      }
    };
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [connection, exp.id, exp.status, stream]);
  useEffect(() => {
    if (tail && view.current)
      view.current.scrollTop = view.current.scrollHeight;
  }, [text, tail]);
  return (
    <section className="logs">
      <div className="log-heading">
        <span>
          <Terminal size={15} /> 实时日志
        </span>
        <div>
          <label>
            <input
              type="checkbox"
              checked={wrap}
              onChange={(e) => setWrap(e.target.checked)}
            />
            换行
          </label>
          <label>
            <input
              type="checkbox"
              checked={tail}
              onChange={(e) => setTail(e.target.checked)}
            />
            跟随
          </label>
        </div>
      </div>
      <div className="log-tabs">
        <button
          className={stream === "stdout" ? "active" : ""}
          onClick={() => setStream("stdout")}
        >
          stdout
        </button>
        <button
          className={stream === "stderr" ? "active" : ""}
          onClick={() => setStream("stderr")}
        >
          stderr
        </button>
        <span>
          {finished(exp.status) ? "已结束" : "LIVE"}
          <i />
        </span>
      </div>
      {error && <div className="log-error">{error}</div>}
      <pre
        ref={view}
        className={wrap ? "wrap" : ""}
        tabIndex={0}
        aria-label={`${stream} 日志`}
        onWheel={(e) => {
          if (e.deltaY < 0) setTail(false);
        }}
        onKeyDown={(e) => {
          if (["ArrowUp", "PageUp", "Home"].includes(e.key)) setTail(false);
        }}
      >
        {text || (
          <span className="log-placeholder">
            $ 等待进程输出…
            <span className="cursor" />
          </span>
        )}
      </pre>
      <div className="log-footer">
        UTF-8 <span>仅保留最近 200,000 字符 · 完整日志已保存</span>
      </div>
    </section>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
