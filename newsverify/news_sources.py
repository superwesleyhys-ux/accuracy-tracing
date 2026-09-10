"""Bounded public-web source collection for current news verification.

Search sends only the explicit query to Bing RSS. Page requests send no cookies,
authorization, referring page, claim text, or model output. Injected transports
are trusted test/application adapters: ``fetch(url)`` returns
``(final_url, headers, body_bytes)`` and ``search(query, limit)`` returns URLs
or dictionaries containing ``url``. The built-in transport validates DNS and
pins each connection to an approved address; injected adapters own their I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import Message
from html.parser import HTMLParser
import http.client
import ipaddress
import math
import os
from queue import Empty, Queue
import re
import socket
import ssl
from threading import Thread, Timer
import time
from typing import Callable, Mapping
from urllib.parse import quote, urlencode, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from .provenance import MaterialVersion


_PAGE_TYPES = {"text/html", "application/xhtml+xml", "text/plain"}
_RSS_TYPES = {"application/rss+xml", "application/xml", "text/xml"}
_REDIRECTS = {301, 302, 303, 307, 308}


class _SourceError(ValueError):
    """Fixed error codes, never remote headers or exception diagnostics."""


def _public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return address.is_global and not address.is_multicast and not address.is_reserved


def canonical_url(value: str) -> str:
    """Normalize an HTTP(S) URL, rejecting local hosts and literal private IPs.

DNS names receive a second, resolved-address check before real connections.
Fragments are removed; meaningful paths and query parameter order are retained.
"""
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise _SourceError("invalid_url")
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value) or "\\" in value:
        raise _SourceError("invalid_url")
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        raise _SourceError("invalid_url")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
        if parsed.scheme not in {"http", "https"} or not host or parsed.username is not None or parsed.password is not None:
            raise _SourceError("invalid_url")
        host = host.rstrip(".").encode("idna").decode("ascii").lower()
        if "%" in host or host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".home", ".lan")):
            raise _SourceError("non_public_url")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if "." not in host or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in host.split(".")):
                raise _SourceError("invalid_url") from None
        else:
            if not _public_address(str(address)):
                raise _SourceError("non_public_url")
            host = str(address)
        if port is not None and not 1 <= port <= 65535:
            raise _SourceError("invalid_url")
        authority = f"[{host}]" if ":" in host else host
        if port is not None and port != (443 if parsed.scheme == "https" else 80):
            authority += f":{port}"
        # Encode Unicode without decoding or reordering existing URL escapes.
        path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
        query = quote(parsed.query, safe="/%?:@!$&'()*+,;=-._~")
        return urlunsplit((parsed.scheme, authority, path, query, ""))
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, _SourceError):
            raise
        raise _SourceError("invalid_url") from None


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _SourceError("timeout")
    return remaining


def _resolve_public(host: str, port: int, deadline: float):
    # System DNS has no portable per-call timeout. A daemon worker bounds the
    # caller's wait; a stuck resolver cannot prevent process shutdown.
    result = Queue(maxsize=1)

    def resolve():
        try:
            result.put(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except Exception:
            result.put(None)

    Thread(target=resolve, daemon=True).start()
    try:
        addresses = result.get(timeout=_remaining(deadline))
    except Empty:
        raise _SourceError("timeout") from None
    if not addresses:
        raise _SourceError("dns_failed")
    # Reject mixed public/private answers instead of trying the public subset.
    for family, kind, protocol, _, address in addresses:
        if family not in {socket.AF_INET, socket.AF_INET6} or not _public_address(address[0]):
            raise _SourceError("non_public_address")
    return addresses[0]


def _tls_context():
    context = ssl.create_default_context()
    if not ("SSL_CERT_FILE" in os.environ or "SSL_CERT_DIR" in os.environ) and not context.cert_store_stats().get("x509_ca", 0):
        try:
            import certifi
        except ImportError:
            pass
        else:
            context.load_verify_locations(cafile=certifi.where())
    return context


def _headers(value: Mapping) -> dict[str, str]:
    if not isinstance(value, Mapping) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
        raise _SourceError("invalid_response")
    return {key.lower(): val for key, val in value.items()}


def _content_type(headers: dict[str, str]) -> tuple[str, str]:
    message = Message()
    message["content-type"] = headers.get("content-type", "application/octet-stream")
    return message.get_content_type().lower(), message.get_content_charset() or "utf-8"


def _publication_time(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            return None  # Do not invent a timezone or a time for a date-only label.
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError):
        return None


class _PageParser(HTMLParser):
    _BLOCKS = {"p", "div", "section", "article", "header", "footer", "main", "aside", "nav", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "table", "caption", "tr", "br", "hr"}
    _HIDDEN = {"script", "style", "noscript", "template", "svg"}

    def __init__(self, url: str, max_chars: int):
        super().__init__(convert_charrefs=True)
        self.url, self.max_chars = url, max_chars
        # Row records bypass prose whitespace folding so empty cells survive.
        self.parts: list[str | list[str]] = []
        self.row: list[str] | None = None
        self.cell_parts: list[str] | None = None
        self.title_parts: list[str] = []
        self.links: list[dict[str, str]] = []
        self.published_at = None
        self.hidden: list[str] = []
        self.in_head = self.in_title = False
        self.anchor: tuple[str, list[str]] | None = None
        self.chars = 0

    def add(self, text):
        self.chars += len(text)
        if self.chars > self.max_chars:
            raise _SourceError("extracted_text_too_large")
        if self.cell_parts is not None:
            self.cell_parts.append(text)
        else:
            self.parts.append(text)

    def close_cell(self):
        if self.cell_parts is not None:
            self.close_anchor()
            self.row.append(" ".join("".join(self.cell_parts).split()))
            self.cell_parts = None

    def close_row(self):
        self.close_cell()
        self.row = None

    def start_row(self):
        self.close_row()
        self.row = []
        self.parts.append(self.row)

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag in self._HIDDEN:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "head":
            self.in_head = True
        if tag == "title":
            self.in_title = True
        if tag == "meta" and (data.get("property", "").lower() == "article:published_time"
                              or data.get("itemprop", "").lower() == "datepublished"
                              or data.get("name", "").lower() in {"datepublished", "date", "pubdate"}):
            self.published_at = self.published_at or _publication_time(data.get("content"))
        if tag == "time" and data.get("itemprop", "").lower() == "datepublished":
            self.published_at = self.published_at or _publication_time(data.get("datetime"))
        if self.in_head:
            return
        if tag == "tr":
            self.start_row()
        elif tag in {"td", "th"}:
            self.close_cell()
            if self.row is None:
                self.start_row()
            self.cell_parts = []
        elif tag == "table":
            self.close_row()
        if tag in self._BLOCKS:
            self.add("\n")
        if tag == "a":
            self.close_anchor()
            try:
                self.anchor = (canonical_url(urljoin(self.url, data.get("href") or "")), []) if data.get("href") else None
            except _SourceError:
                self.anchor = None

    def close_anchor(self):
        if self.anchor:
            url, parts = self.anchor
            self.add(f" [{url}]")
            link = {"url": url, "text": " ".join("".join(parts).split())}
            if link not in self.links:
                self.links.append(link)
            self.anchor = None

    def handle_endtag(self, tag):
        if self.hidden:
            if tag in self.hidden:
                self.hidden = self.hidden[:self.hidden.index(tag)]
            return
        if tag == "title":
            self.in_title = False
        if tag == "head":
            self.in_head = False
        if not self.in_head:
            if tag == "a":
                self.close_anchor()
            if tag in {"td", "th"}:
                self.close_cell()
            elif tag in {"tr", "table"}:
                self.close_row()
            if tag in self._BLOCKS:
                self.add("\n")

    def handle_data(self, text):
        if self.hidden:
            return
        if self.in_title:
            self.title_parts.append(text)
        elif not self.in_head:
            self.add(text)
            if self.anchor:
                self.anchor[1].append(text)

    def document_text(self):
        self.close_row()
        self.close_anchor()
        lines, prose = [], []

        def flush_prose():
            lines.extend(text for line in "".join(prose).splitlines()
                         if (text := " ".join(line.split())))
            prose.clear()

        for part in self.parts:
            if isinstance(part, list):
                flush_prose()
                # Escape literal delimiters without changing the cell values.
                cells = [cell.replace("\\", "\\\\").replace("|", "\\|") for cell in part]
                lines.append("|" + "|".join(f" {cell} " for cell in cells) + "|")
            else:
                prose.append(part)
        flush_prose()
        return "\n".join(lines)


@dataclass(frozen=True)
class SourceDocument:
    url: str
    title: str
    content: str
    retrieved_at: str
    published_at: str | None = None
    links: list[dict[str, str]] = field(default_factory=list)

    @property
    def available_at(self) -> str:
        """A live capture establishes availability of these bytes at retrieval."""
        return self.retrieved_at

    @property
    def availability_basis(self) -> str:
        return "Current source text captured at retrieval; publication metadata does not establish earlier availability of this version."

    def to_material(self, version_id: str) -> MaterialVersion:
        return MaterialVersion(
            version_id=version_id, url=self.url, content=self.content,
            retrieved_at=self.retrieved_at, published_at=self.published_at,
            available_at=self.available_at,
            availability_basis=self.availability_basis,
            issuer=urlsplit(self.url).hostname or "unknown",
        )


class NewsSourceCollector:
    """Collect current source text, with budgets counting attempts, not successes.

Failed URLs are not retried automatically. The timeout bounds each built-in
fetch (including DNS and redirects); a search has one RSS request followed by
at most ``limit`` separately bounded document fetches. Injected adapters must
provide their own I/O deadlines. Instances are intended for sequential use.
"""

    def __init__(self, max_documents=8, max_searches=3, timeout=15, max_bytes=1_000_000,
                 search: Callable | None = None, fetch: Callable | None = None, max_chars=50_000):
        for name, value in (("max_documents", max_documents), ("max_searches", max_searches), ("max_bytes", max_bytes), ("max_chars", max_chars)):
            if type(value) is not int or value < (0 if name == "max_searches" else 1):
                raise ValueError(f"{name} must be a valid integer limit")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        if search is not None and not callable(search) or fetch is not None and not callable(fetch):
            raise ValueError("Injected adapters must be callable")
        self.max_documents, self.max_searches = max_documents, max_searches
        self.timeout, self.max_bytes, self.max_chars = float(timeout), max_bytes, max_chars
        self.documents: dict[str, SourceDocument] = {}
        self.errors: list[dict] = []
        self.requests: list[dict] = []
        self._fetch, self._search = fetch, search
        self._attempted: set[str] = set()
        self._aliases: dict[str, str] = {}
        self._queries: dict[str, list[str]] = {}

    def _error(self, operation, code, url=None):
        error = {"operation": operation, "code": code}
        if url is not None:
            error["url"] = url
        self.errors.append(error)

    def _check_headers(self, headers, allowed):
        kind, encoding = _content_type(headers)
        if kind == "application/pdf":
            raise _SourceError("unsupported_pdf")
        if kind not in allowed:
            raise _SourceError("unsupported_content_type")
        if headers.get("content-encoding", "identity").strip().lower() not in {"", "identity"}:
            raise _SourceError("unsupported_content_encoding")
        if "content-length" in headers:
            if not re.fullmatch(r"[0-9]+", headers["content-length"].strip()):
                raise _SourceError("invalid_content_length")
            if int(headers["content-length"]) > self.max_bytes:
                raise _SourceError("response_too_large")
        return kind, encoding

    def _exchange(self, url, deadline, allowed):
        parsed = urlsplit(url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        family, kind, protocol, _, address = _resolve_public(parsed.hostname, port, deadline)
        connection = http.client.HTTPConnection(parsed.hostname, port, timeout=_remaining(deadline))
        sock = None
        timer = None
        try:
            sock = socket.socket(family, kind, protocol)
            sock.settimeout(_remaining(deadline))
            sock.connect(address)  # Connect to the validated address, without a second DNS lookup.
            if parsed.scheme == "https":
                sock.settimeout(_remaining(deadline))
                sock = _tls_context().wrap_socket(sock, server_hostname=parsed.hostname)
            connection.sock = sock

            def expire():
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            timer = Timer(_remaining(deadline), expire)
            timer.daemon = True
            timer.start()
            target = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
            connection.request("GET", target, headers={
                "User-Agent": "NewsVerify/0.2 source-collector", "Accept": ", ".join(sorted(allowed)),
                "Accept-Encoding": "identity", "Connection": "close",
            })
            response = connection.getresponse()
            headers = _headers(dict(response.getheaders()))
            self.requests.append({"operation": "http", "url": url, "status": response.status})
            if response.status in _REDIRECTS:
                return response.status, headers, b""
            if not 200 <= response.status < 300:
                raise _SourceError("http_error")
            self._check_headers(headers, allowed)
            chunks, size = [], 0
            while True:
                sock.settimeout(_remaining(deadline))
                chunk = response.read1(min(65536, self.max_bytes + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > self.max_bytes:
                    raise _SourceError("response_too_large")
                chunks.append(chunk)
            _remaining(deadline)
            return response.status, headers, b"".join(chunks)
        finally:
            if timer:
                timer.cancel()
            connection.close()
            if sock is not None:
                sock.close()

    def _download(self, url, allowed):
        deadline = time.monotonic() + self.timeout
        seen = set()
        for _ in range(6):
            url = canonical_url(url)
            if url in seen:
                raise _SourceError("redirect_loop")
            seen.add(url)
            status, headers, body = self._exchange(url, deadline, allowed)
            _remaining(deadline)
            if status not in _REDIRECTS:
                return url, headers, body
            location = headers.get("location")
            if not location:
                raise _SourceError("invalid_redirect")
            url = canonical_url(urljoin(url, location))
        raise _SourceError("redirect_limit")

    def fetch(self, url) -> SourceDocument | None:
        try:
            url = canonical_url(url)
        except _SourceError as exc:
            self._error("fetch", str(exc))
            return None
        cached = self.documents.get(self._aliases.get(url, url))
        if cached:
            return cached
        if url in self._attempted:
            return None
        if len(self._attempted) >= self.max_documents:
            self._error("fetch", "document_limit", url)
            return None
        self._attempted.add(url)
        record = {"operation": "fetch", "url": url, "success": False}
        self.requests.append(record)
        started = time.monotonic()
        try:
            final_url, raw_headers, body = self._fetch(url) if self._fetch else self._download(url, _PAGE_TYPES)
            final_url, headers = canonical_url(final_url), _headers(raw_headers)
            kind, encoding = self._check_headers(headers, _PAGE_TYPES)
            if not isinstance(body, bytes):
                raise _SourceError("invalid_response")
            if len(body) > self.max_bytes:
                raise _SourceError("response_too_large")
            if body.lstrip().startswith(b"%PDF-"):
                raise _SourceError("unsupported_pdf")
            if time.monotonic() - started > self.timeout:
                raise _SourceError("timeout")
            try:
                text = body.decode(encoding, errors="replace")
            except LookupError:
                raise _SourceError("unsupported_charset") from None
            if kind in {"text/html", "application/xhtml+xml"}:
                parser = _PageParser(final_url, self.max_chars)
                parser.feed(text)
                parser.close()
                content = parser.document_text()
                title = " ".join("".join(parser.title_parts).split()) or final_url
                published, links = parser.published_at, parser.links
            else:
                content, title, published, links = text.strip(), final_url, None, []
                for candidate in re.findall(r"https?://[^\s<>\"']+", content):
                    try:
                        link = {"url": canonical_url(candidate.rstrip(".,;:!?)]}")), "text": ""}
                    except _SourceError:
                        continue
                    if link not in links:
                        links.append(link)
            if not content:
                raise _SourceError("empty_document")
            if len(content) > self.max_chars or len(title) > self.max_chars:
                raise _SourceError("extracted_text_too_large")
            document = SourceDocument(final_url, title, content,
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), published, links)
            self.documents.setdefault(final_url, document)
            self._aliases[url] = final_url
            record.update(success=True, final_url=final_url, bytes=len(body))
            return self.documents[final_url]
        except _SourceError as exc:
            self._error("fetch", str(exc), url)
        except (TimeoutError, socket.timeout):
            self._error("fetch", "timeout", url)
        except Exception:
            self._error("fetch", "timeout" if time.monotonic() - started >= self.timeout else "fetch_failed", url)
        return None

    def search(self, query, limit=3) -> list[SourceDocument]:
        if not isinstance(query, str) or not query.strip() or len(query) > 512:
            self._error("search", "invalid_query")
            return []
        if type(limit) is not int or limit < 1:
            self._error("search", "invalid_limit")
            return []
        query, limit = query.strip(), min(limit, self.max_documents)
        if query in self._queries:
            return [self.documents[url] for url in self._queries[query]][:limit]
        if len(self._queries) >= self.max_searches:
            self._error("search", "search_limit")
            return []
        self._queries[query] = []
        record = {"operation": "search", "query": query, "limit": limit, "success": False}
        self.requests.append(record)
        try:
            if self._search:
                candidates = self._search(query, limit)
            else:
                endpoint = "https://www.bing.com/search?" + urlencode({"format": "rss", "q": query})
                _, _, body = self._download(endpoint, _RSS_TYPES)
                if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
                    raise _SourceError("invalid_search_response")
                tree = ET.fromstring(body)
                candidates = [item.findtext("link") for item in tree.findall("./channel/item")]
            if not isinstance(candidates, list):
                raise _SourceError("invalid_search_response")
            found, seen = [], set()
            for item in candidates[:limit]:
                url = item.get("url") if isinstance(item, dict) else item
                document = self.fetch(url)
                if document is not None and document.url not in seen:
                    seen.add(document.url)
                    found.append(document)
            self._queries[query] = [doc.url for doc in found]
            record.update(success=True, documents=len(found))
            return found
        except _SourceError as exc:
            self._error("search", str(exc))
        except (TimeoutError, socket.timeout):
            self._error("search", "timeout")
        except Exception:
            self._error("search", "search_failed")
        return []
