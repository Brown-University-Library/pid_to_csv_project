# PID to CSV

Script to create a CSV of pids.

- [Overview](#overview)
- [Setup](#setup)
- [Use cases and command examples](#use-cases-and-command-examples)
    - [Append one PID to an existing sheet](#append-one-pid-to-an-existing-sheet)
    - [Create a CSV for a new sheet](#create-a-csv-for-a-new-sheet)
    - [Include a compound item's direct parts](#include-a-compound-items-direct-parts)
    - [Include a collection's directly assigned members](#include-a-collections-directly-assigned-members)
    - [Include collection members and their direct parts](#include-collection-members-and-their-direct-parts)
    - [Include an entire collection tree](#include-an-entire-collection-tree)
    - [Access content available after a Studio login](#access-content-available-after-a-studio-login)
    - [Expected terminal notices](#expected-terminal-notices)

## Overview

Creates a UTF-8 CSV with the columns `PID` and `Reason`, ready to upload to Google Sheets and append to an existing sheet.

Uses the BDR APIs, when needed -- to get items from a collection, sub-collections, and parts-references.

Motivation: we needed to populate a spreadsheet with PIDS of dev-items we don't want deleted during a migration.

All necessary data is passed in via flags; no envars or dot-env are needed.


## Setup

```bash
mkdir ./pid_to_csv_project_stuff
cd ./pid_to_csv_project_stuff
git clone git@github.com:Brown-University-Library/pid_to_csv_project.git
cd ./pid_to_csv_project
uv sync
uv run ./run_tests.py
```


## Use cases and command examples

Every command requires `--api-root`, `--pid`, and `--output`. The API root may be supplied with or without a trailing slash; the script normalizes it before constructing request URLs.

| Situation | Extra flag or flags | Result |
| --- | --- | --- |
| Append one PID to a sheet that already has headings | None | One headerless row with reason `unknown` |
| Explain why a PID is being added | `--reason` | One headerless row with the supplied reason |
| Create a CSV for a new or empty sheet | `--include-headers` | Adds `PID,Reason` before the data rows |
| Add a compound item such as a book together with its pages or files | `--include-all-has-parts` | Adds the submitted PID and each of its direct parts |
| Add everything directly assigned to one collection | `--grab-all-collection-items` | Adds the collection PID and its directly assigned member PIDs |
| Add a collection's primary items and their direct parts | `--grab-all-collection-items --include-all-has-parts` | Adds collection members and direct parts without following deeper part or sub-collection trees |
| Add an entire collection tree | `--comprehensive` | Validates the submitted PID as a collection and adds all descendant sub-collections and their direct members |
| Add an entire collection tree and each primary item's parts | `--comprehensive --include-all-has-parts` | Adds the complete collection tree plus direct parts throughout that tree |
| Access a PID that is available only after a Studio login | `--cookie-file` | Reuses an authenticated browser session for API requests |

`--include-headers` can be combined with any of the other situations. Without it, the first line contains data and can be appended directly to a sheet that already has headings.

### Append one PID to an existing sheet

Use the simplest form when the destination sheet already has its `PID` and `Reason` headings. The resulting CSV contains one row with the default reason, `unknown`:

```bash
uv run ./main.py \
    --api-root 'https://the.domain.edu/api/' \
    --pid 'test:123456' \
    --output '../pids.csv'
```

When the purpose of the row is known, record it with `--reason` instead of accepting `unknown`:

```bash
uv run ./main.py \
    --api-root 'https://the.domain.edu/api/' \
    --pid 'test:123456' \
    --reason 'needs review' \
    --output '../pids.csv'
```

### Create a CSV for a new sheet

Use `--include-headers` when the CSV will supply the sheet's first rows rather than being appended below existing headings:

```bash
uv run ./main.py \
    --api-root 'https://the.domain.edu/api/' \
    --pid 'test:123456' \
    --output '../pids.csv' \
    --include-headers
```

### Include a compound item's direct parts

Use `--include-all-has-parts` when the submitted PID represents an item whose directly attached pages, files, or other parts should accompany it:

```bash
uv run ./main.py \
    --api-root 'https://the.domain.edu/api/' \
    --pid 'test:123456' \
    --output '../pids-and-parts.csv' \
    --include-all-has-parts
```

Each direct part receives the reason `part of <submitted PID>`. Part rows are placed immediately after the referenced parent whenever that parent is present in the report, including when the part was encountered earlier as a collection member. Part lookup includes records that are publicly displayable through the item API even when they are not independently discoverable in normal search results. The script deliberately does not add parts of parts. It checks whether an included direct part has parts of its own and reports that direct-part PID in the terminal.

### Include a collection's directly assigned members

Use `--grab-all-collection-items` when the submitted PID is a public collection and every PID directly assigned to that collection should be added:

```bash
uv run ./main.py \
    --api-root 'https://the.domain.edu/api/' \
    --pid 'test:123456' \
    --output '../collection-pids.csv' \
    --grab-all-collection-items
```

Collection mode verifies the PID through the BDR collection API, gets the collection name, and follows every page from the BDR search API. The submitted collection PID is written first with the reason `<collection name> collection`. Ordinary member PIDs use `member of <collection name> collection`; sub-collection PIDs use `collection-member of <collection name> collection`, making them distinguishable from top-level items. If `--reason` is also supplied, collection mode ignores it.

### Include collection members and their direct parts

Combine the two expansion flags when the CSV should contain a collection's primary items and their directly attached parts:

```bash
uv run ./main.py \
    --api-root 'https://the.domain.edu/api/' \
    --pid 'test:123456' \
    --output '../collection-pids-and-parts.csv' \
    --grab-all-collection-items \
    --include-all-has-parts
```

Collection members that are already parts are included but are not treated as primary items to process again. If a direct part is already present among the collection members, it appears only once and its reason becomes `part of <primary-item PID>`.

Sub-collection PIDs remain in the CSV, but their members are not added. This keeps the operation limited to the submitted collection instead of unexpectedly expanding every collection nested beneath it.

### Include an entire collection tree

Use `--comprehensive` when the submitted PID is the top-level collection and the CSV should include every descendant sub-collection and the items directly assigned at every level. This flag takes the place of `--grab-all-collection-items` and confirms that `--pid` is a valid, accessible collection PID before proceeding:

```bash
uv run ./main.py \
    --api-root 'https://host.services.brown.edu/api/' \
    --pid 'test:123456' \
    --output '../pids.csv' \
    --include-all-has-parts \
    --cookie-file '/path/to/temp_cookie.txt' \
    --comprehensive
```

The flag is spelled `--comprehensive`, with no space between the two hyphens and the word.

Collection and item reasons show the first hierarchy found from the submitted collection. Given a root named `Archives`, a child named `Photographs`, and a grandchild named `Events`, examples are:

```csv
test:root,Archives collection
test:photo-collection,collection-member of Archives collection > Photographs collection
test:event-collection,collection-member of Archives collection > Photographs collection > Events collection
test:item,member of Archives collection > Photographs collection > Events collection
test:part,part of test:item
```

Traversal uses an internal set of collection PIDs. Each collection PID is processed at most once, even if relationships contain a cycle or the same sub-collection is reachable through multiple parents. If a collection or item PID is reachable through multiple routes, the first hierarchy encountered is retained. Descendant collection rows start with `collection-member of`; ordinary item rows start with `member of`. Direct parts continue to use the specific reason `part of <item PID>` and are positioned directly after that item when possible.

### Access content available after a Studio login

Some collection or item URLs may return more information after a Studio/Shibboleth login. Use `--cookie-file` to reuse that authenticated browser session. Do not put your Brown username, password, or the cookie value directly in the command.

First, obtain the cookie from the browser:

1. Log into the appropriate Studio site normally.
2. Open the collection or item API URL in the same browser session and confirm it displays the restricted information.
3. Open the browser's developer tools, select the API request in the Network panel, and copy the value of its `Cookie` request header. Copy the request header, not a `Set-Cookie` response header.
4. Save the value as a single line in a temporary file. The file may contain either `Cookie: name=value; ...` or only `name=value; ...`.

Then pass the file to the script:

```bash
uv run ./main.py \
    --api-root 'https://dlibbdrwwwcit.services.brown.edu/api/' \
    --pid 'test:123456' \
    --output '../pids.csv' \
    --grab-all-collection-items \
    --include-all-has-parts \
    --cookie-file '/tmp/bdr-api-cookie'
```

For a restricted top-level collection whose complete sub-collection tree is wanted, replace `--grab-all-collection-items` with `--comprehensive`.

The script restricts these cookies to the HTTPS host in `--api-root`; they are not sent to a different login host if a request redirects. It never prints cookie names or values. If the server returns `403`, the terminal explains that the session may have expired or may not grant access. Log into Studio again, replace the cookie file's contents, and retry.

Treat the cookie file as a temporary password: do not commit, share, or keep it after use. Remove `/tmp/bdr-api-cookie` when finished. VPN access is still required for hosts that are available only on the Brown network.

### Expected terminal notices

If an included direct part has parts of its own, those deeper parts are not added. The terminal identifies the included direct-part PID where processing stopped. For example:

```text
PIDs with parts that were not included because only direct parts are added:
  test:part1
  test:part2
```

In this example, `test:part1` and `test:part2` are present in the CSV, but their parts are not.

If collection processing encounters sub-collections, their PIDs remain in the CSV but their contents are not processed. The terminal identifies them like this:

```text
Sub-collection PIDs whose contents were not processed:
  test:subcollection1
  test:subcollection2
```

If both situations occur, both notice blocks are displayed. If neither occurs, these blocks are omitted. The normal completion message, including the output path and data-row count, is also logged to the terminal.

---
