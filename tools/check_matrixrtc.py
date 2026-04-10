from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx


TRANSPORT_PATH = "/_matrix/client/unstable/org.matrix.msc4143/rtc/transports"
ELEMENT_WELL_KNOWN_PATH = "/.well-known/element/element.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Quick MatrixRTC sanity check: well-known, rtc/transports, "
            "Element config, and LiveKit endpoints."
        )
    )
    parser.add_argument(
        "--homeserver",
        required=True,
        help="Matrix homeserver base URL, e.g. https://matrix.example.org",
    )
    parser.add_argument(
        "--client-domain",
        help=(
            "Domain whose /.well-known/matrix/client should be checked. "
            "Defaults to the homeserver host."
        ),
    )
    parser.add_argument(
        "--user",
        help="Matrix localpart or full MXID used for authenticated transport check.",
    )
    parser.add_argument(
        "--password",
        help="Matrix password used for authenticated transport check.",
    )
    parser.add_argument(
        "--access-token",
        help="Existing Matrix access token for authenticated transport check.",
    )
    parser.add_argument(
        "--element-config",
        help="Optional path to Element Web config.json to inspect element_call settings.",
    )
    parser.add_argument(
        "--call-url",
        help=(
            "Optional Element Call frontend base URL, e.g. https://call.example.org. "
            "If omitted, the script will try to infer it from /.well-known/element/element.json."
        ),
    )
    parser.add_argument(
        "--jwt-health-url",
        help="Optional LiveKit JWT health endpoint, e.g. https://rtc.example.org/livekit/jwt/healthz",
    )
    parser.add_argument(
        "--sfu-url",
        help="Optional SFU URL to probe, e.g. https://sfu.example.org",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output in addition to the summary.",
    )
    return parser.parse_args()


def normalize_user(user: str | None) -> str | None:
    if not user:
        return None
    return user[1:].split(":", 1)[0] if user.startswith("@") else user


def decode_json(response: httpx.Response) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text


def fetch(
    client: httpx.Client,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    expected_status: set[int] | None = None,
) -> dict[str, Any]:
    try:
        response = client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        return {"ok": False, "url": url, "error": str(exc)}

    payload = decode_json(response)
    ok = expected_status is None or response.status_code in expected_status
    return {
        "ok": ok,
        "url": url,
        "status_code": response.status_code,
        "payload": payload,
    }


def login_for_token(client: httpx.Client, homeserver: str, user: str, password: str) -> dict[str, Any]:
    url = f"{homeserver.rstrip('/')}/_matrix/client/v3/login"
    body = {
        "type": "m.login.password",
        "identifier": {"type": "m.id.user", "user": normalize_user(user)},
        "password": password,
    }
    try:
        response = client.post(url, json=body)
    except httpx.HTTPError as exc:
        return {"ok": False, "url": url, "error": str(exc)}

    payload = decode_json(response)
    token = payload.get("access_token") if isinstance(payload, dict) else None
    return {
        "ok": response.status_code == 200 and bool(token),
        "url": url,
        "status_code": response.status_code,
        "payload": payload,
        "access_token": token,
    }


def read_element_config(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    config_path = Path(path)
    if not config_path.exists():
        return {"ok": False, "path": str(config_path), "error": "file not found"}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"ok": False, "path": str(config_path), "error": str(exc)}

    element_call = data.get("element_call") or {}
    return {
        "ok": True,
        "path": str(config_path),
        "use_exclusively": element_call.get("use_exclusively"),
    }


def extract_foci_url(well_known: dict[str, Any] | None) -> str | None:
    if not isinstance(well_known, dict):
        return None
    foci = well_known.get("org.matrix.msc4143.rtc_foci")
    if not isinstance(foci, list):
        return None
    for item in foci:
        if isinstance(item, dict) and item.get("type") == "livekit":
            return item.get("livekit_service_url")
    return None


def extract_transport_url(transport_payload: dict[str, Any] | None) -> str | None:
    if not isinstance(transport_payload, dict):
        return None
    transports = transport_payload.get("rtc_transports")
    if not isinstance(transports, list):
        return None
    for item in transports:
        if isinstance(item, dict) and item.get("type") == "livekit":
            return item.get("livekit_service_url")
    return None


def extract_call_widget_url(element_well_known: dict[str, Any] | None) -> str | None:
    if not isinstance(element_well_known, dict):
        return None
    call = element_well_known.get("call")
    if not isinstance(call, dict):
        return None
    widget_url = call.get("widget_url")
    return widget_url.rstrip("/") if isinstance(widget_url, str) else None


def print_check(label: str, result: dict[str, Any]) -> None:
    if result.get("ok"):
        status = result.get("status_code", "OK")
        print(f"[OK] {label}: {status}")
        return
    if "status_code" in result:
        print(f"[FAIL] {label}: HTTP {result['status_code']}")
    else:
        print(f"[FAIL] {label}: {result.get('error', 'unknown error')}")


def main() -> int:
    args = parse_args()
    homeserver = args.homeserver.rstrip("/")
    client_domain = (args.client_domain or homeserver.split("://", 1)[-1]).rstrip("/")
    well_known_url = f"https://{client_domain}/.well-known/matrix/client"
    element_well_known_url = f"https://{client_domain}{ELEMENT_WELL_KNOWN_PATH}"
    transport_url = f"{homeserver}{TRANSPORT_PATH}"

    result: dict[str, Any] = {
        "homeserver": homeserver,
        "client_domain": client_domain,
    }

    with httpx.Client(timeout=args.timeout, verify=not args.insecure, follow_redirects=True) as client:
        well_known = fetch(client, well_known_url, expected_status={200})
        element_well_known = fetch(client, element_well_known_url, expected_status={200})
        unauth_transport = fetch(client, transport_url, expected_status={200, 401})
        auth_login = None
        auth_transport = None

        token = args.access_token
        if not token and args.user and args.password:
            auth_login = login_for_token(client, homeserver, args.user, args.password)
            token = auth_login.get("access_token") if auth_login.get("ok") else None

        if token:
            auth_transport = fetch(
                client,
                transport_url,
                headers={"Authorization": f"Bearer {token}"},
                expected_status={200},
            )

        jwt_health = (
            fetch(client, args.jwt_health_url, expected_status={200}) if args.jwt_health_url else None
        )
        sfu_health = fetch(client, args.sfu_url, expected_status={200}) if args.sfu_url else None

        element_well_known_payload = element_well_known.get("payload")
        inferred_call_url = extract_call_widget_url(element_well_known_payload)
        call_url = (args.call_url or inferred_call_url or "").rstrip("/")
        call_frontend = fetch(client, f"{call_url}/", expected_status={200}) if call_url else None
        call_config = fetch(client, f"{call_url}/config.json", expected_status={200}) if call_url else None

    element_config = read_element_config(args.element_config)
    well_known_payload = well_known.get("payload")
    element_well_known_payload = element_well_known.get("payload")
    auth_transport_payload = auth_transport.get("payload") if auth_transport else None
    foci_url = extract_foci_url(well_known_payload)
    transport_livekit_url = extract_transport_url(auth_transport_payload)
    call_widget_url = extract_call_widget_url(element_well_known_payload)
    payload_match = bool(foci_url and transport_livekit_url and foci_url == transport_livekit_url)
    call_url_match = bool(call_widget_url and call_frontend and call_frontend.get("ok"))

    result.update(
        {
            "well_known": well_known,
            "element_well_known": element_well_known,
            "unauth_transport": unauth_transport,
            "auth_login": auth_login,
            "auth_transport": auth_transport,
            "jwt_health": jwt_health,
            "sfu_health": sfu_health,
            "call_frontend": call_frontend,
            "call_config": call_config,
            "element_config": element_config,
            "well_known_livekit_service_url": foci_url,
            "transport_livekit_service_url": transport_livekit_url,
            "call_widget_url": call_widget_url,
            "transport_payload_match": payload_match,
            "call_frontend_reachable": call_url_match,
        }
    )

    print_check("well-known", well_known)
    print_check("element well-known", element_well_known)
    print_check("rtc/transports without token", unauth_transport)
    if auth_login:
        print_check("matrix login", auth_login)
    if auth_transport:
        print_check("rtc/transports with token", auth_transport)
    if jwt_health:
        print_check("livekit jwt health", jwt_health)
    if sfu_health:
        print_check("sfu health", sfu_health)
    if call_frontend:
        print_check("element call frontend", call_frontend)
    if call_config:
        print_check("element call config", call_config)

    if element_config:
        if element_config.get("ok"):
            print(
                f"[OK] element config: use_exclusively="
                f"{element_config.get('use_exclusively')!r} ({element_config['path']})"
            )
        else:
            print(f"[FAIL] element config: {element_config['error']}")

    if foci_url:
        print(f"[INFO] well-known livekit_service_url: {foci_url}")
    else:
        print("[WARN] well-known livekit_service_url: not found")

    if call_widget_url:
        print(f"[INFO] element call widget_url: {call_widget_url}")
    else:
        print("[WARN] element call widget_url: not found")

    if transport_livekit_url:
        print(f"[INFO] transport livekit_service_url: {transport_livekit_url}")
    elif auth_transport:
        print("[WARN] transport livekit_service_url: not found")

    if foci_url and transport_livekit_url:
        if payload_match:
            print("[OK] transport payload matches .well-known")
        else:
            print("[FAIL] transport payload mismatch with .well-known")

    summary_flags = {
        "route_missing": unauth_transport.get("status_code") == 404,
        "auth_required_as_expected": unauth_transport.get("status_code") == 401,
        "server_misconfigured": not well_known.get("ok")
        or not element_well_known.get("ok")
        or unauth_transport.get("status_code") == 404
        or (auth_transport is not None and not auth_transport.get("ok"))
        or (call_frontend is not None and not call_frontend.get("ok"))
        or (call_config is not None and not call_config.get("ok")),
        "transport_payload_mismatch": bool(foci_url and transport_livekit_url and not payload_match),
        "call_frontend_missing": bool(call_widget_url) and not call_url_match,
    }
    result["summary"] = summary_flags

    if summary_flags["route_missing"]:
        print("[RESULT] route missing")
        exit_code = 2
    elif summary_flags["call_frontend_missing"]:
        print("[RESULT] element call frontend missing")
        exit_code = 5
    elif summary_flags["server_misconfigured"]:
        print("[RESULT] server misconfigured")
        exit_code = 3
    elif summary_flags["transport_payload_mismatch"]:
        print("[RESULT] transport payload mismatch")
        exit_code = 4
    elif summary_flags["auth_required_as_expected"]:
        print("[RESULT] auth required as expected")
        exit_code = 0
    else:
        print("[RESULT] OK")
        exit_code = 0

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
