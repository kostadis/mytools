---
name: mempalaceignore support lives on kostadis-dev branch
description: The kostadis-dev branch of mempalace is the version that understands .mempalaceignore files
type: project
originSessionId: 53c3cb7f-63a4-4a43-8962-e1a12ec1733a
---
The version of mempalace on branch `kostadis-dev` (at `/home/kroussos/src/mempalace/`) is the one that understands `.mempalaceignore` files. As of 2026-04-23, it was installed editable into `/home/kroussos/worldanvil_pipeline/venv` (version 3.3.2).

**Why:** Upstream MemPalace may not yet support `.mempalaceignore`; the user's fork branch carries this capability.

**How to apply:** When the user references `.mempalaceignore` behavior or wants to run mempalace with ignore-file support, ensure they are running the build from `/home/kroussos/src/mempalace/` (kostadis-dev) — not an upstream install. If running via `worldanvil_pipeline/venv`, the editable install already points at this tree.
