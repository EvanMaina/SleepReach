"""
Encryption service for PHI protection.

Provides high-level interface for encrypting and decrypting
Protected Health Information (PHI) before database storage.
"""

import logging
from typing import Optional

from ..core.security import encrypt_phi, decrypt_phi, hash_ip_address
from ..schemas.lead import LeadCreate

_logger = logging.getLogger(__name__)


class EncryptionService:
    """
    Service for encrypting and decrypting PHI.
    
    All PHI must be encrypted before storage in the database.
    This service provides a clean interface for encryption operations.
    
    PHI fields that must be encrypted:
    - first_name
    - last_name
    - email
    - phone
    
    Example usage:
        service = EncryptionService()
        encrypted_data = service.encrypt_lead_phi(lead_create_data)
        # Store encrypted_data in database
        
        # Later, when reading:
        decrypted = service.decrypt_lead_phi(lead_from_db)
    """
    
    @staticmethod
    def encrypt_field(value: Optional[str]) -> Optional[bytes]:
        """
        Encrypt a single field value.
        
        Args:
            value: Plain text value to encrypt
            
        Returns:
            Encrypted bytes or None if value is None
        """
        if value is None:
            return None
        return encrypt_phi(value)
    
    @staticmethod
    def decrypt_field(value: Optional[bytes]) -> Optional[str]:
        """
        Decrypt a single field value.

        Returns None (instead of raising) if decryption fails so that a single
        corrupted record never crashes the entire list endpoint for all
        coordinators.  All failures are logged at ERROR level so ops can
        investigate without the log ever containing the raw ciphertext.

        Args:
            value: Encrypted bytes to decrypt

        Returns:
            Decrypted string or None if value is None or decryption fails
        """
        if value is None:
            return None
        try:
            return decrypt_phi(value)
        except Exception:
            _logger.error(
                "PHI decryption failed for a field — data may be corrupted or "
                "there is a key mismatch.  Returning None to prevent a single "
                "bad record from aborting the full batch.  Investigate immediately."
            )
            return None
    
    @classmethod
    def encrypt_lead_phi(cls, lead_data: LeadCreate) -> dict:
        """
        Encrypt all PHI fields from lead creation data.
        
        Args:
            lead_data: LeadCreate schema with plain text PHI
            
        Returns:
            Dictionary with encrypted PHI fields ready for database
        """
        return {
            "first_name_encrypted": cls.encrypt_field(lead_data.first_name),
            "last_name_encrypted": cls.encrypt_field(lead_data.last_name),
            "email_encrypted": cls.encrypt_field(lead_data.email),
            "phone_encrypted": cls.encrypt_field(lead_data.phone),
        }
    
    @classmethod
    def decrypt_lead_phi(cls, lead_model) -> dict:
        """
        Decrypt all PHI fields from lead database model.
        
        Args:
            lead_model: Lead SQLAlchemy model with encrypted PHI
            
        Returns:
            Dictionary with decrypted PHI fields
        """
        # first_name, email, phone are `str` (non-Optional) in LeadListResponse /
        # LeadResponse Pydantic schemas — Pydantic v2 raises ValidationError if we
        # pass None.  Coerce to "" so a single corrupted record never aborts the
        # entire ThreadPoolExecutor batch and crashes the list endpoint.
        # last_name is Optional[str] in the schema, so None is safe there.
        return {
            "first_name": cls.decrypt_field(lead_model.first_name_encrypted) or "",
            "last_name": cls.decrypt_field(lead_model.last_name_encrypted),  # Optional[str]
            "email": cls.decrypt_field(lead_model.email_encrypted) or "",
            "phone": cls.decrypt_field(lead_model.phone_encrypted) or "",
        }
    
    @staticmethod
    def hash_ip(ip_address: Optional[str]) -> Optional[str]:
        """
        Hash an IP address for privacy-preserving storage.
        
        Args:
            ip_address: IP address to hash
            
        Returns:
            Hashed IP address or None if input is None
        """
        if ip_address is None:
            return None
        return hash_ip_address(ip_address)
    
    @staticmethod
    def mask_email(email: str) -> str:
        """
        Mask email for logging purposes.
        
        Shows first character and domain only.
        Example: "john@example.com" -> "j***@example.com"
        
        Args:
            email: Email address to mask
            
        Returns:
            Masked email string
        """
        if not email or "@" not in email:
            return "[REDACTED]"
        
        local, domain = email.split("@", 1)
        if len(local) <= 1:
            return f"*@{domain}"
        return f"{local[0]}***@{domain}"
    
    @staticmethod
    def mask_phone(phone: str) -> str:
        """
        Mask phone number for logging purposes.
        
        Shows last 4 digits only.
        Example: "5551234567" -> "***-***-4567"
        
        Args:
            phone: Phone number to mask
            
        Returns:
            Masked phone string
        """
        if not phone or len(phone) < 4:
            return "[REDACTED]"
        
        return f"***-***-{phone[-4:]}"
    
    @staticmethod
    def mask_name(name: Optional[str]) -> str:
        """
        Mask name for logging purposes.
        
        Shows first initial only.
        Example: "John" -> "J***"
        
        Args:
            name: Name to mask
            
        Returns:
            Masked name string
        """
        if not name:
            return "[REDACTED]"
        
        return f"{name[0]}***"
