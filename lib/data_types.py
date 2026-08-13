"""
Defines shared application data types and user-facing errors.

The immutable dataclasses carry collection-search results, CSV completion
details, and collection-expansion state between implementation modules.
"""

from dataclasses import dataclass


class PidToCsvError(RuntimeError):
    """
    Identifies an error that can be shown directly to the command-line user.
    """


@dataclass(frozen=True)
class CollectionMember:
    """
    Stores the fields needed to distinguish primary items, parts, and sub-collections.
    """

    pid: str
    object_type: str | None
    parent_pids: tuple[str, ...]


@dataclass(frozen=True)
class CsvCreationResult:
    """
    Stores the CSV row count and PIDs that require a terminal notice.
    """

    row_count: int
    pids_with_unincluded_parts: tuple[str, ...] = ()
    skipped_subcollection_pids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CollectionExpansion:
    """
    Stores collection-tree rows and the PIDs needed for optional part processing.
    """

    rows: list[dict[str, str]]
    primary_item_pids: list[str]
    collection_pids: set[str]
    skipped_subcollection_pids: tuple[str, ...]
