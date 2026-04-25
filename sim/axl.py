"""
AxlNetwork: thin client for the AXL P2P node HTTP API.

Refactored from `skills/autoresearch-network/research_network.py`.
HTTP plumbing, peer discovery and queue draining are unchanged.
The application-level message schema is now `Statement` (geopolitical
simulation) instead of `Finding` (ML training result).

Library usage
-------------
    from sim.axl import AxlNetwork, Statement

    net = AxlNetwork()                       # talks to http://127.0.0.1:9002
    net.broadcast_statement(Statement(...))  # send to every reachable peer
    for s in net.drain_recv_queue():
        ...                                  # react to peer statements

CLI usage
---------
    python -m sim.axl --api http://127.0.0.1:9002 status
    python -m sim.axl --api http://127.0.0.1:9002 recv

Protocol
--------
  Wire format : JSON-encoded bytes, sent via POST /send (Content-Type: application/octet-stream)
  Peer discovery: GET /topology returns peers[] (direct) and tree[] (full spanning tree).
                  Together they cover every node reachable via Yggdrasil routing.
  Statement v1:
    {
      "proto":         1,
      "type":          "statement",
      "round":         <int>,
      "agent":         "us"|"china"|"eu"|"india",
      "act":           "statement"|"signal"|"escalation"|"coordination",
      "addressed_to":  "all" | <agent name>,
      "red_line":      <str|null>,            -- name of red line invoked, if any
      "body":          <str>,                 -- public statement text
      "rationale":     <str|null>,            -- short private reasoning
      "timestamp":     <float>,               -- unix epoch
      "sender_id":     <str>,                 -- 64-char hex Yggdrasil public key
    }
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Optional

PROTO_VERSION = 1
MSG_TYPE_STATEMENT = "statement"

log = logging.getLogger(__name__)


@dataclass
class Statement:
    """A single in-character statement issued by one simulation agent."""

    proto: int
    round_num: int
    agent: str
    act: str
    addressed_to: str
    body: str
    rationale: Optional[str]
    red_line: Optional[str]
    timestamp: float
    sender_id: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = MSG_TYPE_STATEMENT
        d["round"] = d.pop("round_num")
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Statement":
        return cls(
            proto=d.get("proto", PROTO_VERSION),
            round_num=int(d.get("round", d.get("round_num", 0))),
            agent=str(d["agent"]),
            act=str(d.get("act", "statement")),
            addressed_to=str(d.get("addressed_to", "all")),
            body=str(d.get("body", "")),
            rationale=d.get("rationale"),
            red_line=d.get("red_line"),
            timestamp=float(d.get("timestamp", time.time())),
            sender_id=str(d.get("sender_id", "")),
        )


def _get(url: str, timeout: int = 10) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, {}, b""
    except Exception as e:
        log.debug(f"GET {url} failed: {e}")
        return 0, {}, b""


def _post(url: str, data: bytes, headers: dict, timeout: int = 15) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, {}, b""
    except Exception as e:
        log.debug(f"POST {url} failed: {e}")
        return 0, {}, b""


class AxlNetwork:
    """
    Statement-passing client for an AXL node.

    All transport semantics (topology, send, recv) are preserved verbatim
    from the original ResearchNetwork. Only the application schema differs.
    """

    def __init__(self, api_url: str = "http://127.0.0.1:9002"):
        self.api_url = api_url.rstrip("/")
        self._seen: set[tuple[str, int]] = set()
        self._our_id: Optional[str] = None

    def get_topology(self) -> Optional[dict]:
        status, _, body = _get(f"{self.api_url}/topology")
        if status == 200:
            try:
                return json.loads(body)
            except json.JSONDecodeError as e:
                log.warning(f"Topology JSON parse error: {e}")
        return None

    def our_id(self) -> Optional[str]:
        if self._our_id is None:
            topo = self.get_topology()
            if topo:
                self._our_id = topo.get("our_public_key")
        return self._our_id

    def all_peer_ids(self) -> list[str]:
        topo = self.get_topology()
        if not topo:
            return []
        our = topo.get("our_public_key", "")
        ids: set[str] = set()
        for p in topo.get("peers", []):
            if p.get("up") and p.get("public_key"):
                ids.add(p["public_key"])
        for t in topo.get("tree", []):
            if t.get("public_key"):
                ids.add(t["public_key"])
        ids.discard(our)
        return list(ids)

    def broadcast_statement(self, stmt: Statement) -> int:
        if not stmt.sender_id:
            stmt.sender_id = self.our_id() or ""

        payload = json.dumps(stmt.to_dict()).encode("utf-8")
        peers = self.all_peer_ids()

        if not peers:
            log.warning("No peers reachable, statement not broadcast")
            return 0

        sent = 0
        for peer_id in peers:
            code, _, _ = _post(
                f"{self.api_url}/send",
                data=payload,
                headers={
                    "X-Destination-Peer-Id": peer_id,
                    "Content-Type": "application/octet-stream",
                },
            )
            if code == 200:
                sent += 1
            else:
                log.debug(f"Send to {peer_id[:12]}... returned {code}")

        log.info(
            f"Round {stmt.round_num} from {stmt.agent}: broadcast to {sent}/{len(peers)} peers"
        )
        return sent

    def drain_recv_queue(self) -> list[Statement]:
        new: list[Statement] = []

        while True:
            code, headers, body = _get(f"{self.api_url}/recv")
            if code == 204:
                break
            if code != 200:
                if code != 0:
                    log.warning(f"Recv returned {code}")
                break

            sender_id = headers.get("X-From-Peer-Id", headers.get("x-from-peer-id", ""))

            try:
                d = json.loads(body)
            except json.JSONDecodeError:
                continue

            if d.get("type") != MSG_TYPE_STATEMENT:
                continue

            try:
                stmt = Statement.from_dict(d)
            except (KeyError, TypeError, ValueError) as e:
                log.warning(f"Malformed statement from {sender_id[:12]}...: {e}")
                continue

            if sender_id:
                stmt.sender_id = sender_id

            key = (stmt.sender_id, stmt.round_num)
            if key in self._seen:
                continue
            self._seen.add(key)
            new.append(stmt)

        return new


def _cli_status(net: AxlNetwork) -> None:
    topo = net.get_topology()
    if not topo:
        print("ERROR: could not reach AXL node")
        raise SystemExit(1)
    peers = net.all_peer_ids()
    print(f"our_id:   {topo['our_public_key']}")
    print(f"our_ipv6: {topo['our_ipv6']}")
    print(f"peers:    {len(peers)}")
    for p in peers:
        print(f"  {p}")


def _cli_recv(net: AxlNetwork) -> None:
    stmts = net.drain_recv_queue()
    if not stmts:
        print("(no new statements)")
        return
    for s in stmts:
        print(json.dumps(s.to_dict()))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="sim.axl", description="AXL P2P statement client")
    parser.add_argument("--api", default="http://127.0.0.1:9002")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("recv")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )
    net = AxlNetwork(api_url=args.api)
    if args.cmd == "status":
        _cli_status(net)
    elif args.cmd == "recv":
        _cli_recv(net)


if __name__ == "__main__":
    main()
