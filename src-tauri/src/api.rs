use crate::{
    engine::{Engine, Op},
    store::{err, Create},
};
use axum::{
    extract::{DefaultBodyLimit, Path, Query, Request, State},
    http::{header, HeaderValue, StatusCode},
    middleware::{self, Next},
    response::{
        sse::{Event, KeepAlive, Sse},
        IntoResponse, Response,
    },
    routing::{get, post},
    Json, Router,
};
use futures_util::StreamExt;
use serde::Deserialize;
use serde_json::{json, Value};
use std::{
    convert::Infallible,
    io::{Read, Seek, SeekFrom},
    sync::Arc,
};
use tokio_stream::wrappers::BroadcastStream;
use tower_http::cors::CorsLayer;

#[derive(Clone)]
pub struct Api {
    pub engine: Engine,
    pub token: String,
    pub root: String,
    pub port: u16,
}
#[derive(Debug)]
struct Error(StatusCode, String);
impl From<String> for Error {
    fn from(e: String) -> Self {
        Self(
            if e == "not found" {
                StatusCode::NOT_FOUND
            } else {
                StatusCode::CONFLICT
            },
            e,
        )
    }
}
impl IntoResponse for Error {
    fn into_response(self) -> Response {
        (self.0, Json(json!({"error":self.1}))).into_response()
    }
}
type Result<T> = std::result::Result<T, Error>;

pub fn router(state: Arc<Api>) -> Router {
    let origins = [
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "http://127.0.0.1:1420",
    ];
    Router::new()
        .route(
            "/health",
            get(|| async { Json(json!({"ok":true,"version":env!("CARGO_PKG_VERSION")})) }),
        )
        .route("/summary", get(summary))
        .route("/info", get(info))
        .route("/experiments", get(list).post(create))
        .route("/experiments/delete-completed", post(delete_completed))
        .route("/experiments/{id}", get(detail))
        .route("/experiments/{id}/logs", get(logs))
        .route("/experiments/{id}/{action}", post(action))
        .route("/queue/{action}", post(queue))
        .route("/events", get(events))
        .layer(DefaultBodyLimit::max(128 * 1024))
        .layer(middleware::from_fn_with_state(state.clone(), auth))
        .layer(
            CorsLayer::new()
                .allow_origin(origins.map(|o| o.parse::<HeaderValue>().unwrap()).to_vec())
                .allow_methods([axum::http::Method::GET, axum::http::Method::POST])
                .allow_headers([header::AUTHORIZATION, header::CONTENT_TYPE]),
        )
        .with_state(state)
}
async fn auth(State(s): State<Arc<Api>>, req: Request, next: Next) -> Response {
    if let Some(origin) = req.headers().get(header::ORIGIN) {
        if ![
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
            "http://127.0.0.1:1420",
        ]
        .iter()
        .any(|o| origin == *o)
        {
            return Error(StatusCode::FORBIDDEN, "Origin not allowed".into()).into_response();
        }
    }
    if let Some(host) = req
        .headers()
        .get(header::HOST)
        .and_then(|h| h.to_str().ok())
    {
        if host != format!("127.0.0.1:{}", s.port) && host != format!("localhost:{}", s.port) {
            return Error(StatusCode::FORBIDDEN, "Host not allowed".into()).into_response();
        }
    }
    if req.uri().path() != "/health" {
        let supplied = req
            .headers()
            .get(header::AUTHORIZATION)
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.strip_prefix("Bearer "))
            .unwrap_or("");
        let mismatch = supplied.len() != s.token.len()
            || supplied
                .bytes()
                .zip(s.token.bytes())
                .fold(0, |acc, (a, b)| acc | (a ^ b))
                != 0;
        if mismatch {
            return Error(StatusCode::UNAUTHORIZED, "Local API token required".into())
                .into_response();
        }
    }
    next.run(req).await
}
#[derive(Deserialize)]
struct Page {
    #[serde(default)]
    offset: usize,
    #[serde(default = "page_size")]
    limit: usize,
    #[serde(default)]
    status: String,
}
fn page_size() -> usize {
    100
}
async fn list(State(s): State<Arc<Api>>, Query(p): Query<Page>) -> Result<Json<Value>> {
    Ok(Json(
        s.engine
            .request(Op::Snapshot {
                offset: p.offset,
                limit: p.limit.clamp(1, 500),
                filter: p.status,
            })
            .await?,
    ))
}
async fn summary(State(s): State<Arc<Api>>) -> Result<Json<Value>> {
    let v = s
        .engine
        .request(Op::Snapshot {
            offset: 0,
            limit: 0,
            filter: String::new(),
        })
        .await?;
    Ok(Json(v["summary"].clone()))
}
async fn info(State(s): State<Arc<Api>>) -> Json<Value> {
    Json(
        json!({"version":env!("CARGO_PKG_VERSION"),"root":s.root,"platform":std::env::consts::OS,"default_shell":crate::store::default_shell(),"shells":if cfg!(windows){vec!["powershell","cmd","wsl","bash"]}else{vec!["bash"]}}),
    )
}
async fn create(
    State(s): State<Arc<Api>>,
    Json(data): Json<Create>,
) -> Result<(StatusCode, Json<Value>)> {
    Ok((
        StatusCode::CREATED,
        Json(s.engine.request(Op::Create(data)).await?),
    ))
}
async fn detail(State(s): State<Arc<Api>>, Path(id): Path<String>) -> Result<Json<Value>> {
    Ok(Json(s.engine.request(Op::Get(id)).await?))
}
#[derive(Deserialize)]
struct DeleteConfirmation {
    confirm: bool,
}
async fn delete_completed(
    State(s): State<Arc<Api>>,
    Json(body): Json<DeleteConfirmation>,
) -> Result<Json<Value>> {
    if !body.confirm {
        return Err(Error(
            StatusCode::BAD_REQUEST,
            "Explicit confirmation is required".into(),
        ));
    }
    Ok(Json(s.engine.request(Op::DeleteCompleted).await?))
}
async fn action(
    State(s): State<Arc<Api>>,
    Path((id, action)): Path<(String, String)>,
    body: Option<Json<Value>>,
) -> Result<(StatusCode, Json<Value>)> {
    let position = body
        .and_then(|b| b.0.get("position").and_then(|v| v.as_u64()))
        .unwrap_or(0) as usize;
    let code = if action == "retry" {
        StatusCode::CREATED
    } else if matches!(action.as_str(), "stop" | "delete") {
        StatusCode::ACCEPTED
    } else {
        StatusCode::OK
    };
    Ok((
        code,
        Json(s.engine.request(Op::Action(id, action, position)).await?),
    ))
}
async fn queue(State(s): State<Arc<Api>>, Path(action): Path<String>) -> Result<Json<Value>> {
    let pause = match action.as_str() {
        "pause" => true,
        "resume" => false,
        _ => return Err(Error(StatusCode::NOT_FOUND, "not found".into())),
    };
    Ok(Json(s.engine.request(Op::Queue(pause)).await?))
}
async fn events(
    State(s): State<Arc<Api>>,
) -> Sse<impl futures_util::Stream<Item = std::result::Result<Event, Infallible>>> {
    let stream = BroadcastStream::new(s.engine.events.subscribe()).map(|r| {
        Ok(Event::default()
            .event("change")
            .data(r.map(|v| v.to_string()).unwrap_or_else(|_| "resync".into())))
    });
    // Subscribe before sending ready so mutations between initial GET and subscription cannot be missed.
    let ready =
        futures_util::stream::once(async { Ok(Event::default().event("change").data("ready")) });
    Sse::new(ready.chain(stream)).keep_alive(KeepAlive::default())
}
#[derive(Deserialize)]
struct LogQuery {
    #[serde(default = "stdout")]
    stream: String,
    offset: Option<u64>,
}
fn stdout() -> String {
    "stdout".into()
}
async fn logs(
    State(s): State<Arc<Api>>,
    Path(id): Path<String>,
    Query(q): Query<LogQuery>,
) -> Result<Json<Value>> {
    if !matches!(q.stream.as_str(), "stdout" | "stderr") {
        return Err(Error(StatusCode::BAD_REQUEST, "Invalid stream".into()));
    }
    let e = s.engine.request(Op::Get(id)).await?;
    let path = e[format!("{}_path", q.stream)]
        .as_str()
        .unwrap_or("")
        .to_string();
    let complete = crate::store::terminal(e["status"].as_str().unwrap_or(""));
    let result = tokio::task::spawn_blocking(move || read_log(&path, q.offset, complete))
        .await
        .map_err(|e| Error(StatusCode::INTERNAL_SERVER_ERROR, err(e)))??;
    Ok(Json(result))
}
fn read_log(path: &str, offset: Option<u64>, complete: bool) -> std::result::Result<Value, String> {
    let mut f = match std::fs::File::open(path) {
        Ok(f) => f,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            return Ok(json!({"text":"","offset":0,"reset":offset.is_some_and(|v|v>0)}))
        }
        Err(e) => return Err(err(e)),
    };
    let len = f.metadata().map_err(err)?.len();
    let reset = offset.is_some_and(|o| o > len);
    let start = if reset {
        0
    } else {
        offset.unwrap_or(len.saturating_sub(65536))
    };
    f.seek(SeekFrom::Start(start)).map_err(err)?;
    let mut bytes = Vec::new();
    f.take(65536).read_to_end(&mut bytes).map_err(err)?;
    // Do not split an incomplete UTF-8 suffix across requests.
    let used = match std::str::from_utf8(&bytes) {
        Err(e) if e.error_len().is_none() && (!complete || start + (bytes.len() as u64) < len) => {
            e.valid_up_to()
        }
        _ => bytes.len(),
    };
    Ok(
        json!({"text":String::from_utf8_lossy(&bytes[..used]),"offset":start+used as u64,"reset":reset,"more":start+(bytes.len() as u64)<len}),
    )
}

#[cfg(test)]
mod tests {
    use super::read_log;
    #[test]
    fn log_cursor_preserves_utf8_and_handles_truncation() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("stdout.log");
        let name = path.to_str().unwrap();
        let mut bytes = vec![b'a'; 65535];
        bytes.extend_from_slice("中".as_bytes());
        std::fs::write(&path, bytes).unwrap();
        let first = read_log(name, Some(0), false).unwrap();
        assert_eq!(first["offset"], 65535);
        assert_eq!(read_log(name, Some(65535), false).unwrap()["text"], "中");
        std::fs::write(&path, b"new").unwrap();
        let reset = read_log(name, Some(65538), false).unwrap();
        assert_eq!(reset["reset"], true);
        assert_eq!(reset["text"], "new");
        std::fs::write(&path, [0xe4]).unwrap();
        assert_eq!(read_log(name, Some(0), false).unwrap()["offset"], 0);
        assert_eq!(read_log(name, Some(0), true).unwrap()["offset"], 1);
    }
}
