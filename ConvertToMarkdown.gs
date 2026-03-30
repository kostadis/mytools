/**
 * ConvertToMarkdown.gs  — Sheet-bound Google Apps Script
 *
 * SETUP:
 *   1. Create a new Google Sheet
 *   2. Extensions → Apps Script → paste this file → Save
 *   3. Reload the Sheet — a "ConvertToMarkdown" menu appears
 *   4. Click ConvertToMarkdown → "Setup Sheet" to initialize layout
 *
 * SHEET LAYOUT:
 *   Row 1  — Config: A1 = label, B1 = output folder (named range: OUTPUT_FOLDER)
 *   Row 2  — Blank separator
 *   Row 3  — Column headers
 *   Row 4+ — Data rows (one Google Doc URL per row in column A)
 *
 *   Columns:
 *     A  Doc URL            Paste Google Doc URLs here
 *     B  Doc Title          Auto-filled by script
 *     C  Last Modified      Auto-filled: when the source Doc was last changed
 *     D  Last Converted     Auto-filled: when this script last converted it
 *     E  Status             Auto-filled: ✅ Converted / ⏭ Skipped / ❌ Error
 *
 * The output folder is stored in a named range called OUTPUT_FOLDER (cell B1).
 * Sorting the data table (rows 4+) can never affect it.
 */

// ─── CONSTANTS ───────────────────────────────────────────────────────────────

const NAMED_RANGE_FOLDER = "OUTPUT_FOLDER";  // Named range pointing to B1

const COL_URL            = 1;  // A
const COL_TITLE          = 2;  // B
const COL_LAST_MODIFIED  = 3;  // C
const COL_LAST_CONVERTED = 4;  // D
const COL_STATUS         = 5;  // E

const CONFIG_ROW         = 1;  // Row 1: output folder config
const HEADER_ROW         = 3;  // Row 3: column headers
const DATA_START_ROW     = 4;  // Row 4+: doc URLs

// ─── MENU ────────────────────────────────────────────────────────────────────

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("ConvertToMarkdown")
    .addItem("▶ Run Conversions", "runConversions")
    .addSeparator()
    .addItem("Setup Sheet", "setupSheet")
    .addItem("Clear All Statuses", "clearStatuses")
    .addToUi();
}

// ─── SHEET SETUP ─────────────────────────────────────────────────────────────

/**
 * Initializes the sheet layout: config row, named range, headers, formatting.
 * Safe to re-run — won't overwrite existing folder name or doc URLs.
 */
function setupSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getActiveSheet();

  // ── Row 1: config ──
  sheet.getRange(1, 1).setValue("Output Folder")
    .setFontWeight("bold")
    .setFontColor("#7a5700")
    .setBackground("#fce8b2");

  const folderCell = sheet.getRange(1, 2);
  if (!folderCell.getValue()) folderCell.setValue("Markdown Exports");
  folderCell
    .setBackground("#fce8b2")
    .setFontWeight("bold")
    .setNote(
      "Named range: OUTPUT_FOLDER\n" +
      "Enter a Google Drive folder name or folder ID.\n" +
      "The folder will be created if it doesn't exist.\n" +
      "Sorting the data table below will never affect this cell."
    );

  // Style the rest of row 1 to match
  sheet.getRange(1, 3, 1, 3).setBackground("#fce8b2");

  // Create (or update) the named range OUTPUT_FOLDER → B1
  const existing = ss.getRangeByName(NAMED_RANGE_FOLDER);
  if (!existing) {
    ss.setNamedRange(NAMED_RANGE_FOLDER, folderCell);
  }

  // ── Row 2: blank separator ──
  sheet.getRange(2, 1, 1, 5).setBackground(null).clearContent();

  // ── Row 3: headers ──
  const headers = ["Doc URL", "Doc Title", "Last Modified (Source)", "Last Converted", "Status"];
  sheet.getRange(HEADER_ROW, 1, 1, headers.length)
    .setValues([headers])
    .setFontWeight("bold")
    .setBackground("#4a86e8")
    .setFontColor("#ffffff");

  // ── Column widths ──
  sheet.setColumnWidth(COL_URL, 350);
  sheet.setColumnWidth(COL_TITLE, 220);
  sheet.setColumnWidth(COL_LAST_MODIFIED, 180);
  sheet.setColumnWidth(COL_LAST_CONVERTED, 180);
  sheet.setColumnWidth(COL_STATUS, 200);

  // Freeze config + separator + header rows so they stay put
  sheet.setFrozenRows(3);

  showAlert(
    "✅ Sheet is ready!\n\n" +
    "• Output folder is in cell B1 (named range: OUTPUT_FOLDER)\n" +
    "• Paste Google Doc URLs into column A starting at row 4\n" +
    "• Run: ConvertToMarkdown → Run Conversions\n\n" +
    "Tip: sorting the data rows will never affect the config in row 1."
  );
}

// ─── MAIN RUNNER ─────────────────────────────────────────────────────────────

/**
 * Reads the output folder from the OUTPUT_FOLDER named range (B1),
 * then processes all data rows from row 4 down.
 */
function runConversions() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getActiveSheet();

  // Read B1 directly
  const b1Cell = sheet.getRange(1, 2);
  const b1Formula = b1Cell.getFormula();
  const b1Value = b1Cell.getValue().toString().trim();
  const b1Display = b1Cell.getDisplayValue().toString().trim();

  // Extract folder ID from HYPERLINK formula if present, otherwise use raw value
  let folderIdOrName = b1Value;
  if (b1Formula) {
    const urlMatch = b1Formula.match(/HYPERLINK\s*\(\s*"([^"]+)"/i);
    if (urlMatch) {
      const folderMatch = urlMatch[1].match(/\/folders\/([a-zA-Z0-9_-]{25,})/);
      if (folderMatch) folderIdOrName = folderMatch[1];
    }
  }

  if (!folderIdOrName) {
    showAlert("Output folder is blank. Enter a folder ID in cell B1.");
    return;
  }

  let outputFolder, outputFolderRef;
  try {
    outputFolder = DriveApp.getFolderById(folderIdOrName);
    outputFolderRef = outputFolder.getName();
  } catch (e) {
    showAlert("Could not open folder with ID [" + folderIdOrName + "]:\n" + e.message);
    return;
  }

  const lastRow = sheet.getLastRow();
  if (lastRow < DATA_START_ROW) {
    showAlert("No Doc URLs found. Paste Google Doc URLs into column A starting at row 4.");
    return;
  }

  const numRows = lastRow - DATA_START_ROW + 1;
  const data = sheet.getRange(DATA_START_ROW, 1, numRows, COL_STATUS).getValues();

  let converted = 0, skipped = 0, errors = 0;

  for (let i = 0; i < data.length; i++) {
    const rowIndex = DATA_START_ROW + i;
    const url = data[i][COL_URL - 1].toString().trim();
    if (!url) continue;

    // Check if this row is a Drive folder URL — expand it into individual doc rows
    const sourceFolderId = extractFolderId(url);
    if (sourceFolderId) {
      try {
        const sourceFolder = DriveApp.getFolderById(sourceFolderId);
        setStatus(sheet, rowIndex, "📂 Expanding folder...", "#e8f0fe");
        sheet.getRange(rowIndex, COL_TITLE).setValue(sourceFolder.getName());
        SpreadsheetApp.flush();

        const docs = sourceFolder.getFilesByType(MimeType.GOOGLE_DOCS);
        const newRows = [];
        while (docs.hasNext()) {
          const f = docs.next();
          newRows.push([f.getUrl(), "", "", "", ""]);
        }

        if (newRows.length === 0) {
          setStatus(sheet, rowIndex, "📂 No Docs found in folder", "#fce8b2");
        } else {
          // Insert new rows after current row and populate them
          sheet.insertRowsAfter(rowIndex, newRows.length);
          sheet.getRange(rowIndex + 1, 1, newRows.length, 5).setValues(newRows);
          setStatus(sheet, rowIndex, "📂 Expanded (" + newRows.length + " docs)", "#d9ead3");
          // Extend our loop to cover the newly inserted rows
          data.splice(i + 1, 0, ...newRows);
        }
      } catch (e) {
        setStatus(sheet, rowIndex, "❌ Folder error: " + e.message, "#f4cccc");
        errors++;
      }
      continue;
    }

    const docId = extractDocId(url);
    if (!docId) {
      setStatus(sheet, rowIndex, "❌ Invalid URL", "#f4cccc");
      errors++;
      continue;
    }

    try {
      const file = DriveApp.getFileById(docId);
      const docLastModified = file.getLastUpdated();
      const lastConverted = data[i][COL_LAST_CONVERTED - 1];

      sheet.getRange(rowIndex, COL_TITLE).setValue(file.getName());
      sheet.getRange(rowIndex, COL_LAST_MODIFIED).setValue(docLastModified);

      // Skip if source hasn't changed since last conversion
      if (lastConverted && lastConverted instanceof Date && docLastModified <= lastConverted) {
        setStatus(sheet, rowIndex, "⏭ Skipped (up to date)", "#d9ead3");
        skipped++;
        continue;
      }

      const doc = DocumentApp.openById(docId);
      const md = docToMarkdown(doc);
      saveMarkdownFile(file.getName(), md, outputFolder);

      sheet.getRange(rowIndex, COL_LAST_CONVERTED).setValue(new Date());
      setStatus(sheet, rowIndex, "✅ Converted", "#d9ead3");
      converted++;

    } catch (e) {
      setStatus(sheet, rowIndex, "❌ " + e.message, "#f4cccc");
      errors++;
    }

    if (i % 5 === 0) SpreadsheetApp.flush();
  }

  SpreadsheetApp.flush();
  showAlert(
    `Run complete!\n\n` +
    `✅ Converted:  ${converted}\n` +
    `⏭ Skipped:    ${skipped} (already up to date)\n` +
    `❌ Errors:     ${errors}\n\n` +
    `Output folder: "${outputFolderRef}"`
  );
}

/**
 * Clears Last Converted and Status columns so all rows re-convert on next run.
 */
function clearStatuses() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const lastRow = sheet.getLastRow();
  if (lastRow < DATA_START_ROW) return;

  const numRows = lastRow - DATA_START_ROW + 1;
  sheet.getRange(DATA_START_ROW, COL_LAST_CONVERTED, numRows, 1).clearContent();
  sheet.getRange(DATA_START_ROW, COL_STATUS, numRows, 1).clearContent().setBackground(null);

  showAlert("Statuses cleared. All docs will be re-converted on next run.");
}

// ─── HELPERS: SHEET ──────────────────────────────────────────────────────────

function setStatus(sheet, row, message, color) {
  const cell = sheet.getRange(row, COL_STATUS);
  cell.setValue(message);
  cell.setBackground(color || null);
}

// ─── HELPERS: URL / ID ───────────────────────────────────────────────────────

/**
 * Extracts a Drive file ID from a Google Docs/Drive URL,
 * or returns the string directly if it already looks like a bare ID.
 */
function extractDocId(urlOrId) {
  const match = urlOrId.match(/\/d\/([a-zA-Z0-9_-]{25,})/);
  if (match) return match[1];
  if (/^[a-zA-Z0-9_-]{25,}$/.test(urlOrId)) return urlOrId;
  return null;
}

/**
 * Extracts a Drive folder ID from a folder URL.
 * Handles:
 *   https://drive.google.com/drive/folders/FOLDER_ID
 *   https://drive.google.com/drive/u/0/folders/FOLDER_ID
 */
function extractFolderId(url) {
  const match = url.match(/\/folders\/([a-zA-Z0-9_-]{25,})/);
  return match ? match[1] : null;
}

/**
 * Reads the raw formula from the OUTPUT_FOLDER cell and extracts the
 * folder ID or name from it, handling three cases:
 *
 *   1. Google auto-converted the pasted URL to =HYPERLINK("url","name")
 *      → extract the URL from the formula and parse the folder ID from it
 *
 *   2. Plain Drive folder URL pasted as text
 *      → parse the folder ID directly
 *
 *   3. Plain folder name or bare folder ID
 *      → return as-is
 */
function resolveFolderRef(ss) {
  const range = ss.getRangeByName(NAMED_RANGE_FOLDER);
  if (!range) return null;

  // Check for a HYPERLINK formula — Sheets auto-creates these when you paste URLs
  const formula = range.getFormula();
  if (formula) {
    // =HYPERLINK("https://drive.google.com/drive/folders/FOLDER_ID","Name")
    const urlMatch = formula.match(/HYPERLINK\s*\(\s*"([^"]+)"/i);
    if (urlMatch) {
      const id = extractFolderId(urlMatch[1]);
      if (id) return { type: "id", value: id };
    }
  }

  // No formula — read display value
  const value = range.getValue().toString().trim();
  if (!value) return null;

  // Plain Drive URL pasted as text?
  const idFromUrl = extractFolderId(value);
  if (idFromUrl) return { type: "id", value: idFromUrl };

  // Bare folder ID?
  if (/^[a-zA-Z0-9_-]{25,}$/.test(value)) return { type: "id", value };

  // Folder name — will search Drive
  return { type: "name", value };
}

// ─── HELPERS: DRIVE ──────────────────────────────────────────────────────────

/**
 * Resolves the output folder from the named range, handling hyperlink formulas,
 * plain URLs, bare IDs, and folder names.
 * When given a name, searches all of Drive (not just root) and returns the
 * first match, or creates a new folder at root if none found.
 */
function getOutputFolder(ss) {
  const ref = resolveFolderRef(ss);
  if (!ref) throw new Error("Output folder not set in cell B1.");

  if (ref.type === "id") {
    try {
      return DriveApp.getFolderById(ref.value);
    } catch (e) {
      throw new Error(`Could not open folder with ID "${ref.value}". Check that the script has access to it.`);
    }
  }

  // Name-based lookup — warn user this is ambiguous
  const existing = DriveApp.getFoldersByName(ref.value);
  if (existing.hasNext()) return existing.next();

  // Not found — create at root and warn
  Logger.log(`Folder "${ref.value}" not found — creating at Drive root.`);
  return DriveApp.createFolder(ref.value);
}

function saveMarkdownFile(name, content, folder) {
  const filename = sanitizeFilename(name) + ".md";
  const existing = folder.getFilesByName(filename);
  while (existing.hasNext()) existing.next().setTrashed(true);
  folder.createFile(filename, content, MimeType.PLAIN_TEXT);
}

function sanitizeFilename(name) {
  return name.replace(/[\/\\:*?"<>|]/g, "-").trim();
}

// ─── CORE: DOC → MARKDOWN ────────────────────────────────────────────────────

function docToMarkdown(doc) {
  const body = doc.getBody();
  const lines = [];

  for (let i = 0; i < body.getNumChildren(); i++) {
    const child = body.getChild(i);
    const type = child.getType();

    if (type === DocumentApp.ElementType.PARAGRAPH) {
      lines.push(convertParagraph(child.asParagraph()));
    } else if (type === DocumentApp.ElementType.LIST_ITEM) {
      lines.push(convertListItem(child.asListItem()));
    } else if (type === DocumentApp.ElementType.TABLE) {
      lines.push(convertTable(child.asTable()));
    } else if (type === DocumentApp.ElementType.HORIZONTAL_RULE) {
      lines.push("---");
    } else if (type === DocumentApp.ElementType.TABLE_OF_CONTENTS) {
      lines.push("<!-- Table of Contents -->");
    }
  }

  return lines.join("\n").replace(/\n{3,}/g, "\n\n").trim() + "\n";
}

function convertParagraph(para) {
  const text = convertInlineElements(para);
  if (!text.trim()) return "";

  switch (para.getHeading()) {
    case DocumentApp.ParagraphHeading.HEADING1:  return `# ${text}`;
    case DocumentApp.ParagraphHeading.HEADING2:  return `## ${text}`;
    case DocumentApp.ParagraphHeading.HEADING3:  return `### ${text}`;
    case DocumentApp.ParagraphHeading.HEADING4:  return `#### ${text}`;
    case DocumentApp.ParagraphHeading.HEADING5:  return `##### ${text}`;
    case DocumentApp.ParagraphHeading.HEADING6:  return `###### ${text}`;
    case DocumentApp.ParagraphHeading.TITLE:     return `# ${text}`;
    case DocumentApp.ParagraphHeading.SUBTITLE:  return `## ${text}`;
    default:                                      return text;
  }
}

function convertListItem(item) {
  const text = convertInlineElements(item);
  const indent = "  ".repeat(item.getNestingLevel());
  const isOrdered = [
    DocumentApp.GlyphType.NUMBER,
    DocumentApp.GlyphType.LATIN_LOWER,
    DocumentApp.GlyphType.LATIN_UPPER,
    DocumentApp.GlyphType.ROMAN_LOWER,
    DocumentApp.GlyphType.ROMAN_UPPER,
  ].includes(item.getGlyphType());

  return isOrdered ? `${indent}1. ${text}` : `${indent}- ${text}`;
}

function convertTable(table) {
  const rows = [];
  const numRows = table.getNumRows();
  if (numRows === 0) return "";

  for (let r = 0; r < numRows; r++) {
    const row = table.getRow(r);
    const cells = [];
    for (let c = 0; c < row.getNumCells(); c++) {
      cells.push(row.getCell(c).getText().replace(/\n/g, " ").replace(/\|/g, "\\|"));
    }
    rows.push("| " + cells.join(" | ") + " |");
    if (r === 0) rows.push("| " + cells.map(() => "---").join(" | ") + " |");
  }

  return rows.join("\n");
}

function convertInlineElements(element) {
  let result = "";
  for (let i = 0; i < element.getNumChildren(); i++) {
    const child = element.getChild(i);
    if (child.getType() === DocumentApp.ElementType.TEXT) {
      result += convertTextElement(child.asText());
    } else if (child.getType() === DocumentApp.ElementType.INLINE_IMAGE) {
      result += "![image]()";
    }
  }
  return result;
}

function convertTextElement(textEl) {
  const raw = textEl.getText();
  if (!raw) return "";

  const indices = textEl.getTextAttributeIndices();
  const runs = [];
  for (let i = 0; i < indices.length; i++) {
    runs.push({
      start: indices[i],
      end: (i + 1 < indices.length) ? indices[i + 1] : raw.length,
      text: raw.slice(indices[i], (i + 1 < indices.length) ? indices[i + 1] : raw.length)
    });
  }
  if (runs.length === 0) runs.push({ start: 0, end: raw.length, text: raw });

  let result = "";
  for (const run of runs) {
    if (!run.text) continue;
    const isBold   = textEl.isBold(run.start);
    const isItalic = textEl.isItalic(run.start);
    const isStrike = textEl.isStrikethrough(run.start);
    const font     = textEl.getFontFamily(run.start);
    const isCode   = font === "Courier New" || font === "Consolas" || font === "Roboto Mono";
    const linkUrl  = textEl.getLinkUrl(run.start);

    let chunk = run.text;
    if (!isCode) chunk = escapeMarkdown(chunk);
    if (isCode)             chunk = `\`${chunk}\``;
    if (isBold && isItalic) chunk = `***${chunk}***`;
    else if (isBold)        chunk = `**${chunk}**`;
    else if (isItalic)      chunk = `*${chunk}*`;
    if (isStrike)           chunk = `~~${chunk}~~`;
    if (linkUrl)            chunk = `[${chunk}](${linkUrl})`;
    result += chunk;
  }
  return result;
}

function escapeMarkdown(text) {
  return text
    .replace(/\\/g, "\\\\")
    .replace(/\*/g, "\\*")
    .replace(/_/g, "\\_")
    .replace(/`/g, "\\`")
    .replace(/\[/g, "\\[")
    .replace(/\]/g, "\\]");
}

// ─── UI ──────────────────────────────────────────────────────────────────────

function showAlert(message) {
  try {
    SpreadsheetApp.getUi().alert(message);
  } catch (e) {
    Logger.log(message);
  }
}
