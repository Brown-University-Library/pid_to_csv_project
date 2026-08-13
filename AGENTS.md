# AGENTS.md — Repository Agent Instructions (Source of Truth)

This file defines the canonical coding directives for this repository.

If other instruction files exist (Copilot, IDE rules, contributor docs) and conflict with this file, follow this file and treat the others as stale.

## Table of contents

- [Project basics](#project-basics)
- [How to run code](#how-to-run-code)
- [Coding directives (Python)](#coding-directives-python)
- [Django architecture conventions](#django-architecture-conventions)
- [Front-end change guidance](#front-end-change-guidance)
- [Tests](#tests)
- [Change workflow expectations](#change-workflow-expectations)
- [If instructions are missing or ambiguous](#if-instructions-are-missing-or-ambiguous)
- [Agent project index](#agent-project-index)

## Project basics

- Primary language: Python
- Target runtime: Python 3.12 -- unless a `pyproject.toml` specifies a different version
- Dependency / execution tool: `uv`
- Project-root is the directory containing this file (and `.git/`, and `.gitignore`).

## How to run code

- Assume user is in the project-root directory.
- Do not use `python` to run scripts.
- Run a script via: `uv run ./path_to_script.py --help`
- Run tests via:
    - `uv run ./run_tests.py`
        - Note that `run_tests.py` has usage instructions about how to run more granular tests.
- Run django management scripts via: `uv run ./manage.py THE-COMMAND`

## Coding directives (Python)

### Type hints and imports

- Use Python 3.12 type hints everywhere (functions and important variables). (Unless a `pyproject.toml` specifies a different version.)
- Prefer builtin generics (e.g., `list[str]`, `dict[str, int]`) over `typing.List` / `typing.Dict`.
- Prefer PEP 604 unions (e.g., `str | None`) over `Optional[str]`.
- Avoid `typing` and `annotations` imports unless strictly necessary.

### Script structure

- Structure runnable modules as:
  - `def main() -> None: ...`
  - `if __name__ == '__main__': main()`
- Keep `main()` simple: parse args / orchestrate calls only.
- Put real logic into top-level helper functions and modules (no nested function definitions).
- Rarely use more than three levels of hierarchy: main() can call helper_A() which can call helper(B) which can, if necessary, can call helper(C) -- but that's it.

### Functions and control flow

- Prefer single-return functions (use local variables and a final return).
- Do not define functions inside other functions.
- Favor clarity and explicitness over cleverness.

### Logging

- When adding a log statement, when possible, format variable values as a label, followed by a comma and a space, with the value enclosed in double backticks.
- Prefer a label that matches the variable name. For example: ```log.debug(f'branch_and_commit, ``{branch_and_commit}``')```

### HTTP and networking

- Use `httpx` for all HTTP calls.
- Do not introduce alternate HTTP libraries (e.g., `requests`, `aiohttp`) unless the repository already depends on them and there is a documented reason.

### Docstrings

- Use triple-quoted docstrings.
- Write docstrings in present tense, with triple-quotes on their own lines.
  - Good:
    ```
    """
    Parses ...
    """
    ```
  - Avoid: `"""Parse ..."""`
- The last line of non-test function-docstrings should be: `Called by: the_caller_function()` (or, if in another class/module, `Called by: module.Class.the_caller_function()`)
- Start test-function docstring-text with "Checks..."
- For header-comments, in functions, start the comment with two hashes (e.g., `## does this`).

### Additional coding directives

- Inspect the `/ruff.toml` for additional coding directives, such as `max-line-length` and `quote-style`.

### Markdown formatting

- Do not use hard line-breaks in markdown files; let paragraphs wrap naturally.
- When creating a Markdown file with more than three top-level `##` headings, add a table of contents near the top with links to those `##` headings.

## Django architecture conventions

This is currently a standalone script, not a Django application. Apply the following conventions only if Django code is introduced.

### View-layer responsibilities

- `project/app/views.py` should contain **only** view functions that directly handle URL endpoints.
- Every view function in `project/app/views.py` should correspond to an entry in `project/config/urls.py`.
- Views should act as **manager/orchestrator** functions:
  - Parse request input (query params, POST body, files)
  - Perform minimal validation and shaping of inputs
  - Delegate substantive work to modules under `project/app/lib/`
  - Convert returned results into the appropriate `HttpResponse` (HTML, JSON, redirects)

### Business logic placement

- Put domain logic, integrations, and reusable operations in `project/app/lib/` (not in `views.py`).
- If multiple endpoints share logic, move that shared logic into `project/app/lib/` and keep each view thin.
- Prefer pure, testable functions in `project/app/lib/` that accept plain Python values (not Django request objects) unless passing the request is necessary for a narrow, well-justified reason.

### Imports and dependencies

- `views.py` should primarily import:
  - Django primitives (`HttpRequest`, `HttpResponse`, `render`, `redirect`, etc.)
  - The minimal set of functions/classes from `project/app/lib/` needed for each endpoint
- Avoid creating a secondary abstraction layer inside `views.py` (no view-helper utilities); place helpers in `project/app/lib/`.

## Front-end change guidance

- When front-end changes are required, use JavaScript only where it is truly required.
- Prefer updates in CSS, Python code, or Django template code when those can satisfy the behavior or presentation need.

## Tests

- Use the standard library `unittest` framework (not pytest) for non-Django projects.
- Use Django's test framework for Django projects.
- New behavior should usually come with a focused test covering:
  - the happy path
  - at least one failure / edge case

## Change workflow expectations

When implementing a change (especially from an issue/task):

1. Read relevant surrounding code and match existing conventions.
2. Make the smallest correct change that satisfies the request.
3. Update tests and run: `uv run ./run_tests.py`
4. If you cannot run tests in your environment, still write/adjust tests and state what you would run.

### Commit messages

- Group related files into logical, focused commits; do not require a separate commit for every file.
- Keep each commit message brief, with no more than ten words.
- Write messages in the present tense so they complete the phrase "This commit..." Begin with a fitting verb such as "Adds," "Implements," or "Updates."

## If instructions are missing or ambiguous

- Do not ask questions unless absolutely necessary to proceed.
- Make reasonable assumptions, state them explicitly, then implement.
- If blocked, provide:
  - what you tried
  - what you found in the repo
  - a concrete next step (command, file to edit, or minimal decision needed)

## Agent project index

### Orientation and file map

- `main.py` contains argument parsing and the top-level `main()` manager only. Keep helper functions out of this file. Start at `main()`, then follow `lib.csv_creator.create_csv()` for CSV behavior.
- `lib/cli_values.py` validates and normalizes command-line values. `lib/data_types.py` contains shared exceptions and dataclasses. `lib/terminal.py` displays the optional terminal notices.
- `lib/bdr_api.py` owns cookie-file parsing, HTTP-client setup, JSON validation, collection and search requests, paging, Solr query construction, and direct-part lookup.
- `lib/csv_creator.py` owns collection traversal, reason creation, row uniqueness and ordering, CSV writing, and the `create_csv()` manager called by `main.py`.
- `README.md` is the user-facing behavior reference. Keep its command examples, flag descriptions, CSV reason formats, and terminal-output examples synchronized with code changes.
- `pyproject.toml` fixes the runtime to Python 3.12 and declares `httpx` as the only runtime dependency. `uv.lock` records the resolved dependencies. `ruff.toml` sets a 125-character line length, Python 3.12 syntax, four-space indentation, and single quotes.
- `run_tests.py` runs the `unittest` suite and accepts an optional module, class, or method path. Tests are in `tests/test.py`; API tests mock `lib.bdr_api.httpx.Client` and use temporary directories for CSV output.
- This repository has no Django or front-end code. The generic sections above remain for consistency with the source instruction template but do not describe the current application.

### Command modes and CSV behavior

- `--api-root`, `--pid`, and `--output` are always required. API roots are stripped of whitespace and all trailing slashes before URLs are built.
- With neither collection flag, the output contains the submitted PID and `--reason`, which defaults to `unknown`. CSV headers are omitted unless `--include-headers` is present.
- `--grab-all-collection-items` validates `--pid` as a collection and includes its directly assigned members. It records encountered sub-collections but deliberately does not process their contents.
- `--comprehensive` also validates `--pid` as a collection and takes the place of `--grab-all-collection-items`. It processes descendant sub-collections breadth-first. Scheduled and visited PID sets prevent cycles and repeated requests; the first hierarchy found for a PID wins.
- The root collection reason is `<name> collection`. Descendant collections use `collection-member of <hierarchy>`, ordinary items use `member of <hierarchy>`, and parts use `part of <parent PID>`.
- PID rows are unique. When a direct part was already found as a collection member, `add_direct_part_rows()` removes the earlier row and places it immediately after its parent with the part-specific reason. Do not weaken this ordering guarantee without updating the tests and README.
- `--include-all-has-parts` adds only the direct parts of the submitted PID or of primary items found in the selected collection scope. It does not process parts of parts. The application checks included parts once more and prints the PIDs whose deeper parts were intentionally omitted.
- In non-comprehensive collection mode, the terminal also lists sub-collection PIDs whose contents were intentionally not processed. Comprehensive mode follows those collections instead and therefore does not produce that notice for successfully processed descendants.

### BDR API integration

- Collection validation and naming use `GET <api-root>/collections/<encoded-pid>/`. Member and part discovery use the Shibboleth-aware `GET <api-root>/search/` endpoint.
- Collection members are selected through `rel_is_member_of_collection_ssim`; parts are selected through `rel_is_part_of_ssim`; `object_type:bdr-collection` is represented in results by `object_type == 'bdr-collection'`.
- Search requests use `rows=500`, `start` paging, and `sort=pid asc`. The adjacent BDR API checkout caps one search response at 500 rows, so retain paging whenever searches can return a whole collection or a batched set of parts.
- Queries intentionally begin with `display:*`. In the adjacent BDR API's `search_app/models.py`, the presence of `display:` switches the mandatory permission filter from discover access to display access. This allows displayable parts that are not independently discoverable while still restricting results to the identities supplied by the current Shibboleth session.
- Part-parent queries are batched in groups of 50 to keep generated Solr query strings manageable. Solr phrase values must continue to escape backslashes and quotation marks.
- `--cookie-file` accepts one browser `Cookie` request-header value, optionally prefixed by `Cookie:`. `create_http_client()` converts it to host-scoped cookies and requires an HTTPS API host. Redirects may be followed, but the cookies must never be sent to a different host.
- A Studio browser session can expand the Shibboleth identities seen by the collection and search endpoints. A `403` with supplied cookies should advise refreshing the browser session; a `403` without cookies should mention `--cookie-file`.

### Tests and change guidance

- `lib.csv_creator.create_csv()` is the main behavior boundary for tests: it accepts ordinary Python values, creates its own shared client where needed, writes the file, and returns counts and terminal-notice PIDs in `CsvCreationResult`.
- Mocked collection-tree tests depend on the order of `client.get()` responses: each collection name request is followed by its member search, then optional direct-part and deeper-part searches occur after collection expansion. Update response sequences and call-count assertions when adding API requests.
- Preserve coverage for headerless and headed output, custom reasons, paging, hierarchy and cycle handling, collection-versus-item reason prefixes, direct-part ordering, deeper-part notices, skipped-subcollection notices, cookie parsing and host scoping, safe `403` messages, and invalid collection PIDs.
- Live development hosts can require Brown VPN access and a current Studio login. Do not make a live request a prerequisite for the local test suite; use mocked HTTP responses for repeatable tests.

### Sensitive data

- Treat cookie files as temporary passwords. Never log cookie names or values, include real cookie content in fixtures or documentation, or commit cookie files, generated CSV reports, outer `.env` values, logs, or deployment notes.

---
