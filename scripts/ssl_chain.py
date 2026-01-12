import re
import subprocess

import rich_click as click


@click.command()
@click.argument("host")
@click.option("-p", "--port", default=443, help="Port to connect to")
@click.option("-o", "--output", type=click.File("w"), default="-", help="Output file")
def main(host: str, port: int, output):
    """Extract SSL certificate chain from a host."""
    result = subprocess.run(
        ["openssl", "s_client", "-connect", f"{host}:{port}", "-showcerts"],
        input=b"",
        capture_output=True,
    )
    certs = re.findall(
        rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
        result.stdout,
        re.DOTALL,
    )
    for cert in certs:
        output.write(cert.decode() + "\n")
