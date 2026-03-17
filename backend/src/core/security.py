"""
Security utilities for authentication and encryption.

Provides AES-256 encryption for PHI, password hashing, and JWT utilities.
All PHI must be encrypted before storage using these utilities.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64

import bcrypt as _bcrypt
from jose import JWTError, jwt

from .config import settings


# =============================================================================
# Password Hashing  (direct bcrypt – avoids passlib/bcrypt>=4 incompatibility)
# =============================================================================


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return _bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# =============================================================================
# JWT Token Management
# =============================================================================

ALGORITHM = "HS256"


def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Payload data to encode in token
        expires_delta: Optional custom expiration time
        
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.access_token_expire_minutes
        )
    
    to_encode.update({"exp": expire, "type": "access"})
    
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(data: dict[str, Any]) -> str:
    """
    Create a JWT refresh token with longer expiration.
    
    Args:
        data: Payload data to encode in token
        
    Returns:
        Encoded JWT refresh token string
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict[str, Any]]:
    """
    Decode and verify a JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded payload dict or None if invalid
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# =============================================================================
# AES-256 Encryption for PHI
# =============================================================================

def _get_fernet_key() -> bytes:
    """
    Derive a Fernet-compatible key from the encryption key.
    
    Fernet requires a 32-byte base64-urlsafe encoded key.
    We use PBKDF2 to derive a consistent key from the configured encryption key.
    
    Returns:
        Fernet-compatible encryption key
    """
    # Use PBKDF2 to derive a key
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"neuroreach_phi_salt",  # Static salt for consistent derivation
        iterations=100000,
        backend=default_backend()
    )
    key = base64.urlsafe_b64encode(
        kdf.derive(settings.encryption_key.encode())
    )
    return key


# Initialize Fernet cipher
_fernet = Fernet(_get_fernet_key())


def encrypt_phi(plaintext: str) -> bytes:
    """
    Encrypt PHI (Protected Health Information) using AES-256.
    
    All PHI must be encrypted before storing in the database.
    
    Args:
        plaintext: Plain text PHI to encrypt
        
    Returns:
        Encrypted bytes
        
    Example:
        encrypted_name = encrypt_phi("John Doe")
        # Store encrypted_name in database
    """
    if not plaintext:
        return b""
    
    return _fernet.encrypt(plaintext.encode("utf-8"))


def decrypt_phi(ciphertext: bytes) -> str:
    """
    Decrypt PHI (Protected Health Information).
    
    Args:
        ciphertext: Encrypted bytes from database
        
    Returns:
        Decrypted plain text string
        
    Raises:
        ValueError: If decryption fails (invalid or corrupted data)
        
    Example:
        name = decrypt_phi(lead.first_name_encrypted)
    """
    if not ciphertext:
        return ""
    
    try:
        return _fernet.decrypt(ciphertext).decode("utf-8")
    except Exception as e:
        # Log error without exposing PHI
        raise ValueError("Failed to decrypt PHI data") from e


# =============================================================================
# Hashing Utilities
# =============================================================================

def hash_ip_address(ip_address: str) -> str:
    """
    Hash an IP address for privacy-preserving storage.
    
    Uses SHA-256 with a salt for one-way hashing.
    
    Args:
        ip_address: IP address string
        
    Returns:
        Hashed IP address (64 character hex string)
    """
    if not ip_address:
        return ""
    
    # Add salt to prevent rainbow table attacks
    salted = f"neuroreach_ip_{ip_address}_{settings.secret_key[:16]}"
    return hashlib.sha256(salted.encode()).hexdigest()


def generate_secure_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure random token.
    
    Args:
        length: Desired length of token
        
    Returns:
        URL-safe random token string
    """
    return secrets.token_urlsafe(length)


# =============================================================================
# Input Sanitization
# =============================================================================

def sanitize_string(value: str, max_length: int = 1000) -> str:
    """
    Sanitize a string input to prevent injection attacks.
    
    Args:
        value: Input string to sanitize
        max_length: Maximum allowed length
        
    Returns:
        Sanitized string
    """
    if not value:
        return ""
    
    # Truncate to max length
    value = value[:max_length]
    
    # Remove null bytes
    value = value.replace("\x00", "")
    
    # Strip leading/trailing whitespace
    value = value.strip()
    
    return value


def is_valid_zip_code(zip_code: str) -> bool:
    """
    Validate US ZIP code format.
    
    Args:
        zip_code: ZIP code string to validate
        
    Returns:
        True if valid format, False otherwise
    """
    if not zip_code:
        return False
    
    # Remove any spaces or dashes
    clean_zip = zip_code.replace(" ", "").replace("-", "")
    
    # Must be 5 or 9 digits
    if not clean_zip.isdigit():
        return False
    
    return len(clean_zip) in (5, 9)


def is_in_service_area(zip_code: str) -> bool:
    """
    Check if ZIP code is within the service area.
    
    Service area is defined by ZIP code prefixes in configuration.
    Default: Arizona (85xxx, 86xxx)
    
    Args:
        zip_code: ZIP code to check
        
    Returns:
        True if in service area, False otherwise
    """
    if not zip_code:
        return False
    
    # Clean and get first 2 digits
    clean_zip = zip_code.replace(" ", "").replace("-", "")
    
    if len(clean_zip) < 2:
        return False
    
    prefix = clean_zip[:2]
    
    return prefix in settings.service_area_prefixes_list
