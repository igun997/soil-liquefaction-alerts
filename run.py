#!/usr/bin/env python3
"""
Run script for Liquefaction Alert Detection System.

Usage:
    python run.py              # Run with default settings
    python run.py --reload     # Run with auto-reload for development
    python run.py --port 8080  # Run on custom port
"""
import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(
        description="Liquefaction Alert Detection System"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )

    args = parser.parse_args()

    print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║     Liquefaction Alert Detection System                      ║
    ║     Based on Boulanger & Idriss (2014) methodology           ║
    ╠══════════════════════════════════════════════════════════════╣
    ║     Dashboard: http://{args.host}:{args.port}                         ║
    ║     API Docs:  http://{args.host}:{args.port}/api/docs                ║
    ╚══════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
