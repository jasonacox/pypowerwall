# pyPowerWall - Tesla FleetAPI - Create PEM Key
# -*- coding: utf-8 -*-
"""
 Tesla FleetAPI Setup - Create PEM Key
 
 This script creates a PEM-encoded public and private key.
 Put the public key in 
  {site}/.well-known/appspecific/com.tesla.3p.public-key.pem
 
 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall

 Requires: pip install cryptography
"""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

# Generate an EC key pair using the secp256r1 curve
private_key = ec.generate_private_key(ec.SECP256R1())

# Extract the public key
public_key = private_key.public_key()

# Serialize the public key in PEM format
pem_public_key = public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)

# Print the PEM-encoded public and private keys
print(f"Private Key: \n{private_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.TraditionalOpenSSL, encryption_algorithm=serialization.NoEncryption()).decode()}")
print(f"\nPublic Key: \n{pem_public_key.decode()}")

# Write the PEM-encoded public key to a file
with open('com.tesla.3p.public-key.pem', 'w') as f:
    f.write(pem_public_key.decode())
# Write the PEM-encoded private key to a file
with open('com.tesla.3p.private-key.pem', 'w') as f:
    f.write(private_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.TraditionalOpenSSL, encryption_algorithm=serialization.NoEncryption()).decode())

# Tell User
print("\nPublic and Private Keys written to PEM files:")
print(" * com.tesla.3p.public-key.pem")
print(" * com.tesla.3p.private-key.pem")
print("\nPut the public key on your registered website at:")
print("https://{domain}/.well-known/appspecific/com.tesla.3p.public-key.pem")
