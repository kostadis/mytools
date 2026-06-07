use anyhow::{Context, Result};
use std::fs;
use std::path::PathBuf;

/// Microsoft Graph base URL
pub const GRAPH_BASE: &str = "https://graph.microsoft.com/v1.0";

/// Azure authority for personal Microsoft accounts
const AUTHORITY: &str = "https://login.microsoftonline.com/consumers";

/// OneDrive scopes
pub const READ_SCOPE: &str = "https://graph.microsoft.com/Files.Read";
pub const WRITE_SCOPE: &str = "https://graph.microsoft.com/Files.ReadWrite";

pub const CONFIG_DIR: &str = ".config/onedrive-cli";

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct Token {
    pub access_token: String,
    pub expires_at: Option<i64>,
}

impl Token {
    pub fn is_expired(&self) -> bool {
        if let Some(expires_at) = self.expires_at {
            let now = chrono::Utc::now().timestamp();
            expires_at - 60 < now
        } else {
            false
        }
    }
}

/// Get config directory path
pub fn config_dir() -> Result<PathBuf> {
    let dir = dirs::home_dir()
        .context("Cannot find home directory")?
        .join(CONFIG_DIR);
    fs::create_dir_all(&dir).context("Cannot create config directory")?;
    Ok(dir)
}

/// App config path
pub fn credentials_path() -> Result<PathBuf> {
    Ok(config_dir()?.join("credentials.json"))
}

fn token_path() -> Result<PathBuf> {
    Ok(config_dir()?.join("token.json"))
}

async fn exchange_code(client_id: &str, client_secret: &str, code: &str) -> Result<Token> {
    let client = reqwest::Client::new();

    let form = [
        ("client_id", client_id),
        ("client_secret", client_secret),
        ("code", code),
        ("grant_type", "authorization_code"),
        ("redirect_uri", "http://localhost:8080"),
        ("scope", "https://graph.microsoft.com/Files.ReadWrite"),
    ];

    let resp = client
        .post(&format!("{}/oauth2/v2.0/token", AUTHORITY))
        .form(&form)
        .send()
        .await
        .context("Token exchange request failed")?;

    if !resp.status().is_success() {
        let error = resp.text().await?;
        anyhow::bail!("Token exchange failed: {}", error);
    }

    let json: serde_json::Value = resp.json().await?;

    let access_token = json["access_token"]
        .as_str()
        .context("Missing access_token")?
        .to_string();
    let expires_in = json["expires_in"].as_i64();

    Ok(Token {
        access_token,
        expires_at: expires_in.map(|d| chrono::Utc::now().timestamp() + d),
    })
}

pub async fn get_credentials() -> Result<Token> {
    let token_path = token_path()?;

    // Try to load existing token
    if token_path.exists() {
        let data = fs::read_to_string(&token_path)?;
        if let Ok(token) = serde_json::from_str::<Token>(&data) {
            if !token.is_expired() {
                return Ok(token);
            }
        }
    }

    // Need to do full OAuth flow
    let creds_path = credentials_path()?;
    if !creds_path.exists() {
        anyhow::bail!(
            "Missing {}. Create an Azure app registration with Microsoft Graph permissions, download the credentials JSON, and save it there.",
            creds_path.display()
        );
    }

    let creds_data = fs::read_to_string(&creds_path)?;
    let creds: serde_json::Value = serde_json::from_str(&creds_data)
        .context("Invalid credentials JSON")?;

    let client_id = creds["client_id"]
        .as_str()
        .context("Missing client_id")?;
    let client_secret = creds["client_secret"]
        .as_str()
        .context("Missing client_secret")?;

    let auth_url = format!(
        "{}/oauth2/v2.0/authorize?client_id={}&redirect_uri=http://localhost:8080&response_type=code&scope=https://graph.microsoft.com/Files.ReadWrite&prompt=consent",
        AUTHORITY, client_id
    );

    println!("Open this URL in your browser:");
    println!("{}", auth_url);
    println!("\nWaiting for authorization...");

    let code = tokio::task::spawn_blocking(|| {
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:8080").unwrap();
        for stream in listener.incoming() {
            if let Ok(mut stream) = stream {
                let mut buffer = [0u8; 4096];
                let n = stream.read(&mut buffer).unwrap();
                let request = String::from_utf8_lossy(&buffer[..n]);
                if let Some(start) = request.find("code=") {
                    let rest = &request[start + 5..];
                    let end = rest.find('&').unwrap_or(rest.len());
                    let code = rest[..end].to_string();

                    let response = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<html><body><h1>Authorization received. You can close this tab.</h1></body></html>";
                    let _ = stream.write_all(response);
                    return Ok::<String, std::io::Error>(code);
                }
                let response = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<html><body><h1>Authorization received. You can close this tab.</h1></body></html>";
                let _ = stream.write_all(response);
            }
        }
        Err(std::io::Error::new(std::io::ErrorKind::Other, "No authorization code received"))
    }).await??;

    let token = exchange_code(client_id, client_secret, &code).await?;

    fs::write(&token_path, serde_json::to_string_pretty(&token)?)?;
    Ok(token)
}

/// Graph GET request with retry and backoff
pub async fn graph_get(url: &str, token: &str) -> Result<reqwest::Response> {
    let client = reqwest::Client::new();
    const RETRYABLE: &[u16] = &[429, 500, 502, 503, 504];
    const MAX_ATTEMPTS: usize = 5;

    for attempt in 0..MAX_ATTEMPTS {
        let resp = client
            .get(url)
            .header("Authorization", format!("Bearer {}", token))
            .timeout(std::time::Duration::from_secs(60))
            .send()
            .await
            .context("Request failed")?;

        if RETRYABLE.contains(&resp.status().as_u16()) && attempt < MAX_ATTEMPTS - 1 {
            let delay = 2_f64.powi(attempt as i32);
            eprintln!(
                "http {}; retry {}/{} in {:.1}s",
                resp.status(),
                attempt + 1,
                MAX_ATTEMPTS - 1,
                delay
            );
            tokio::time::sleep(std::time::Duration::from_secs_f64(delay)).await;
            continue;
        }
        return Ok(resp);
    }

    unreachable!()
}
