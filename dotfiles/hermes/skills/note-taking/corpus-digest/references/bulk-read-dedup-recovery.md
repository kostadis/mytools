# Bulk-read dedup recovery — read_file cache-miss detection

## Problem
When reading 40+ files in batches, `read_file` on an already-ingested file may return:
- `{"status":"unchanged","dedup":true,"content_returned":false}` ... "File unchanged since last read."
- or simply the earlier content with a note that it's "still current."

This is NOT a skipped file — the content is already in context. But across a huge batch
you cannot be 100% sure every file registered. The safe, single verification pass:

## Step 1 — Pull every H1 into one view
```
search_files(
  pattern="^# ",           # or "^# Chapter" for "Chapter NN" titles
  target="content",
  path="<directory>",
  output_mode="content",   # path-grouped: each file then "<line>: <content>"
  limit=100
)
```
This returns every file's title line in one tool call — a complete inventory.

## Step 2 — Cross-check
Compare the returned titles against the file list from the initial
`search_files(target="files")` inventory. Every expected file must appear with a title.
If a file's title is MISSING from the content grep, that file's body did NOT register —
`read_file` it explicitly (use offset/limit to page large files).

## Step 3 — Proceed
Once the cross-check passes, you have read everything. Do not re-read blindly; trust
the grep. For very large files (>~15k chars) read by paging offset/limit so no tail is cut.

## Note on numbering
Filenames often run one number ahead of internal H1s (chapter_02 -> "Chapter 01").
Record this mapping in the digest header; cite by filename so citations stay stable.
