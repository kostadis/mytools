use anyhow::{Context, Result};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

const READ_SCOPE: &str = "https://www.googleapis.com/auth/drive.readonly";
const WRITE_SCOPE: &str = "https://www.googleapis.com/auth/drive";

pub const CONFIG_DIR: &str = ".config/gdrive-cli";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Token {
    pub access_token: String,
    pub refresh_token: Option<String>,
    pub expires_at: Option<i64>,
    pub scopes: Vec<String>,
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

pub fn config_dir() -> Result<PathBuf> {
    let dir = dirs::home_dir()
        .context("Cannot find home directory")?
        .join(CONFIG_DIR);
    fs::create_dir_all(&dir).context("Cannot create config directory")?;
    Ok(dir)
}

pub fn credentials_path() -> Result<PathBuf> {
    Ok(config_dir()?.join("credentials.json"))
}

fn token_path(write: bool) -> Result<PathBuf> {
    let name = if write { "token-write.json" } else { "token.json" };
    Ok(config_dir()?.join(name))
}

async fn exchange_code(client_id: &str, client_secret: &str, code: &str, scope: &str) -> Result<Token> {
    let client = Client::new();
    
    let form = [
        ("client_id", client_id),
        ("client_secret", client_secret),
        ("code", code),
        ("grant_type", "authorization_code"),
        ("redirect_uri", "http://localhost:8080"),
        ("scope", scope),
    ];

    let resp = client
        .post("https://oauth2.googleapis.com/token")
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
    let refresh_token = json["refresh_token"].as_str().map(String::from);
    let expires_in = json["expires_in"].as_i64();
    
    Ok(Token {
        access_token,
        refresh_token,
        expires_at: expires_in.map(|d| chrono::Utc::now().timestamp() + d),
        scopes: vec![scope.to_string()],
    })
}

async fn refresh_token(client_secret: &str, refresh_token: &str, scope: &str) -> Result<Token> {
    let client = Client::new();
    
    let creds_path = credentials_path()?;
    let creds_data = fs::read_to_string(&creds_path)?;
    let creds: serde_json::Value = serde_json::from_str(&creds_data)?;
    let client_id = creds["installed"]["client_id"]
        .as_str()
        .context("Missing client_id")?;

    let form = [
        ("client_id", client_id),
        ("client_secret", client_secret),
        ("grant_type", "refresh_token"),
        ("refresh_token", refresh_token),
        ("scope", scope),
    ];

    let resp = client
        .post("https://oauth2.googleapis.com/token")
        .form(&form)
        .send()
        .await
        .context("Token refresh request failed")?;

    if !resp.status().is_success() {
        let error = resp.text().await?;
        anyhow::bail!("Token refresh failed: {}", error);
    }

    let json: serde_json::Value = resp.json().await?;
    
    let access_token = json["access_token"]
        .as_str()
        .context("Missing access_token")?
        .to_string();
    let expires_in = json["expires_in"].as_i64();
    
    Ok(Token {
        access_token,
        refresh_token: Some(refresh_token.to_string()),
        expires_at: expires_in.map(|d| chrono::Utc::now().timestamp() + d),
        scopes: vec![scope.to_string()],
    })
}

pub async fn get_credentials(write: bool) -> Result<Token> {
    let scope = if write { WRITE_SCOPE } else { READ_SCOPE };

    let token_path = token_path(write)?;

    // Try to load existing token
    if token_path.exists() {
        let data = fs::read_to_string(&token_path)?;
        if let Ok(token) = serde_json::from_str::<Token>(&data) {
            if !token.is_expired() {
                return Ok(token);
            }
            // Token expired, try to refresh
            if let Some(rt) = &token.refresh_token {
                let creds_path = credentials_path()?;
                let creds_data = fs::read_to_string(&creds_path)?;
                let creds: serde_json::Value = serde_json::from_str(&creds_data)?;
                let client_secret = creds["installed"]["client_secret"]
                    .as_str()
                    .context("Missing client_secret")?;
                
                match refresh_token(client_secret, rt, scope).await {
                    Ok(new_token) => {
                        fs::write(&token_path, serde_json::to_string_pretty(&new_token)?)?;
                        return Ok(new_token);
                    }
                    Err(e) => {
                        eprintln!("Failed to refresh token: {}. Re-authorizing...", e);
                    }
                }
            }
        }
    }

    // Need to do full OAuth flow
    let creds_path = credentials_path()?;
    if !creds_path.exists() {
        anyhow::bail!(
            "Missing {}. Create an OAuth Desktop client in GCP, enable Drive API, download JSON, and save it there.",
            creds_path.display()
        );
    }

    let creds_data = fs::read_to_string(&creds_path)?;
    let creds: serde_json::Value = serde_json::from_str(&creds_data)
        .context("Invalid credentials JSON")?;

    let client_id = creds["installed"]["client_id"]
        .as_str()
        .context("Missing client_id")?;
    let client_secret = creds["installed"]["client_secret"]
        .as_str()
        .context("Missing client_secret")?;

    let auth_url = format!(
        "https://accounts.google.com/o/oauth2/v2/auth?client_id={}&redirect_uri=http://localhost:8080&response_type=code&scope={}&access_type=offline&prompt=consent",
        client_id,
        urlencoding::encode(scope)
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

    let token = exchange_code(client_id, client_secret, &code, scope).await?;

    fs::write(&token_path, serde_json::to_string_pretty(&token)?)?;
    Ok(token)
}

pub async fn drive_client_read() -> Result<(Client, String)> {
    let token = get_credentials(false).await?;
    Ok((Client::new(), token.access_token))
}

pub async fn drive_client_write() -> Result<(Client, String)> {
    let token = get_credentials(true).await?;
    Ok((Client::new(), token.access_token))
}
