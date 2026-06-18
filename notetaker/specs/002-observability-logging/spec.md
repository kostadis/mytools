# Feature Specification: Pipeline Progress Logging

**Feature Branch**: `002-observability-logging`
**Created**: 2026-05-09
**Status**: Draft
**Input**: User description: "I want to be able to know what notetaker is doing. Ideally it reports via logfile where it is and what its' done and what phase it is."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Confirm a long-running pipeline is alive (Priority: P1)

While a notetaker run is processing a recording (capture + transcript scrape can run for the full duration of the meeting; understanding/synthesis can each take minutes for a long deck), the user wants to look at a log somewhere and immediately know whether the pipeline is still making progress, what phase it is in, and roughly when it last did something. If nothing has happened in a noticeable window, the user should be able to conclude with confidence that the pipeline is hung or has crashed — not just "maybe still working."

**Why this priority**: This is the original, unblocking pain point — the user explicitly framed the request as *"How do I know it's running and not crashed/hung?"* Without a heartbeat signal the user has no way to distinguish a slow stage from a dead process, so they either wait too long or kill a healthy run. Every other observability concern depends on first having a reliable heartbeat.

**Independent Test**: Start `notetaker run <url>` in one terminal. From a second terminal, locate and tail the run's log file. Verify that the file exists, that the file's most recent line names the current stage, and that a new line appears at a predictable cadence as long as the pipeline is healthy. Kill the pipeline mid-stage and confirm the log file's last line clearly shows the last activity before death.

**Acceptance Scenarios**:

1. **Given** notetaker has been running for 10 minutes in capture stage, **When** the user tails the run's log file, **Then** the most recent line is timestamped within the last heartbeat interval and identifies the active stage as `capture`.
2. **Given** notetaker has just transitioned from `extract` to `understand`, **When** the user looks at the log file, **Then** there is a clearly marked stage-transition entry showing `extract` completed (with summary metrics) and `understand` started.
3. **Given** the pipeline is hung (e.g., the browser tab froze), **When** the user inspects the log file, **Then** no new lines have been written for substantially longer than the expected heartbeat interval, allowing the user to conclude the run is stuck.
4. **Given** the pipeline crashed with an exception during a stage, **When** the user opens the log file after the process exits, **Then** the file contains the failing stage, the operation in progress at the time, and the exception details.

---

### User Story 2 - Find the log without hunting (Priority: P2)

The user should not have to remember an output path or grep through `/var` or scrollback to find the log. When a run starts, the path of the log file should be announced on the console; when a run is in flight, there should be a stable, discoverable way (e.g., a `latest` pointer or a single conventional directory) to reach the active log without first knowing the recording URL hash.

**Why this priority**: A log nobody can find is operationally worthless. This makes the P1 capability usable in practice — especially when the user comes back to a long-running terminal and wants to peek at progress quickly.

**Independent Test**: Start a run. Without copying any path from the original terminal, open a fresh shell and locate the log file for the active run using only the documented convention. Confirm the file is the right one for the in-flight invocation.

**Acceptance Scenarios**:

1. **Given** a run has just started, **When** the user looks at the console output, **Then** the absolute path of this run's log file is printed once, prominently, before the first interactive prompt.
2. **Given** a run is in flight, **When** the user follows the documented convention to locate the "latest run" log, **Then** they find the same file that is currently being written to.
3. **Given** several past runs, **When** the user lists the log directory, **Then** each log file's name encodes enough information (timestamp and recording identifier) to disambiguate runs without opening the file.

---

### User Story 3 - Reconstruct what happened after the fact (Priority: P3)

After a run completes (successfully or not) the user wants to revisit the log later — sometimes hours or days later — to understand timing, cost, OCR fallback events, parse errors, and other stage-level outcomes without re-running the pipeline.

**Why this priority**: This is a quality-of-life and debugging benefit, valuable but secondary to live status. The cache directory already preserves stage outputs; this feature ensures the *narrative* of how those outputs were produced is also preserved.

**Independent Test**: Run a pipeline to completion, wait until the next day, then open the saved log and verify it contains a per-stage start/end record, the durations of each stage, the costs reported by the understanding and synthesis stages, and any warnings (transcript unavailable, OCR fallback, JSON parse errors).

**Acceptance Scenarios**:

1. **Given** a completed run, **When** the user reads the log file, **Then** they see one start-of-stage and one end-of-stage record per stage, each annotated with the stage's headline metric (frames captured, slides detected, vision/OCR counts, cost, summary path).
2. **Given** a completed run that hit the budget ceiling and fell back to OCR, **When** the user reads the log file, **Then** the fallback event and the slide(s) it affected are clearly recorded.
3. **Given** a run that completed but the log directory has filled up over many runs, **When** retention policy applies, **Then** the user can find all logs younger than the retention window and old logs have been purged.

---

### Edge Cases

- **Hang detection ambiguity**: A genuinely slow stage (e.g., a 60-minute capture) must still emit heartbeats so it is not mistaken for a hang. Heartbeat cadence must be tight enough that the worst-case "no news" window is shorter than what a user would tolerate before assuming the worst.
- **Interactive prompts**: Capture stage blocks twice on `input()` ("Press Enter when playback has started…" / "…complete"). The system must continue to write a heartbeat (or a clearly-labelled "waiting for user input" state) during these waits, so the user does not interpret the deliberate pause as a hang.
- **Disk-full / unwritable log location**: If the log file cannot be opened, the run must still proceed and emit progress to the existing console stream rather than aborting silently.
- **Concurrent runs**: Two notetaker runs started in parallel must not write to the same log file. Each invocation gets its own file.
- **Very long captures**: A 2-hour recording capturing one frame per second with periodic heartbeats must not produce a log file so large it becomes unusable. The volume of log lines per stage must be bounded by a sampling/throttling rule, not by the duration of the input.
- **Crash mid-write**: If the process is killed (SIGKILL, OOM, power loss), the log on disk must still contain everything written up to the last flush — the file must not buffer indefinitely in memory.
- **Existing `--debug` flag**: Debug mode already raises log verbosity. Logfile output must compose cleanly with `--debug`: more detail goes to the file, but the heartbeat / stage-transition markers remain at the same prominent level so they are not lost in a flood of debug lines.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST write a per-invocation log file to a stable, discoverable location for every CLI invocation that performs pipeline work (capture, extract, understand, synthesise, run).
- **FR-002**: System MUST print the absolute path of the log file to the console at the start of each invocation, before any interactive prompt or long-running work begins.
- **FR-003**: System MUST emit a clearly-marked stage-start record when entering each pipeline stage, including the stage name and the cache directory the stage will read from / write to.
- **FR-004**: System MUST emit a clearly-marked stage-end record when leaving each pipeline stage, including the stage name, elapsed wall-clock duration, and the headline metric(s) for that stage (e.g., frames captured, unique slides detected, vision/OCR counts, total cost, summary output path).
- **FR-005**: System MUST emit a heartbeat record at a bounded, predictable interval throughout every long-running stage (capture, understand, synthesise) so that the absence of new records for substantially longer than the interval is a reliable signal of a hung or crashed run.
- **FR-006**: System MUST treat blocking on user input (e.g., "Press Enter when playback has started/complete") as a distinct, named state in the log so that users do not interpret an intentional pause as a hang.
- **FR-007**: System MUST flush log records to disk promptly after they are emitted, so that a process killed mid-stage still leaves the most recent activity on disk for post-mortem inspection.
- **FR-008**: System MUST capture unhandled exceptions and write them to the log file, including the active stage and the operation in progress, before propagating or exiting.
- **FR-009**: System MUST provide a stable convention for locating the "most recent run" log file without prior knowledge of the recording URL or invocation timestamp (for example, a `latest` symlink, or a single well-known directory listed by recency).
- **FR-010**: System MUST encode the recording identifier and the invocation timestamp in each log file's name or metadata, so runs are disambiguable without opening the files.
- **FR-011**: System MUST preserve the existing console output behaviour — including interactive prompts, the existing structured-log console stream, and final summary lines — so the addition of file logging does not regress the in-terminal experience.
- **FR-012**: System MUST continue the run if the log file cannot be created or written (degraded mode), surfacing a single console warning rather than aborting the pipeline.
- **FR-013**: System MUST bound the size of any single run's log file by throttling repetitive heartbeat detail, so that a multi-hour capture does not produce a log file disproportionate to the work performed.
- **FR-014**: System MUST apply a retention policy to old log files consistent with the existing cache retention behaviour, so the log directory does not grow without bound.
- **FR-015**: When the user passes the existing `--debug` flag, the system MUST increase the verbosity of records written to the log file. Stage-transition and heartbeat records MUST carry a closed-set categorical field whose value identifies the record's role (e.g. `stage_start`, `stage_end`, `heartbeat`), so a single one-line filter (`grep` / `jq` / equivalent) extracts them from the file unaltered regardless of the surrounding debug volume.
- **FR-016**: System MUST write log records in a format that is both human-readable when opened in a plain text viewer (e.g., `tail -f`) and unambiguous about each record's stage, timestamp, and event type.

### Key Entities *(include if feature involves data)*

- **Run log file**: A single text file representing one invocation of a notetaker CLI command. Identified by recording URL hash and invocation timestamp. Contains an ordered sequence of records covering stage transitions, heartbeats, stage-level metrics, warnings, and any unhandled errors. Bounded in size by throttling rules; subject to retention.
- **Log record**: A single, time-stamped line within a run log file. Has a category (stage_start, stage_end, heartbeat, waiting_for_input, warning, error, etc.), a stage tag (capture / extract / understand / synthesise), and a free-text message plus structured key/value metadata.
- **Latest-run pointer**: A stable, well-known filesystem path that always resolves to the log file of the most recently started run, so a user opening a fresh terminal can reach the active log without knowing the recording URL.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user looking at the most recent line of the active run's log file can identify the current pipeline stage and the most recent activity within 5 seconds, without referring to source code or the original terminal.
- **SC-002**: During any long-running stage, the gap between consecutive log records is no longer than 30 seconds while the pipeline is healthy, so a user observing 60+ seconds of silence can confidently classify the run as hung.
- **SC-003**: 100% of `notetaker run` invocations that crash mid-pipeline leave a log file on disk whose final records identify the stage, the in-progress operation, and (where applicable) the exception.
- **SC-004**: A user opening a fresh terminal can locate the active run's log file using only the documented convention in under 10 seconds, without any path being copied from the original terminal.
- **SC-005**: For a representative full-length capture (60-minute meeting at the default 1-frame-per-second sample rate), the run log file remains under 5 MB.
- **SC-006**: After a completed run, every stage has exactly one stage-start and one stage-end record in the log, and the stage-end record carries the same headline metrics that the stage prints to the console summary.
- **SC-007**: When the log file cannot be created (e.g., target directory not writable), the pipeline still completes successfully and the user sees exactly one warning explaining the degraded state.

## Assumptions

- The existing structured logger (structlog, configured in `src/notetaker/utils/logging.py`) is the natural foundation for this feature; this spec describes the user-visible behaviour the logging layer must deliver, not which library to use.
- The existing console stream (currently `stderr`) and the new run log file are independent sinks. The new feature adds the file sink without removing or reformatting the console sink.
- A reasonable default location for run log files is alongside the existing cache directory (`~/.local/share/notetaker/`), so log retention can mirror the existing 30-day cache retention policy, and a user inspecting `~/.local/share/notetaker/` finds both artifacts and logs in one place.
- The heartbeat cadence target of "no more than 30 seconds between log lines" aligns with the existing `capture.progress` event, which already fires every 30 frames at the default 1-frame-per-second sample rate.
- The log file format may be JSON-per-line (machine-parseable) or plain key=value lines, as long as it remains human-readable in `tail -f`. The choice between formats is an implementation detail and out of scope for this spec.
- The user runs notetaker interactively from one terminal at a time and expects to peek at progress from a second terminal. Concurrent same-machine runs are supported by per-invocation log files but are not the primary use case.
- Live remote monitoring (shipping logs to a server, dashboards, alerting) is out of scope; "knowing what notetaker is doing" means inspecting a local file, not external observability.
