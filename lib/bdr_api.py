"""
Provides access to collection, search, and relationship data from the BDR API.

The module manages authenticated cookies, HTTP and JSON validation, paged
collection-member searches, and direct-part searches.
"""

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from lib.data_types import CollectionMember, PidToCsvError

SEARCH_PAGE_SIZE: int = 500
PART_PARENT_BATCH_SIZE: int = 50
REQUEST_TIMEOUT_SECONDS: float = 60.0
HTTP_HEADERS: dict[str, str] = {
    'Accept': 'application/json',
    'User-Agent': 'pid-to-csv/0.1',
}


def read_cookie_file(cookie_file: Path) -> dict[str, str]:
    """
    Loads browser cookies from a protected file without exposing their values in errors.
    Called by: main.main()
    """
    try:
        cookie_text = cookie_file.read_text(encoding='utf-8').strip()
    except OSError as error:
        raise PidToCsvError(f'Could not read cookie file {cookie_file}: {error.strerror or error}.') from error

    if cookie_text.lower().startswith('cookie:'):
        cookie_text = cookie_text.split(':', 1)[1].strip()
    if not cookie_text:
        raise PidToCsvError(f'Cookie file {cookie_file} is empty.')
    if '\n' in cookie_text or '\r' in cookie_text:
        raise PidToCsvError(f'Cookie file {cookie_file} must contain one Cookie header value on one line.')

    cookies: dict[str, str] = {}
    for cookie_pair in cookie_text.split(';'):
        cookie_pair = cookie_pair.strip()
        cookie_name, separator, cookie_value = cookie_pair.partition('=')
        if not separator or not cookie_name.strip():
            raise PidToCsvError(f'Cookie file {cookie_file} contains an invalid cookie pair.')
        cookies[cookie_name.strip()] = cookie_value.strip()
    return cookies


def create_http_client(api_root: str, cookie_values: dict[str, str] | None = None) -> httpx.Client:
    """
    Creates the shared BDR API client and limits supplied browser cookies to its HTTPS host.
    Called by: lib.csv_creator.create_csv()
    """
    parsed_api_root = urlparse(api_root)
    cookies = httpx.Cookies()
    if cookie_values:
        if parsed_api_root.scheme != 'https' or not parsed_api_root.hostname:
            raise PidToCsvError('--cookie-file requires an --api-root containing a valid HTTPS host.')
        for cookie_name, cookie_value in cookie_values.items():
            cookies.set(cookie_name, cookie_value, domain=parsed_api_root.hostname, path='/')

    client = httpx.Client(
        headers=HTTP_HEADERS,
        cookies=cookies,
        follow_redirects=True,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return client


def get_json(
    client: httpx.Client,
    url: str,
    params: dict[str, str],
    request_description: str,
) -> dict[str, object]:
    """
    Requests and validates one JSON object from the BDR API.
    Called by: fetch_collection_name(), fetch_search_docs()
    """
    try:
        response = client.get(url, params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        status_code = error.response.status_code
        error_message = f'{request_description} failed with HTTP status {status_code}.'
        if status_code == 403:
            if client.cookies.jar:
                error_message = (
                    f'{error_message} The browser session cookie may be expired or may not grant access. '
                    'Log in again and refresh --cookie-file.'
                )
            else:
                error_message = f'{error_message} If this PID requires login, supply an authenticated browser session with --cookie-file.'
        raise PidToCsvError(error_message) from error
    except httpx.RequestError as error:
        raise PidToCsvError(f'{request_description} failed: {error}.') from error

    try:
        data = response.json()
    except ValueError as error:
        raise PidToCsvError(f'{request_description} returned invalid JSON.') from error
    if not isinstance(data, dict):
        raise PidToCsvError(f'{request_description} returned an unexpected JSON value.')
    return data


def fetch_collection_name(client: httpx.Client, api_root: str, collection_pid: str) -> str:
    """
    Verifies an accessible collection PID and retrieves its display name.
    Called by: lib.csv_creator.expand_collection_tree()
    """
    encoded_pid = quote(collection_pid, safe=':._-')
    url = f'{api_root}/collections/{encoded_pid}/'
    params = {'q': '*', 'fl': 'pid', 'rows': '0'}
    data = get_json(client, url, params, f'Collection lookup for {collection_pid}')
    collection_name = data.get('name')
    if not isinstance(collection_name, str) or not collection_name.strip():
        raise PidToCsvError(f'Collection {collection_pid} has no usable name in its API response.')
    return collection_name.strip()


def escape_solr_phrase(value: str) -> str:
    """
    Escapes backslashes and quotation marks inside a quoted Solr phrase.
    Called by: build_part_query(), fetch_collection_members()
    """
    escaped_value = value.replace('\\', '\\\\').replace('"', '\\"')
    return escaped_value


def fetch_search_docs(
    client: httpx.Client,
    api_root: str,
    query: str,
    fields: str,
    request_description: str,
) -> list[dict[str, object]]:
    """
    Retrieves and validates every page of documents for one accessible BDR search.
    Called by: fetch_collection_members(), fetch_direct_part_map()
    """
    url = f'{api_root}/search/'
    all_docs: list[dict[str, object]] = []
    start = 0
    done = False

    while not done:
        params = {
            'q': query,
            'fl': fields,
            'rows': str(SEARCH_PAGE_SIZE),
            'start': str(start),
            'sort': 'pid asc',
        }
        data = get_json(client, url, params, f'{request_description} at row {start}')
        response_data = data.get('response')
        if not isinstance(response_data, dict):
            raise PidToCsvError(f'{request_description} has no response object.')

        num_found = response_data.get('numFound')
        docs = response_data.get('docs')
        if not isinstance(num_found, int) or not isinstance(docs, list):
            raise PidToCsvError(f'{request_description} is missing numFound or docs.')

        page_docs: list[dict[str, object]] = []
        for doc in docs:
            if not isinstance(doc, dict):
                raise PidToCsvError(f'{request_description} contains a result that is not an object.')
            page_docs.append(doc)

        all_docs.extend(page_docs)
        if len(all_docs) >= num_found:
            done = True
        elif not page_docs:
            raise PidToCsvError(
                f'{request_description} reported {num_found} results but stopped after {len(all_docs)}.',
            )
        else:
            start = start + len(page_docs)

    return all_docs


def get_parent_pids(doc: dict[str, object], request_description: str) -> tuple[str, ...]:
    """
    Validates and returns an item's is-part-of PIDs from a BDR search result.
    Called by: fetch_collection_members(), fetch_direct_part_map()
    """
    parent_data = doc.get('rel_is_part_of_ssim', [])
    if not isinstance(parent_data, list) or not all(isinstance(parent_pid, str) for parent_pid in parent_data):
        raise PidToCsvError(f'{request_description} contains an invalid rel_is_part_of_ssim value.')
    parent_pids = tuple(parent_data)
    return parent_pids


def fetch_collection_members(client: httpx.Client, api_root: str, collection_pid: str) -> list[CollectionMember]:
    """
    Retrieves every accessible PID directly assigned to a collection, following all result pages.
    Called by: lib.csv_creator.expand_collection_tree()
    """
    escaped_pid = escape_solr_phrase(collection_pid)
    query = f'display:* AND rel_is_member_of_collection_ssim:"{escaped_pid}"'
    request_description = f'Collection-member lookup for {collection_pid}'
    docs = fetch_search_docs(
        client,
        api_root,
        query,
        'pid,object_type,rel_is_part_of_ssim',
        request_description,
    )
    members: list[CollectionMember] = []
    for doc in docs:
        member_pid = doc.get('pid')
        object_type = doc.get('object_type')
        if not isinstance(member_pid, str):
            raise PidToCsvError('A collection-member result is missing its PID.')
        if object_type is not None and not isinstance(object_type, str):
            raise PidToCsvError(f'Collection member {member_pid} has an invalid object_type value.')
        parent_pids = get_parent_pids(doc, request_description)
        members.append(CollectionMember(member_pid, object_type, parent_pids))

    return members


def batched_pids(pids: list[str]) -> Iterator[list[str]]:
    """
    Splits parent PIDs into request-sized groups.
    Called by: fetch_direct_part_map()
    """
    start = 0
    while start < len(pids):
        yield pids[start : start + PART_PARENT_BATCH_SIZE]
        start = start + PART_PARENT_BATCH_SIZE


def build_part_query(parent_pids: list[str]) -> str:
    """
    Builds a Solr query matching accessible displayable parts whose parent is any supplied PID.
    Called by: fetch_direct_part_map()
    """
    quoted_pids = [f'"{escape_solr_phrase(parent_pid)}"' for parent_pid in parent_pids]
    query = f'display:* AND rel_is_part_of_ssim:({" OR ".join(quoted_pids)})'
    return query


def fetch_direct_part_map(client: httpx.Client, api_root: str, parent_pids: list[str]) -> dict[str, list[str]]:
    """
    Retrieves direct part PIDs for each supplied parent PID using batched, paged searches.
    Called by: collect_direct_parts()
    """
    unique_parent_pids = list(dict.fromkeys(parent_pids))
    part_map: dict[str, list[str]] = {parent_pid: [] for parent_pid in unique_parent_pids}
    for pid_batch in batched_pids(unique_parent_pids):
        query = build_part_query(pid_batch)
        request_description = f'Direct-part lookup for {len(pid_batch)} PID(s)'
        docs = fetch_search_docs(
            client,
            api_root,
            query,
            'pid,rel_is_part_of_ssim',
            request_description,
        )
        for doc in docs:
            part_pid = doc.get('pid')
            if not isinstance(part_pid, str):
                raise PidToCsvError('A direct-part result is missing its PID.')
            for parent_pid in get_parent_pids(doc, request_description):
                if parent_pid in part_map and part_pid not in part_map[parent_pid]:
                    part_map[parent_pid].append(part_pid)

    return part_map


def collect_direct_parts(
    client: httpx.Client,
    api_root: str,
    parent_pids: list[str],
) -> tuple[dict[str, list[str]], tuple[str, ...]]:
    """
    Retrieves direct parts and identifies those direct parts whose own parts will not be included.
    Called by: lib.csv_creator.create_csv()
    """
    direct_part_map = fetch_direct_part_map(client, api_root, parent_pids)
    direct_part_pids = list(
        dict.fromkeys(part_pid for parts in direct_part_map.values() for part_pid in parts),
    )
    pids_with_unincluded_parts: tuple[str, ...] = ()
    if direct_part_pids:
        deeper_part_map = fetch_direct_part_map(client, api_root, direct_part_pids)
        pids_with_unincluded_parts = tuple(part_pid for part_pid in direct_part_pids if deeper_part_map[part_pid])
    return direct_part_map, pids_with_unincluded_parts
