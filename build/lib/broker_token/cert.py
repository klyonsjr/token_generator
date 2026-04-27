import os


def create_self_signed_cert(cert_path: str = "server.crt", key_path: str = "server.key") -> bool:
    """Generate a self-signed certificate and write it to *cert_path* and *key_path*.

    Returns True on success, False if the cryptography library is not installed.
    Raises RuntimeError on any other failure.
    """
    try:
        import datetime
        import ipaddress

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        print("cryptography library not installed. Install with: pip install cryptography")
        print("Alternatively, generate a certificate manually with OpenSSL:")
        print(
            "openssl req -x509 -newkey rsa:2048 -keyout server.key -out server.crt -days 365 -nodes"
        )
        return False

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "ID"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Star"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OAuth2 Test Server"),
            x509.NameAttribute(NameOID.COMMON_NAME, "myapp.kelyons.com"),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("myapp.kelyons.com"),
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )

    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    with open(key_path, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    print(f"Self-signed certificate created: {cert_path}, {key_path}")
    return True
