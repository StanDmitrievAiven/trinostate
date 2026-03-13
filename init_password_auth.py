#!/usr/bin/env python3
"""
Configure Trino password authentication when TRINO_ADMIN_USER and TRINO_ADMIN_PASSWORD are set.
Generates a bcrypt password file and configures password-authenticator.properties.
Password auth requires internal-communication.shared-secret (required for single-node too).
"""
import os
import sys
import secrets

try:
    import bcrypt
except ImportError:
    print("ERROR: bcrypt required. Install with: pip install bcrypt", file=sys.stderr)
    sys.exit(1)


def main():
    admin_user = os.environ.get("TRINO_ADMIN_USER")
    admin_password = os.environ.get("TRINO_ADMIN_PASSWORD")

    if not admin_user or not admin_password:
        return  # No password auth configured

    config_dir = "/etc/trino"
    password_file = os.path.join(config_dir, "password.db")

    # Generate bcrypt hash (cost 10, Trino requires min 8)
    hashed = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt(rounds=10)).decode()
    with open(password_file, "w") as f:
        f.write(f"{admin_user}:{hashed}\n")

    # Ensure trino user can read it (we run as root in entrypoint)
    os.chmod(password_file, 0o640)
    try:
        import pwd
        trino = pwd.getpwnam("trino")
        os.chown(password_file, trino.pw_uid, trino.pw_gid)
    except (KeyError, ImportError):
        pass  # trino user might not exist in some environments

    # Write password-authenticator.properties
    auth_config = os.path.join(config_dir, "password-authenticator.properties")
    with open(auth_config, "w") as f:
        f.write("password-authenticator.name=file\n")
        f.write(f"file.password-file={password_file}\n")

    # Update config.properties: enable password auth, shared secret, and process forwarded headers
    config_file = os.path.join(config_dir, "config.properties")
    if os.path.exists(config_file):
        try:
            with open(config_file) as f:
                content = f.read()
            additions = []
            if "http-server.authentication.type" not in content:
                additions.append("http-server.authentication.type=PASSWORD")
            if "http-server.process-forwarded" not in content:
                additions.append("http-server.process-forwarded=true")
            # Allow HTTP for localhost (catalog watcher); required for internal REST API calls
            if "http-server.authentication.allow-insecure-over-http" not in content:
                additions.append("http-server.authentication.allow-insecure-over-http=true")
            # Password auth requires shared secret (use env or generate)
            if "internal-communication.shared-secret" not in content:
                secret = os.environ.get("TRINO_INTERNAL_SECRET") or secrets.token_urlsafe(32)
                additions.append(f"internal-communication.shared-secret={secret}")
            if additions:
                with open(config_file, "a") as f:
                    f.write("\n# Password auth (from TRINO_ADMIN_USER/PASSWORD)\n")
                    f.write("\n".join(additions) + "\n")
        except PermissionError:
            print("WARNING: Cannot write config.properties for password auth", file=sys.stderr)

    print(f"Password authentication configured for user: {admin_user}")


if __name__ == "__main__":
    main()
