use super::*;
use crate::{
    digest_json,
    evidence::{PopplerExtractor, TextExtractor},
    grouping::hash_source,
    inventory::checked_path,
    models::PageText,
};
use sha2::{Digest, Sha256};
use std::{io::Read, time::Duration};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Engine {
    pub id: String,
    pub binary: PathBuf,
    pub binary_sha256: String,
    pub provenance: Value,
    pub chunk_pages: u32,
    pub timeout_secs: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Job {
    pub id: String,
    pub output: PathBuf,
    pub source_root: PathBuf,
    pub snapshot_id: String,
    pub ready: Ready,
    pub engine: Engine,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Chunk {
    pub schema_version: u32,
    pub sha256: String,
    pub engine_id: String,
    pub first: u32,
    pub last: u32,
    pub pages: Vec<PageText>,
    pub warnings: Vec<String>,
    pub checksum: String,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct WorkerResult {
    pub status: String,
    pub error: Option<String>,
    pub reused_ranges: usize,
    pub extracted_ranges: usize,
    pub text_pages: usize,
    pub empty_pages: Vec<u32>,
    pub sparse_pages: Vec<u32>,
}
pub fn range_path(output: &Path, sha: &str, engine: &Engine, first: u32, last: u32) -> PathBuf {
    output
        .join("cache/pages")
        .join(sha)
        .join(&engine.id)
        .join(format!("{first}-{last}.json"))
}
pub fn read_chunk(
    output: &Path,
    sha: &str,
    engine: &Engine,
    first: u32,
    last: u32,
) -> Result<Chunk> {
    let mut c: Chunk = read_json(&range_path(output, sha, engine, first, last))?;
    let checksum = std::mem::take(&mut c.checksum);
    if c.schema_version != 1
        || c.sha256 != sha
        || c.engine_id != engine.id
        || c.first != first
        || c.last != last
        || c.pages.iter().map(|p| p.page).collect::<Vec<_>>() != (first..=last).collect::<Vec<_>>()
        || digest_json(&c) != checksum
    {
        return Err(SelectionError::Invalid("invalid range/checksum".into()));
    }
    c.checksum = checksum;
    Ok(c)
}
pub fn all_chunks(output: &Path, ready: &Ready, engine: &Engine) -> Result<Vec<Chunk>> {
    let mut chunks = vec![];
    for first in (1..=ready.page_count).step_by(engine.chunk_pages as usize) {
        let last = ready.page_count.min(first + engine.chunk_pages - 1);
        chunks.push(read_chunk(output, &ready.sha256, engine, first, last)?);
    }
    Ok(chunks)
}
fn stage(job: &Job) -> Result<PathBuf> {
    let dest = job
        .output
        .join("cache/sources")
        .join(format!("{}.pdf", job.ready.sha256));
    if dest.exists() && hash_source(&dest)? == job.ready.sha256 {
        return Ok(dest);
    }
    let source = checked_path(&job.source_root, &job.ready.relative_path)?;
    fs::create_dir_all(dest.parent().unwrap())?;
    let tmp = dest.with_extension(format!("staging-{}", std::process::id()));
    let result = (|| {
        let mut input = File::open(&source)?;
        let mut output = File::create_new(&tmp)?;
        let mut hash = Sha256::new();
        let mut buf = [0u8; 128 * 1024];
        loop {
            let n = input.read(&mut buf)?;
            if n == 0 {
                break;
            }
            hash.update(&buf[..n]);
            output.write_all(&buf[..n])?;
        }
        output.sync_all()?;
        if format!("{:x}", hash.finalize()) != job.ready.sha256 {
            return Err(SelectionError::Invalid(
                "source hash changed; rescan/reselect".into(),
            ));
        }
        fs::rename(&tmp, &dest)?;
        Ok(dest.clone())
    })();
    if result.is_err() {
        let _ = fs::remove_file(tmp);
    }
    result
}
pub fn run(path: &Path) -> Result<()> {
    let job: Job = read_json(path)?;
    safe_id(&job.id)?;
    safe_id(&job.ready.sha256)?;
    safe_id(&job.engine.id)?;
    validate_output(&job.output)?;
    let _lease = lock(&job.output.join("leases"), &job.id)?;
    let mut result = WorkerResult::default();
    let attempt = (|| -> Result<()> {
        if hash_source(&job.engine.binary)? != job.engine.binary_sha256 {
            return Err(SelectionError::Invalid(
                "extractor changed since dispatch".into(),
            ));
        }
        let path = stage(&job)?;
        let extractor = PopplerExtractor::new(
            job.engine.binary.clone(),
            Duration::from_secs(job.engine.timeout_secs),
        );
        for first in (1..=job.ready.page_count).step_by(job.engine.chunk_pages as usize) {
            let last = job.ready.page_count.min(first + job.engine.chunk_pages - 1);
            let chunk = if let Ok(c) =
                read_chunk(&job.output, &job.ready.sha256, &job.engine, first, last)
            {
                result.reused_ranges += 1;
                c
            } else {
                eprintln!(
                    "{}: extracting physical pages {first}-{last}/{}",
                    job.ready.source_id, job.ready.page_count
                );
                let pages = extractor.extract(&path, &(first..=last).collect::<Vec<_>>())?;
                if pages.iter().map(|p| p.page).collect::<Vec<_>>()
                    != (first..=last).collect::<Vec<_>>()
                {
                    return Err(SelectionError::Invalid(
                        "extractor page coverage mismatch".into(),
                    ));
                }
                let mut c = Chunk {
                    schema_version: 1,
                    sha256: job.ready.sha256.clone(),
                    engine_id: job.engine.id.clone(),
                    first,
                    last,
                    pages,
                    warnings: extractor.warnings(),
                    checksum: String::new(),
                };
                c.checksum = digest_json(&c);
                write_json(
                    &range_path(&job.output, &job.ready.sha256, &job.engine, first, last),
                    &c,
                )?;
                result.extracted_ranges += 1;
                c
            };
            for p in &chunk.pages {
                let chars = p.text.chars().filter(|c| c.is_alphanumeric()).count();
                if p.text.trim().is_empty() {
                    result.empty_pages.push(p.page);
                } else {
                    result.text_pages += 1;
                    if chars < 40 {
                        result.sparse_pages.push(p.page);
                    }
                }
            }
        }
        if hash_source(&path)? != job.ready.sha256 {
            return Err(SelectionError::Invalid(
                "cached source changed during extraction".into(),
            ));
        }
        result.status = if result.text_pages == 0 {
            "needs_ocr_or_visual_review"
        } else {
            "complete"
        }
        .into();
        Ok(())
    })();
    if let Err(e) = attempt {
        result.status = "failed".into();
        result.error = Some(e.to_string());
    }
    write_json(
        &job.output.join("results").join(format!("{}.json", job.id)),
        &result,
    )
}
