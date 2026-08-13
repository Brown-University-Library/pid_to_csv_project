"""
Builds ordered PID rows and writes them to CSV files.

The module manages single-PID output, collection-tree traversal, direct-part
placement, duplicate prevention, reasons, and optional column headers.
"""

import csv
from collections.abc import Iterable
from pathlib import Path

import httpx

from lib.bdr_api import collect_direct_parts, create_http_client, fetch_collection_members, fetch_collection_name
from lib.data_types import CollectionExpansion, CsvCreationResult, PidToCsvError

CSV_FIELDNAMES: tuple[str, ...] = ('PID', 'Reason')


def single_pid_rows(pid: str, reason: str) -> list[dict[str, str]]:
    """
    Builds the one CSV row used outside collection mode.
    Called by: create_csv()
    """
    rows = [{'PID': pid, 'Reason': reason}]
    return rows


def format_collection_hierarchy(collection_names: tuple[str, ...]) -> str:
    """
    Formats collection names from the submitted root through the immediate collection.
    Called by: expand_collection_tree()
    """
    hierarchy = ' > '.join(f'{collection_name} collection' for collection_name in collection_names)
    return hierarchy


def add_unique_row(
    rows: list[dict[str, str]],
    row_pids: set[str],
    pid: str,
    reason: str,
) -> bool:
    """
    Adds a PID row once and reports whether it was added.
    Called by: expand_collection_tree()
    """
    added = False
    if pid not in row_pids:
        rows.append({'PID': pid, 'Reason': reason})
        row_pids.add(pid)
        added = True
    return added


def expand_collection_tree(
    client: httpx.Client,
    api_root: str,
    root_collection_pid: str,
    comprehensive: bool,
) -> CollectionExpansion:
    """
    Validates the root collection and gathers either its direct members or its entire sub-collection tree.
    Called by: create_csv()
    """
    pending_collections: list[tuple[str, tuple[str, ...]]] = [(root_collection_pid, ())]
    scheduled_collection_pids = {root_collection_pid}
    visited_collection_pids: set[str] = set()
    skipped_subcollection_pids: list[str] = []
    rows: list[dict[str, str]] = []
    row_pids: set[str] = set()
    primary_item_pids: list[str] = []
    primary_item_pid_set: set[str] = set()

    while pending_collections:
        collection_pid, ancestor_names = pending_collections.pop(0)
        if collection_pid in visited_collection_pids:
            continue
        visited_collection_pids.add(collection_pid)

        collection_name = fetch_collection_name(client, api_root, collection_pid)
        collection_names = (*ancestor_names, collection_name)
        hierarchy = format_collection_hierarchy(collection_names)
        collection_reason = hierarchy if collection_pid == root_collection_pid else f'collection-member of {hierarchy}'
        add_unique_row(rows, row_pids, collection_pid, collection_reason)

        members = fetch_collection_members(client, api_root, collection_pid)
        for member in members:
            if member.object_type == 'bdr-collection':
                if comprehensive:
                    if member.pid not in scheduled_collection_pids:
                        pending_collections.append((member.pid, collection_names))
                        scheduled_collection_pids.add(member.pid)
                else:
                    add_unique_row(rows, row_pids, member.pid, f'collection-member of {hierarchy}')
                    if member.pid not in skipped_subcollection_pids:
                        skipped_subcollection_pids.append(member.pid)
            else:
                member_added = add_unique_row(rows, row_pids, member.pid, f'member of {hierarchy}')
                if member_added and not member.parent_pids and member.pid not in primary_item_pid_set:
                    primary_item_pids.append(member.pid)
                    primary_item_pid_set.add(member.pid)

        if not comprehensive:
            pending_collections.clear()

    expansion = CollectionExpansion(
        rows=rows,
        primary_item_pids=primary_item_pids,
        collection_pids=visited_collection_pids | set(skipped_subcollection_pids),
        skipped_subcollection_pids=tuple(skipped_subcollection_pids),
    )
    return expansion


def add_direct_part_rows(
    rows: list[dict[str, str]],
    direct_part_map: dict[str, list[str]],
    protected_pids: set[str],
) -> list[dict[str, str]]:
    """
    Places each direct part immediately after its parent and gives it the part-specific reason.
    Called by: create_csv()
    """
    assigned_part_pids: set[str] = set()
    part_rows_by_parent: dict[str, list[dict[str, str]]] = {}
    for parent_pid, part_pids in direct_part_map.items():
        for part_pid in part_pids:
            if part_pid in protected_pids or part_pid in assigned_part_pids:
                continue
            part_rows_by_parent.setdefault(parent_pid, []).append(
                {'PID': part_pid, 'Reason': f'part of {parent_pid}'},
            )
            assigned_part_pids.add(part_pid)

    rows_without_assigned_parts = [row for row in rows if row['PID'] not in assigned_part_pids]
    ordered_rows: list[dict[str, str]] = []
    placed_parent_pids: set[str] = set()
    for row in rows_without_assigned_parts:
        ordered_rows.append(row)
        if row['PID'] in part_rows_by_parent:
            ordered_rows.extend(part_rows_by_parent[row['PID']])
            placed_parent_pids.add(row['PID'])
    for parent_pid, part_rows in part_rows_by_parent.items():
        if parent_pid not in placed_parent_pids:
            ordered_rows.extend(part_rows)
    return ordered_rows


def write_csv(output_path: Path, rows: Iterable[dict[str, str]], include_headers: bool) -> int:
    """
    Writes rows as UTF-8, optionally adds headers, and returns the number of data rows.
    Called by: create_csv()
    """
    row_count = 0
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open('w', encoding='utf-8', newline='') as output_file:
            writer = csv.DictWriter(output_file, fieldnames=CSV_FIELDNAMES)
            if include_headers:
                writer.writeheader()
            for row in rows:
                writer.writerow(row)
                row_count += 1
    except OSError as error:
        raise PidToCsvError(f'Could not write CSV file {output_path}: {error}.') from error
    return row_count


def create_csv(
    api_root: str,
    pid: str,
    output_path: Path,
    reason: str,
    grab_all_collection_items: bool,
    include_headers: bool = False,
    include_all_has_parts: bool = False,
    cookie_values: dict[str, str] | None = None,
    comprehensive: bool = False,
) -> CsvCreationResult:
    """
    Selects the requested behavior, gathers any collection members, and writes the CSV.
    Called by: main.main()
    """
    pids_with_unincluded_parts: tuple[str, ...] = ()
    skipped_subcollection_pids: tuple[str, ...] = ()

    collection_mode = grab_all_collection_items or comprehensive
    if collection_mode:
        with create_http_client(api_root, cookie_values) as client:
            expansion = expand_collection_tree(client, api_root, pid, comprehensive)
            rows = expansion.rows
            skipped_subcollection_pids = expansion.skipped_subcollection_pids
            if include_all_has_parts:
                direct_part_map, pids_with_unincluded_parts = collect_direct_parts(
                    client,
                    api_root,
                    expansion.primary_item_pids,
                )
                rows = add_direct_part_rows(rows, direct_part_map, expansion.collection_pids)
    else:
        rows = single_pid_rows(pid, reason)
        if include_all_has_parts:
            with create_http_client(api_root, cookie_values) as client:
                direct_part_map, pids_with_unincluded_parts = collect_direct_parts(client, api_root, [pid])
            rows = add_direct_part_rows(rows, direct_part_map, {pid})

    row_count = write_csv(output_path, rows, include_headers)
    result = CsvCreationResult(row_count, pids_with_unincluded_parts, skipped_subcollection_pids)
    return result
