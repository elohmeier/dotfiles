import base64
import binascii
import datetime
import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal

import rich_click as click
import questionary
from rich.console import Console
from rich.panel import Panel

# Initialize console
console = Console(
    stderr=True
)  # Use stderr for prompts/logs to not interfere with potential stdout usage

# --- Helper Functions ---


def run_command(
    cmd: list[str],
    check: bool = True,
    env: dict[str, str] | None = None,
    capture_output: bool = True,
    text: bool = True,
    suppress_output: bool = False,
) -> subprocess.CompletedProcess:
    """Runs a subprocess command, handles errors, and optionally captures output."""
    if not suppress_output:
        console.print(f"[dim]$ {' '.join(cmd)}[/dim]")
    try:
        # Combine OS environment with provided env vars if any
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        process = subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=text,
            env=full_env,
            errors="ignore",  # Ignore decoding errors for resilience
        )
        if not suppress_output and process.stdout and capture_output:
            console.print(f"[dim]Stdout: {process.stdout.strip()}[/dim]")
        if not suppress_output and process.stderr and capture_output:
            console.print(f"[dim]Stderr: {process.stderr.strip()}[/dim]")
        return process
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error executing command:[/bold red] {' '.join(cmd)}")
        if e.stdout:
            console.print(f"[red]Stdout:[/red]\n{e.stdout}")
        if e.stderr:
            console.print(f"[red]Stderr:[/red]\n{e.stderr}")
        raise  # Re-raise the exception after printing details
    except FileNotFoundError:
        console.print(
            f"[bold red]Error: Command not found:[/bold red] {cmd[0]}. Is it installed and in your PATH?"
        )
        sys.exit(1)
    except Exception:
        console.print(
            f"[bold red]An unexpected error occurred running command:[/bold red] {' '.join(cmd)}"
        )
        console.print_exception(show_locals=False)
        sys.exit(1)


def get_kube_secret_value(
    kubeconfig: str, context: str, namespace: str, secret_name: str, data_key: str
) -> str:
    """Retrieves and decodes a specific key from a Kubernetes secret."""
    cmd = [
        "kubectl",
        "--kubeconfig",
        kubeconfig,
        "--context",
        context,
        "-n",
        namespace,
        "get",
        "secret",
        secret_name,
        "-o",
        f"jsonpath={{.data.{data_key}}}",
    ]
    console.print(f"[dim]Fetching secret '{secret_name}' key '{data_key}'...[/dim]")
    try:
        # Run silently first, only show command if it fails
        result = run_command(
            cmd, capture_output=True, text=True, check=False, suppress_output=True
        )
        if result.returncode != 0 or not result.stdout:
            console.print(
                f"[yellow]Warn:[/yellow] Could not get secret '{secret_name}' key '{data_key}'. Trying again verbosely."
            )
            # Rerun verbosely if failed silently
            result = run_command(
                cmd, capture_output=True, text=True, check=True, suppress_output=False
            )

        encoded_value = result.stdout.strip()
        if not encoded_value:
            msg = f"Secret '{secret_name}' key '{data_key}' not found or is empty."
            raise ValueError(msg)  # noqa

        decoded_value = base64.b64decode(encoded_value).decode("utf-8")
        console.print(
            f"[green]Successfully retrieved secret '{secret_name}' key '{data_key}'.[/green]"
        )
    except subprocess.CalledProcessError:
        console.print(
            f"[bold red]Error:[/bold red] Failed to get secret '{secret_name}' key '{data_key}' in namespace '{namespace}' context '{context}'."
        )
        console.print(
            "Please check if the secret and key exist and you have permissions."
        )
        sys.exit(1)
    except (ValueError, binascii.Error) as e:
        console.print(
            f"[bold red]Error:[/bold red] Failed to decode secret value for '{secret_name}' key '{data_key}'. Error: {e}"
        )
        sys.exit(1)
    else:
        return decoded_value


def ensure_value(value: str | None, flag: str) -> str:
    """Ensure a required CLI/config value is present."""
    if value:
        return value
    console.print(f"[bold red]Error:[/bold red] Missing required option {flag}.")
    sys.exit(1)


def resolve_context_namespace(
    kubeconfig: str, context: str | None, namespace: str | None
) -> tuple[str, str]:
    """Prompt/select context and namespace, ensuring strings."""
    if not context:
        contexts = get_kube_contexts(kubeconfig)
        context = select_from_list(contexts, "Select the Kubernetes context")
    context = ensure_value(context, "--context")

    if not namespace:
        namespaces = get_kube_namespaces(kubeconfig, context)
        namespace = select_from_list(
            namespaces, f"Select the namespace in context '{context}'"
        )
    namespace = ensure_value(namespace, "--namespace")
    return context, namespace


def resolve_db_params(
    mode: Literal["backup", "restore"],
    kubeconfig: str,
    context: str,
    namespace: str,
    cnpg_cluster: str | None,
    pod_name: str | None,
    db_name: str | None,
    db_user: str | None,
) -> tuple[str | None, str, str, str]:
    """Shared auto-discovery for cluster/pod/db/user."""
    if not cnpg_cluster and (not pod_name or not db_name or not db_user):
        cnpg_clusters = get_cnpg_clusters(kubeconfig, context, namespace)
        cnpg_cluster = select_from_list(
            cnpg_clusters,
            f"Select the CloudNativePG cluster in '{namespace}'",
        )

    if cnpg_cluster:
        console.print(
            f"Attempting to derive config from CNPG cluster '{cnpg_cluster}'..."
        )
        if not pod_name:
            pod_selector = (
                get_cnpg_primary_pod if mode == "restore" else get_cnpg_backup_pod
            )
            pod_name = pod_selector(kubeconfig, context, namespace, cnpg_cluster)
            if not pod_name:
                console.print(
                    f"  Could not find suitable pod for cluster '{cnpg_cluster}'"
                )

        if not db_name or not db_user:
            db_name_found, db_owner = get_cnpg_db_info(
                kubeconfig, context, namespace, cnpg_cluster
            )
            if db_name_found and not db_name:
                db_name = db_name_found
                console.print(f"  Derived database name: {db_name}")
            if db_owner and not db_user:
                db_user = db_owner
                console.print(f"  Derived database user: {db_user}")

        if not db_name:
            db_name = questionary.text(
                "Enter database name:", default=cnpg_cluster
            ).ask()
        if not db_user:
            db_user = questionary.text(
                "Enter database user:", default=cnpg_cluster
            ).ask()

    pod_name = ensure_value(pod_name, "--pod-name")
    db_name = ensure_value(db_name, "--db-name")
    db_user = ensure_value(db_user, "--db-user")
    return cnpg_cluster, pod_name, db_name, db_user


def _kubectl_base_cmd(kubeconfig: str, context: str, namespace: str) -> list[str]:
    return [
        "kubectl",
        "--kubeconfig",
        kubeconfig,
        "--context",
        context,
        "-n",
        namespace,
    ]


def kubectl_exec_dump(
    kubeconfig: str,
    context: str,
    namespace: str,
    pod_name: str,
    db_name: str,
    output_file: str,
    format_type: str = "c",
    compress_level: int = 6,
) -> bool:
    """Dump database on the pod to a temp file, then transfer via kubectl cp.

    Avoids streaming binary data through kubectl exec stdout, which can
    silently truncate large outputs due to SPDY/WebSocket buffering issues.
    """
    if format_type == "d":
        console.print(
            "[bold red]Error:[/bold red] Directory format ('d') is not supported."
        )
        return False

    console.print(
        f"Dumping database '{db_name}' from pod '{pod_name}' to {output_file}..."
    )

    # Build pg_dump command to run inside the pod, writing to a temp file
    remote_tmp = f"/run/pg_dump_{db_name}_{os.getpid()}.backup"
    pg_dump_cmd = f"pg_dump -d {db_name} -F {format_type}"
    if format_type in ["c", "t"] and compress_level is not None:
        pg_dump_cmd += f" -Z {compress_level}"
    pg_dump_cmd += f" -f {remote_tmp}"

    kbase = _kubectl_base_cmd(kubeconfig, context, namespace)
    output_path = Path(output_file)
    temp_path = output_path.with_suffix(f"{output_path.suffix}.tmp")

    try:
        # Step 1: Run pg_dump on the pod, writing to a file there
        console.print(f"  Running pg_dump on pod (writing to {remote_tmp})...")
        dump_result = subprocess.run(
            [*kbase, "exec", pod_name, "--", "bash", "-c", pg_dump_cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=False,
        )
        if dump_result.stderr:
            stderr_text = dump_result.stderr.decode("utf-8", errors="ignore").strip()
            if stderr_text:
                console.print(f"[dim]pg_dump stderr: {stderr_text}[/dim]")

        # Step 2: Get the file size on the pod for later verification
        size_result = subprocess.run(
            [*kbase, "exec", pod_name, "--", "stat", "-c", "%s", remote_tmp],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True,
        )
        remote_size = int(size_result.stdout.strip())
        console.print(f"  Remote dump size: {remote_size / (1024 * 1024):.2f} MB")

        # Step 3: Copy the file from the pod to local temp path
        console.print("  Transferring backup via kubectl cp...")
        cp_src = f"{namespace}/{pod_name}:{remote_tmp}"
        subprocess.run(
            [*kbase, "cp", cp_src, str(temp_path), "--retries=3"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=False,
        )

        # Step 4: Verify transferred file size matches remote
        local_size = temp_path.stat().st_size
        if local_size != remote_size:
            console.print(
                f"[bold red]Error:[/bold red] Size mismatch: remote={remote_size}, local={local_size}"
            )
            temp_path.unlink(missing_ok=True)
            return False
        console.print(f"  Size verified: {local_size} bytes")

        # Step 5: Verify archive TOC is readable
        verify_result = subprocess.run(
            ["pg_restore", "--list", str(temp_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
            text=False,
        )
        if verify_result.returncode != 0:
            console.print(
                "[bold red]Error:[/bold red] Backup verification failed with pg_restore --list."
            )
            if verify_result.stderr:
                console.print(
                    f"[red]Stderr:[/red]\n{verify_result.stderr.decode('utf-8', errors='ignore')}"
                )
            temp_path.unlink(missing_ok=True)
            return False

        # Step 6: Compute checksum and atomically publish
        hasher = hashlib.sha256()
        with temp_path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                hasher.update(chunk)
        checksum_path = output_path.with_suffix(f"{output_path.suffix}.sha256")
        checksum_path.write_text(f"{hasher.hexdigest()}  {output_path.name}\n")

        os.replace(temp_path, output_path)
        dir_fd = os.open(output_path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

        console.print(
            f"[green]Database dump completed successfully to {output_file}[/green]"
        )
        console.print(f"[green]Checksum written to {checksum_path}[/green]")
        return True

    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error during database dump:[/bold red] {e}")
        if e.stderr:
            console.print(
                f"[red]Stderr:[/red]\n{e.stderr.decode('utf-8', errors='ignore')}"
            )
        temp_path.unlink(missing_ok=True)
        return False
    except Exception as e:
        console.print(
            f"[bold red]Unexpected error during database dump:[/bold red] {e}"
        )
        temp_path.unlink(missing_ok=True)
        return False
    finally:
        # Clean up remote temp file
        try:
            subprocess.run(
                [*kbase, "exec", pod_name, "--", "rm", "-f", remote_tmp],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 for a file."""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_backup_checksum(backup_file: str) -> bool:
    """Verify backup checksum against adjacent .sha256 sidecar."""
    backup_path = Path(backup_file)
    checksum_path = backup_path.with_suffix(f"{backup_path.suffix}.sha256")

    if not checksum_path.exists():
        console.print(
            f"[bold red]Error:[/bold red] Checksum file not found: {checksum_path}"
        )
        return False

    checksum_line = checksum_path.read_text().strip()
    expected_checksum = checksum_line.split()[0] if checksum_line else ""
    if not expected_checksum:
        console.print(
            f"[bold red]Error:[/bold red] Invalid checksum file format: {checksum_path}"
        )
        return False

    actual_checksum = compute_sha256(backup_path)
    if actual_checksum != expected_checksum:
        console.print("[bold red]Error:[/bold red] Backup checksum mismatch.")
        console.print(f"Expected: {expected_checksum}")
        console.print(f"Actual:   {actual_checksum}")
        return False

    console.print(f"[green]Checksum verified successfully: {checksum_path}[/green]")
    return True


def kubectl_exec_restore(
    kubeconfig: str,
    context: str,
    namespace: str,
    pod_name: str,
    db_name: str,
    db_user: str,
    backup_file: str,
) -> bool:
    """Use kubectl exec to restore database from backup file."""
    try:
        maintenance_db = "postgres"  # Use postgres db for maintenance operations

        # Drop database
        console.print(f"Dropping database '{db_name}'...")
        drop_cmd = [
            "kubectl",
            "--kubeconfig",
            kubeconfig,
            "--context",
            context,
            "-n",
            namespace,
            "exec",
            pod_name,
            "--",
            "psql",
            "-d",
            maintenance_db,
            "-c",
            f'DROP DATABASE IF EXISTS "{db_name}";',
        ]
        run_command(drop_cmd, check=True)

        # Create database
        console.print(f"Creating database '{db_name}'...")
        create_cmd = [
            "kubectl",
            "--kubeconfig",
            kubeconfig,
            "--context",
            context,
            "-n",
            namespace,
            "exec",
            pod_name,
            "--",
            "psql",
            "-d",
            maintenance_db,
            "-c",
            f'CREATE DATABASE "{db_name}";',
        ]
        run_command(create_cmd, check=True)

        # Set ownership
        console.print(f"Setting ownership of '{db_name}' to '{db_user}'...")
        owner_cmd = [
            "kubectl",
            "--kubeconfig",
            kubeconfig,
            "--context",
            context,
            "-n",
            namespace,
            "exec",
            pod_name,
            "--",
            "psql",
            "-d",
            maintenance_db,
            "-c",
            f'ALTER DATABASE "{db_name}" OWNER TO "{db_user}";',
        ]
        run_command(owner_cmd, check=True)

        # Restore from backup
        console.print(f"Restoring database from {backup_file}...")
        restore_cmd = [
            "kubectl",
            "--kubeconfig",
            kubeconfig,
            "--context",
            context,
            "-n",
            namespace,
            "exec",
            "-i",
            pod_name,
            "--",
            "pg_restore",
            "-d",
            db_name,
            "--no-owner",
            "--clean",
            "--if-exists",
        ]

        # Pipe the backup file to kubectl exec
        with open(backup_file, "rb") as f:
            subprocess.run(
                restore_cmd,
                stdin=f,
                stderr=subprocess.PIPE,
                check=True,
                text=False,  # Binary mode for backup files
            )

        # Grant all privileges on database to app user
        console.print(
            f"Granting privileges on database '{db_name}' to user '{db_user}'..."
        )
        grant_db_cmd = [
            "kubectl",
            "--kubeconfig",
            kubeconfig,
            "--context",
            context,
            "-n",
            namespace,
            "exec",
            pod_name,
            "--",
            "psql",
            "-d",
            db_name,
            "-c",
            f'GRANT ALL PRIVILEGES ON DATABASE "{db_name}" TO "{db_user}";',
        ]
        run_command(grant_db_cmd, check=True)

        # Grant privileges on all tables in public schema to app user
        console.print(f"Granting privileges on all tables to user '{db_user}'...")
        grant_tables_cmd = [
            "kubectl",
            "--kubeconfig",
            kubeconfig,
            "--context",
            context,
            "-n",
            namespace,
            "exec",
            pod_name,
            "--",
            "psql",
            "-d",
            db_name,
            "-c",
            f'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "{db_user}";',
        ]
        run_command(grant_tables_cmd, check=True)

        # Grant privileges on all sequences in public schema to app user
        console.print(f"Granting privileges on all sequences to user '{db_user}'...")
        grant_sequences_cmd = [
            "kubectl",
            "--kubeconfig",
            kubeconfig,
            "--context",
            context,
            "-n",
            namespace,
            "exec",
            pod_name,
            "--",
            "psql",
            "-d",
            db_name,
            "-c",
            f'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "{db_user}";',
        ]
        run_command(grant_sequences_cmd, check=True)

        # Grant default privileges for future objects
        console.print("Setting default privileges for future objects...")
        grant_default_cmd = [
            "kubectl",
            "--kubeconfig",
            kubeconfig,
            "--context",
            context,
            "-n",
            namespace,
            "exec",
            pod_name,
            "--",
            "psql",
            "-d",
            db_name,
            "-c",
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "{db_user}"; ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO "{db_user}";',
        ]
        run_command(grant_default_cmd, check=True)

        console.print(
            f"[green]Database restore completed successfully from {backup_file}[/green]"
        )
        return True

    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error during database restore:[/bold red] {e}")
        if e.stderr:
            console.print(
                f"[red]Stderr:[/red]\n{e.stderr.decode('utf-8', errors='ignore')}"
            )
        return False
    except Exception as e:
        console.print(
            f"[bold red]Unexpected error during database restore:[/bold red] {e}"
        )
        return False


# --- Auto Discovery Functions ---


def select_from_list(items: list[str], message: str) -> str | None:
    """Uses questionary to prompt user selection from a list."""
    if not items:
        console.print(f"[yellow]No items found for selection: {message}[/yellow]")
        return None
    if len(items) == 1:
        console.print(
            f"Auto-selecting the only available option for {message}: {items[0]}"
        )
        return items[0]
    return questionary.select(message, choices=items).ask()


def get_kube_contexts(kubeconfig: str | None = None) -> list[str]:
    """Gets available Kubernetes contexts."""
    cmd = ["kubectl", "config", "get-contexts", "-o", "name"]
    if kubeconfig:
        cmd.extend(["--kubeconfig", kubeconfig])
    try:
        result = run_command(
            cmd, check=True, capture_output=True, text=True, suppress_output=True
        )
        return result.stdout.strip().splitlines()
    except Exception as e:
        console.print(f"[bold red]Error getting Kubernetes contexts:[/bold red] {e}")
        return []


def get_kube_namespaces(kubeconfig: str, context: str) -> list[str]:
    """Gets available Kubernetes namespaces in a context."""
    cmd = [
        "kubectl",
        "--kubeconfig",
        kubeconfig,
        "--context",
        context,
        "get",
        "namespaces",
        "-o",
        "name",
    ]
    try:
        result = run_command(
            cmd, check=True, capture_output=True, text=True, suppress_output=True
        )
        return [
            ns.replace("namespace/", "") for ns in result.stdout.strip().splitlines()
        ]
    except Exception as e:
        console.print(
            f"[bold red]Error getting namespaces for context '{context}':[/bold red] {e}"
        )
        return []


def get_cnpg_clusters(kubeconfig: str, context: str, namespace: str) -> list[str]:
    """Gets CloudNativePG cluster names in a namespace."""
    cmd = [
        "kubectl",
        "--kubeconfig",
        kubeconfig,
        "--context",
        context,
        "-n",
        namespace,
        "get",
        "clusters.postgresql.cnpg.io",
        "-o",
        "name",
    ]
    try:
        result = run_command(
            cmd, check=True, capture_output=True, text=True, suppress_output=True
        )
        return [
            c.replace("cluster.postgresql.cnpg.io/", "")
            for c in result.stdout.strip().splitlines()
        ]
    except Exception as e:
        # It's okay if CNPG CRD isn't installed or no clusters exist, just return empty
        console.print(
            f"[dim]Could not list CNPG clusters in {namespace} (maybe none exist or CRD not installed): {e}[/dim]"
        )
        return []


def get_cnpg_db_info(
    kubeconfig: str, context: str, namespace: str, cluster_name: str
) -> tuple[str | None, str | None]:
    """Gets the database name and owner from a CNPG cluster spec.

    Returns:
        tuple: (database_name, database_owner) or (None, None) if not found
    """
    cmd = [
        "kubectl",
        "--kubeconfig",
        kubeconfig,
        "--context",
        context,
        "-n",
        namespace,
        "get",
        f"cluster.postgresql.cnpg.io/{cluster_name}",
        "-o",
        "jsonpath={.spec.bootstrap.initdb.database},{.spec.bootstrap.initdb.owner}",
    ]
    try:
        result = run_command(
            cmd, check=True, capture_output=True, text=True, suppress_output=True
        )
        output = result.stdout.strip()
        if output and "," in output:
            db_name, db_owner = output.split(",", 1)
            if db_name and db_owner:
                console.print(f"  Found database name: {db_name}, owner: {db_owner}")
                return db_name, db_owner

        console.print(
            f"[yellow]Warn:[/yellow] Could not extract database name and owner from CNPG cluster '{cluster_name}' spec."
        )
    except Exception as e:
        console.print(
            f"[yellow]Warn:[/yellow] Error getting database info from CNPG cluster '{cluster_name}': {e}"
        )

    return None, None


def get_cnpg_secret_name(
    kubeconfig: str, context: str, namespace: str, cluster_name: str
) -> str | None:
    """Gets the application secret name from a CNPG cluster spec.

    Returns:
        str: Secret name or None if not found
    """
    cmd = [
        "kubectl",
        "--kubeconfig",
        kubeconfig,
        "--context",
        context,
        "-n",
        namespace,
        "get",
        f"cluster.postgresql.cnpg.io/{cluster_name}",
        "-o",
        "jsonpath={.spec.bootstrap.initdb.secret.name}",
    ]
    try:
        result = run_command(
            cmd, check=True, capture_output=True, text=True, suppress_output=True
        )
        secret_name = result.stdout.strip()
        if secret_name:
            console.print(f"  Found application secret name: {secret_name}")
            return secret_name

        console.print(
            f"[yellow]Warn:[/yellow] Could not extract secret name from CNPG cluster '{cluster_name}' spec."
        )
    except Exception as e:
        console.print(
            f"[yellow]Warn:[/yellow] Error getting secret name from CNPG cluster '{cluster_name}': {e}"
        )

    return None


def get_cnpg_superuser_secret_name(
    kubeconfig: str, context: str, namespace: str, cluster_name: str
) -> str | None:
    """Gets the superuser secret name from a CNPG cluster.

    Returns:
        str: Superuser secret name or None if not found
    """
    # CNPG typically creates a superuser secret named <cluster-name>-superuser
    expected_secret_name = f"{cluster_name}-superuser"
    cmd = [
        "kubectl",
        "--kubeconfig",
        kubeconfig,
        "--context",
        context,
        "-n",
        namespace,
        "get",
        "secret",
        expected_secret_name,
        "-o",
        "name",
    ]
    try:
        run_command(cmd, check=True, suppress_output=True)  # Just check existence
        console.print(f"  Found superuser secret name: {expected_secret_name}")
        return expected_secret_name
    except Exception:
        console.print(
            f"[yellow]Warn:[/yellow] Could not find standard CNPG superuser secret '{expected_secret_name}' for cluster '{cluster_name}'."
        )
        return None


def get_cnpg_replica_pod(
    kubeconfig: str, context: str, namespace: str, cluster_name: str
) -> str | None:
    """Gets a read replica pod name for a CNPG cluster."""
    cmd = [
        "kubectl",
        "--kubeconfig",
        kubeconfig,
        "--context",
        context,
        "-n",
        namespace,
        "get",
        "pods",
        "-l",
        f"cnpg.io/cluster={cluster_name},cnpg.io/instanceRole=replica",
        "-o",
        "name",
    ]
    try:
        result = run_command(
            cmd, check=True, capture_output=True, text=True, suppress_output=True
        )
        pods = [p.replace("pod/", "") for p in result.stdout.strip().splitlines()]
        if pods:
            console.print(f"  Found replica pod: {pods[0]}")
            return pods[0]
        else:
            console.print(
                f"[dim]No replica pods found for CNPG cluster '{cluster_name}'.[/dim]"
            )
            return None
    except Exception as e:
        console.print(
            f"[yellow]Warn:[/yellow] Error getting replica pods for CNPG cluster '{cluster_name}': {e}"
        )
        return None


def get_cnpg_primary_pod(
    kubeconfig: str, context: str, namespace: str, cluster_name: str
) -> str | None:
    """Gets the primary pod name for a CNPG cluster."""
    cmd = [
        "kubectl",
        "--kubeconfig",
        kubeconfig,
        "--context",
        context,
        "-n",
        namespace,
        "get",
        "pods",
        "-l",
        f"cnpg.io/cluster={cluster_name},cnpg.io/instanceRole=primary",
        "-o",
        "name",
    ]
    try:
        result = run_command(
            cmd, check=True, capture_output=True, text=True, suppress_output=True
        )
        pods = [p.replace("pod/", "") for p in result.stdout.strip().splitlines()]
        if pods:
            console.print(f"  Found primary pod: {pods[0]}")
            return pods[0]
        else:
            console.print(
                f"[yellow]Warn:[/yellow] No primary pod found for CNPG cluster '{cluster_name}'."
            )
            return None
    except Exception as e:
        console.print(
            f"[yellow]Warn:[/yellow] Error getting primary pod for CNPG cluster '{cluster_name}': {e}"
        )
        return None


def get_cnpg_backup_pod(
    kubeconfig: str, context: str, namespace: str, cluster_name: str
) -> str | None:
    """Gets the best pod for backup operations (prefers replica, falls back to primary)."""
    # First try to get a replica pod for backup
    replica_pod = get_cnpg_replica_pod(kubeconfig, context, namespace, cluster_name)
    if replica_pod:
        console.print(f"  Using replica pod for backup: {replica_pod}")
        return replica_pod

    # Fall back to primary if no replicas available
    console.print("  No replica pods available, falling back to primary pod for backup")
    primary_pod = get_cnpg_primary_pod(kubeconfig, context, namespace, cluster_name)
    if primary_pod:
        console.print(f"  Using primary pod for backup: {primary_pod}")
        return primary_pod

    return None


# --- Click Group and Context ---


@click.group()
@click.option(
    "--kubeconfig",
    default=lambda: os.path.expanduser("~/.kube/config"),
    envvar="KUBECONFIG",
    help="Path to the Kubernetes config file. Can also be set via KUBECONFIG environment variable.",
    type=click.Path(exists=True),
)
@click.option("--context", help="Kubernetes context. If omitted, will prompt.")
@click.option("--namespace", help="Kubernetes namespace. If omitted, will prompt.")
@click.option(
    "--cnpg-cluster",
    help="CloudNativePG cluster name. If omitted, will prompt.",
)
@click.option(
    "--pod-name",
    help="PostgreSQL pod name. If omitted, derived from CNPG cluster primary pod.",
)
@click.option(
    "--db-name",
    help="Database name. If omitted, derived from CNPG cluster spec or prompts.",
)
@click.option(
    "--db-user",
    help="Database user. If omitted, derived from CNPG cluster spec or prompts.",
)
@click.pass_context
def cli(
    ctx,
    kubeconfig,
    context,
    namespace,
    cnpg_cluster,
    pod_name,
    db_name,
    db_user,
):
    """PostgreSQL Kubernetes Management Tool."""
    # Ensure that ctx.obj exists and is a dict (for subcommands)
    ctx.ensure_object(dict)

    # Store common configuration in context
    ctx.obj["kubeconfig"] = kubeconfig
    ctx.obj["context"] = context
    ctx.obj["namespace"] = namespace
    ctx.obj["cnpg_cluster"] = cnpg_cluster
    ctx.obj["pod_name"] = pod_name
    ctx.obj["db_name"] = db_name
    ctx.obj["db_user"] = db_user


@cli.command()
@click.option(
    "--backup-dir",
    default=lambda: os.path.join(os.path.expanduser("~"), "backups"),
    help="Directory to store backups.",
    type=click.Path(),
)
@click.option(
    "--backup-file",
    help="Specific file path for the backup. If provided, --backup-dir is ignored.",
    type=click.Path(),
)
@click.option(
    "--format",
    type=click.Choice(["c", "p", "t"]),
    default="c",
    help="Backup format: c=custom, p=plain text, t=tar.",
)
@click.option(
    "--compress-level",
    type=click.IntRange(0, 9),
    default=6,
    help="Compression level (0-9) for custom and tar formats.",
)
@click.option(
    "--retention-days",
    type=int,
    default=30,
    help="Number of days to keep backups. Set to 0 to disable cleanup.",
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts.")
@click.pass_context
def backup(
    ctx,
    backup_dir,
    backup_file,
    format,
    compress_level,
    retention_days,
    yes,
):
    """Backs up a PostgreSQL database from a Kubernetes cluster to a local directory."""

    # Get configuration from context
    kubeconfig = ctx.obj["kubeconfig"]
    context = ctx.obj["context"]
    namespace = ctx.obj["namespace"]
    cnpg_cluster = ctx.obj["cnpg_cluster"]
    pod_name = ctx.obj["pod_name"]
    db_name = ctx.obj["db_name"]
    db_user = ctx.obj["db_user"]

    console.print(
        Panel(
            "[bold magenta]PostgreSQL Kubernetes Backup Tool[/bold magenta]",
            expand=False,
        )
    )

    # --- Auto-Discovery ---
    console.print("\n[bold blue]--- Auto-Discovery and Configuration ---[/bold blue]")

    context, namespace = resolve_context_namespace(kubeconfig, context, namespace)
    cnpg_cluster, pod_name, db_name, db_user = resolve_db_params(
        "backup",
        kubeconfig,
        context,
        namespace,
        cnpg_cluster,
        pod_name,
        db_name,
        db_user,
    )

    # --- Setup Backup File Path ---
    console.print("\n[bold blue]--- Setting Up Backup File Path ---[/bold blue]")

    if backup_file:
        # Use the specific file path provided
        backup_file_path = Path(backup_file)
        # Create parent directory if it doesn't exist
        backup_file_path.parent.mkdir(parents=True, exist_ok=True)
        console.print(f"Using specified backup file: {backup_file_path}")
        backup_path = backup_file_path.parent
    else:
        # Use the auto-generated directory structure
        # Create timestamp for the backup
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create directory structure: backup_dir/context/namespace/cluster/database/
        backup_path = Path(backup_dir) / context / namespace
        if cnpg_cluster:
            backup_path = backup_path / cnpg_cluster
        backup_path = backup_path / db_name

        # Create the directory if it doesn't exist
        backup_path.mkdir(parents=True, exist_ok=True)
        console.print(f"Backup directory: {backup_path}")

        # Determine file extension based on format
        format_extensions = {
            "c": ".backup",
            "p": ".sql",
            "d": "",  # directory format doesn't have an extension
            "t": ".tar",
        }
        extension = format_extensions[format]

        # Create the full backup filename
        backup_filename = f"{db_name}_{timestamp}{extension}"
        backup_file_path = backup_path / backup_filename

    # --- Display Confirmation ---
    console.print("\n[bold blue]--- Backup Plan ---[/bold blue]")
    console.print(f"Context:    [cyan]{context}[/cyan]")
    console.print(f"Namespace:  [cyan]{namespace}[/cyan]")
    console.print(f"Pod:        [cyan]{pod_name}[/cyan]")
    console.print(f"Database:   [cyan]{db_name}[/cyan]")
    console.print(f"User:       [cyan]{db_user}[/cyan]")
    console.print(
        f"Backup Format: [cyan]{format}[/cyan] (Compression: {compress_level})"
    )
    console.print(f"Backup File: [cyan]{backup_file_path}[/cyan]")

    if not yes and not questionary.confirm("Proceed with backup?", default=True).ask():
        console.print("Backup aborted by user.")
        sys.exit(0)

    # --- Perform Backup ---
    console.print("\n[bold blue]--- Starting Backup ---[/bold blue]")

    # Use kubectl exec to run pg_dump
    success = kubectl_exec_dump(
        kubeconfig=kubeconfig,
        context=context,
        namespace=namespace,
        pod_name=pod_name,
        db_name=db_name,
        output_file=str(backup_file_path),
        format_type=format,
        compress_level=compress_level,
    )

    if not success:
        console.print("[bold red]Backup failed.[/bold red]")
        sys.exit(1)

    # --- Cleanup Old Backups ---
    if retention_days > 0 and not backup_file:
        # Only perform cleanup when using auto-generated directory structure
        console.print("\n[bold blue]--- Cleaning Up Old Backups ---[/bold blue]")
        console.print(
            f"Looking for backups older than {retention_days} days in {backup_path}..."
        )

        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=retention_days)
        count_removed = 0

        for backup_file_item in backup_path.glob(f"{db_name}_*"):
            if backup_file_item.is_file():
                file_mtime = datetime.datetime.fromtimestamp(
                    backup_file_item.stat().st_mtime
                )
                if file_mtime < cutoff_date:
                    console.print(
                        f"Removing old backup: {backup_file_item.name} (from {file_mtime.strftime('%Y-%m-%d')})"
                    )
                    backup_file_item.unlink()
                    count_removed += 1

        if count_removed > 0:
            console.print(f"[green]Removed {count_removed} old backup(s).[/green]")
        else:
            console.print("No old backups to remove.")
    elif retention_days > 0 and backup_file:
        console.print(
            "\n[yellow]Note:[/yellow] Cleanup skipped when using --backup-file option."
        )

    # --- Summary ---
    console.print("\n[bold green]--- Backup Completed Successfully ---[/bold green]")
    console.print(f"Backup saved to: {backup_file_path}")
    console.print(
        f"Backup size: {backup_file_path.stat().st_size / (1024 * 1024):.2f} MB"
    )


@cli.command()
@click.option(
    "--backup-file",
    required=True,
    help="Path to the backup file to restore.",
    type=click.Path(exists=True),
)
@click.option(
    "--verify-checksum/--no-verify-checksum",
    default=True,
    help="Verify backup checksum using adjacent .sha256 file before restoring.",
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts.")
@click.pass_context
def restore(ctx, backup_file, verify_checksum, yes):
    """Restores a PostgreSQL database from a backup file to a Kubernetes cluster."""

    # Get configuration from context
    kubeconfig = ctx.obj["kubeconfig"]
    context = ctx.obj["context"]
    namespace = ctx.obj["namespace"]
    cnpg_cluster = ctx.obj["cnpg_cluster"]
    pod_name = ctx.obj["pod_name"]
    db_name = ctx.obj["db_name"]
    db_user = ctx.obj["db_user"]

    console.print(
        Panel(
            "[bold magenta]PostgreSQL Kubernetes Restore Tool[/bold magenta]",
            expand=False,
        )
    )

    # --- Auto-Discovery ---
    console.print("\n[bold blue]--- Auto-Discovery and Configuration ---[/bold blue]")

    context, namespace = resolve_context_namespace(kubeconfig, context, namespace)
    cnpg_cluster, pod_name, db_name, db_user = resolve_db_params(
        "restore",
        kubeconfig,
        context,
        namespace,
        cnpg_cluster,
        pod_name,
        db_name,
        db_user,
    )

    # --- Display Confirmation ---
    console.print("\n[bold blue]--- Restore Plan ---[/bold blue]")
    console.print(f"Context:       [cyan]{context}[/cyan]")
    console.print(f"Namespace:     [cyan]{namespace}[/cyan]")
    console.print(f"Pod:           [cyan]{pod_name}[/cyan]")
    console.print(f"Database:      [cyan]{db_name}[/cyan]")
    console.print(f"App User:      [cyan]{db_user}[/cyan]")
    console.print(f"Backup File:   [cyan]{backup_file}[/cyan]")
    console.print(f"Verify Checksum: [cyan]{verify_checksum}[/cyan]")

    console.print(
        f"\n[bold red]WARNING:[/bold red] This will [bold red]DROP and RECREATE[/bold red] the database '{db_name}'!"
    )
    console.print(
        "[bold red]All existing data in the database will be lost![/bold red]"
    )

    if (
        not yes
        and not questionary.confirm(
            "Are you sure you want to proceed with the restore?", default=False
        ).ask()
    ):
        console.print("Restore aborted by user.")
        sys.exit(0)

    # --- Perform Restore ---
    console.print("\n[bold blue]--- Starting Restore ---[/bold blue]")

    if verify_checksum and not verify_backup_checksum(backup_file):
        console.print(
            "[bold red]Restore aborted due to checksum verification failure.[/bold red]"
        )
        sys.exit(1)

    success = kubectl_exec_restore(
        kubeconfig=kubeconfig,
        context=context,
        namespace=namespace,
        pod_name=pod_name,
        db_name=db_name,
        db_user=db_user,
        backup_file=backup_file,
    )

    if not success:
        console.print("[bold red]Restore failed.[/bold red]")
        sys.exit(1)

    # --- Summary ---
    console.print("\n[bold green]--- Restore Completed Successfully ---[/bold green]")
    console.print(f"Database '{db_name}' has been restored from: {backup_file}")


def main() -> None:
    cli(standalone_mode=True)


if __name__ == "__main__":
    main()
