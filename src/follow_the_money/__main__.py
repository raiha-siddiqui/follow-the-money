"""Local entry points. No command sends an exchange request or transaction."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("demo", "init", "serve", "mcp", "m365"):
        p = sub.add_parser(name)
        p.add_argument(
            "--workspace", type=Path, default=Path("data/follow_the_money/demo")
        )
        p.add_argument("--p1-workspace", type=Path)
        p.add_argument("--p1-config", type=Path)
        p.add_argument("--model-actor", action="append", default=[])
        if name == "demo":
            p.add_argument(
                "--learned-synthetic",
                action="store_true",
                help="Train a value policy on separate fictional traces and use it in this demo",
            )
        if name in {"serve", "mcp", "m365"}:
            p.add_argument("--key-file", type=Path)
            p.add_argument(
                "--port",
                type=int,
                default={"serve": 8765, "mcp": 8766, "m365": 3978}[name],
            )
        if name == "mcp":
            p.add_argument(
                "--transport", choices=["stdio", "streamable-http"], default="stdio"
            )
            p.add_argument("--actor", default="local-mcp")
            p.add_argument("--read-only", action="store_true")
        if name == "m365":
            p.add_argument("--allow-anonymous", action="store_true")
            p.add_argument("--max-cases-per-conversation", type=int, default=5)
    key = sub.add_parser("keygen")
    key.add_argument("--actor", required=True)
    key.add_argument(
        "--role", choices=["viewer", "agent", "approver", "reviewer"], required=True
    )
    sub.add_parser("ui")
    evaluation = sub.add_parser("evaluate")
    evaluation.add_argument("--output", type=Path, required=True)
    evaluation.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.command == "keygen":
        from follow_the_money.auth import new_key

        token, entry = new_key(args.actor, args.role)
        print(json.dumps({"token_shown_once": token, "key_file_entry": entry}))
        return
    if args.command == "ui":
        from follow_the_money import ui

        raise SystemExit(
            subprocess.call(
                [
                    sys.executable,
                    "-m",
                    "streamlit",
                    "run",
                    ui.__file__,
                    "--server.address=127.0.0.1",
                    "--server.headless=true",
                    "--server.allowedHosts=localhost",
                    "--server.allowedHosts=127.0.0.1",
                    "--browser.gatherUsageStats=false",
                ]
            )
        )
    if args.command == "evaluate":
        from follow_the_money.evaluation import evaluate

        print(json.dumps(evaluate(output=args.output, repeats=args.repeats), indent=2))
        return
    from follow_the_money.cases import TraceRequest
    from follow_the_money.fixtures import build_fixtures
    from follow_the_money.service import TraceService, validate_actor

    from follow_the_money.resolver import EntityResolver

    if bool(args.p1_workspace) != bool(args.p1_config):
        parser.error("Both --p1-workspace and --p1-config are required")
    resolver = EntityResolver.from_workspace(args.p1_workspace, args.p1_config)
    if args.command in {"demo", "init"}:
        score = None
        if getattr(args, "learned_synthetic", False):
            from follow_the_money.evaluation import train_value_policy

            score, _ = train_value_policy(args.workspace / "value-training")
        fixtures = build_fixtures(args.workspace / "fixtures")
        service = TraceService.initialize(
            args.workspace / "service",
            cache=Path(fixtures["cache"]),
            labels=Path(fixtures["labels"]),
            score=score,
            resolver=resolver,
            model_actors=args.model_actor,
        )
        if args.command == "demo":
            view = service.start_case(
                TraceRequest(
                    chain="bitcoin",
                    seed="syn_seed_a",
                    request_id=str(uuid4()),
                    draft_request=True,
                ),
                actor="local-analyst",
            )
            print(json.dumps(view, indent=2))
        else:
            print(
                json.dumps(
                    {
                        "service_workspace": str(service.root.resolve()),
                        "mode": "synthetic_replay",
                    }
                )
            )
        return
    service = TraceService(
        args.workspace, resolver=resolver, model_actors=args.model_actor
    )
    if args.command == "m365":
        from follow_the_money.m365 import run_local

        from follow_the_money.auth import KeyStore, parse_key_entries

        if not args.key_file and not args.allow_anonymous:
            parser.error("Playground requires --key-file or --allow-anonymous")
        keys = (
            KeyStore(
                parse_key_entries(
                    args.key_file.read_text(encoding="utf-8").splitlines()
                )
            )
            if args.key_file
            else None
        )
        run_local(
            service,
            port=args.port,
            keys=keys,
            allow_anonymous=args.allow_anonymous,
            max_cases_per_conversation=args.max_cases_per_conversation,
        )
        return
    from follow_the_money.auth import KeyStore, Principal, parse_key_entries

    if args.command == "mcp" and args.transport == "stdio":
        from follow_the_money.mcp_server import build_server

        os.environ["LANGSMITH_TRACING"] = "false"
        build_server(
            service,
            stdio_principal=Principal(
                validate_actor(args.actor), "viewer" if args.read_only else "agent"
            ),
        ).run(transport="stdio")
        return
    if not args.key_file:
        parser.error("HTTP services require --key-file with hashed key entries")
    keys = KeyStore(
        parse_key_entries(args.key_file.read_text(encoding="utf-8").splitlines())
    )
    import uvicorn

    if args.command == "serve":
        from follow_the_money.api import create_app

        app = create_app(service, keys)
    else:
        from follow_the_money.mcp_server import http_app

        app = http_app(service, keys)
    uvicorn.run(
        app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning"
    )


if __name__ == "__main__":
    main()
