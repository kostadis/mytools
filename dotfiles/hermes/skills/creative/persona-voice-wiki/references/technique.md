# Technique: chunked build + concatenate + verify

For persona-voiced wikis with multiple large files (>~3k words each), do NOT write the whole file in one `write_file` call. Write in parts, then `cat` together. This avoids write-tool stalls/truncation and lets you sanity-check each section.

## 1. Write parts to /tmp
Write each section (or campaign) as `/tmp/<name>_partN.md` via `write_file`. Keep each part self-contained (own headings). Multiple `write_file` calls can be batched in one turn.

## 2. Concatenate into the final path
Run once per file:
```
cat /tmp/chron_part1.md /tmp/chron_part2.md /tmp/chron_part3.md > /home/kostadis/histories/historian_chronology.md
wc -w /home/kostadis/histories/historian_chronology.md
wc -l /home/kostadis/histories/historian_chronology.md
```

## 3. Verify (grep counts must line up)
```
# citations present (adapt regex to source conventions)
grep -c 'ch: chapter_\|(chapter_\|(ch[0-9]' /path/to/file.md
# opinion blocks present (should equal event/npc count)
grep -c "Historian's Assessment" /path/to/file.md
# signoffs present (should equal assessments + any closing statements)
grep -c '— The Persona Name' /path/to/file.md
```
If a count is low, a section was dropped during concatenation — rebuild that `/tmp` chunk and re-`cat`.

## 4. Report
Give the user: each file path, line count, word count, and a one-line note on what it contains.
