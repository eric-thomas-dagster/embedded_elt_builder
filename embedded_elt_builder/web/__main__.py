"""Launch the ELT Builder Web UI.

Usage:
    python -m embedded_elt_builder.web
    python -m embedded_elt_builder.web --repo-path /path/to/elt-pipelines
"""

import argparse
from pathlib import Path
import uvicorn
from .app_enhanced import create_app


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Launch the ELT Builder Web UI")
    parser.add_argument(
        "--repo-path",
        type=str,
        default=".",
        help="Path to your ELT pipelines repository"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)"
    )

    args = parser.parse_args()

    repo_path = Path(args.repo_path).expanduser().resolve()
    
    print("\n" + "="*60)
    print(f"  Starting ELT Builder Web UI")
    print("="*60)
    print(f"\n  Repository: {repo_path}")
    print(f"  URL: http://{args.host}:{args.port}")
    print("\nPress Ctrl+C to stop the server")
    print("="*60 + "\n")

    app = create_app(str(repo_path))
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
