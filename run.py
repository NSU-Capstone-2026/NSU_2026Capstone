from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NSU 통합 실행기 (Pose + Web)")
    parser.add_argument("--mode", choices=["all", "pose", "web"], default="all")

    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--https", action="store_true", help="Enable HTTPS with mkcert-managed local certs")
    parser.add_argument("--mkcert-dir", default="certs", help="Directory for mkcert-generated cert/key")
    parser.add_argument("--ssl-cert", default=None, help="HTTPS certificate file path (PEM)")
    parser.add_argument("--ssl-key", default=None, help="HTTPS private key file path (PEM)")

    return parser


def run_pose_process() -> subprocess.Popen:
    pose_entry = Path(__file__).resolve().parent / "pose" / "main.py"
    return subprocess.Popen([sys.executable, str(pose_entry)])


def run_web(args: argparse.Namespace) -> None:
    from pose.web_server import run_web_server

    ssl_cert, ssl_key = resolve_ssl_paths(args)
    pose_entry = Path(__file__).resolve().parent / "pose" / "main.py"
    run_web_server(
        host=args.host,
        port=args.port,
        pose_entry=pose_entry,
        ssl_cert=ssl_cert,
        ssl_key=ssl_key,
    )


def resolve_ssl_paths(args: argparse.Namespace) -> tuple[str | None, str | None]:
    if not args.https:
        return args.ssl_cert, args.ssl_key

    cert_path = Path(args.ssl_cert) if args.ssl_cert else Path(args.mkcert_dir) / "localhost.pem"
    key_path = Path(args.ssl_key) if args.ssl_key else Path(args.mkcert_dir) / "localhost-key.pem"

    if cert_path.exists() and key_path.exists():
        return str(cert_path), str(key_path)

    mkcert = shutil.which("mkcert")
    if not mkcert:
        raise RuntimeError(
            "mkcert가 필요합니다. 설치 후 `mkcert -install` 실행하거나 "
            "--ssl-cert/--ssl-key로 인증서를 직접 지정하세요."
        )

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[HTTPS] mkcert로 인증서 생성: {cert_path}, {key_path}")
    cmd = [
        mkcert,
        "-cert-file",
        str(cert_path),
        "-key-file",
        str(key_path),
        "localhost",
        "127.0.0.1",
        "::1",
    ]
    subprocess.run(cmd, check=True)
    return str(cert_path), str(key_path)


def main() -> None:
    args = build_parser().parse_args()

    if args.mode == "pose":
        proc = run_pose_process()
        proc.wait()
        return

    if args.mode == "web":
        run_web(args)
        return

    run_web(args)


if __name__ == "__main__":
    main()
