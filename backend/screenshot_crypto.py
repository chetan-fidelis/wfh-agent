"""
Screenshot Encryption Module for WFH Agent
Provides AES-256-GCM encryption for screenshots at rest and in transit
"""

import os
import io
import json
import base64
import hashlib
from typing import Optional, Tuple, BinaryIO
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
from PIL import Image


class ScreenshotCrypto:
    """Handles encryption/decryption of screenshot files using AES-256-GCM"""

    def __init__(self, master_key: Optional[str] = None):
        """
        Initialize screenshot encryption

        Args:
            master_key: Master encryption key (base64 or hex string).
                       If None, will be derived from machine-specific data.
        """
        self.master_key = self._derive_key(master_key)
        self.aesgcm = AESGCM(self.master_key)

    def _derive_key(self, provided_key: Optional[str] = None) -> bytes:
        """
        Derive a 256-bit encryption key

        Args:
            provided_key: Optional key provided by user

        Returns:
            32-byte encryption key
        """
        if provided_key:
            # Use provided key
            if len(provided_key) == 64:  # Hex string
                return bytes.fromhex(provided_key)
            else:  # Base64 string
                return base64.b64decode(provided_key)

        # Derive key from machine-specific data for default encryption
        # This provides basic protection at rest
        machine_id = self._get_machine_id()
        salt = b'wfh_agent_screenshot_v1'  # Static salt for consistency

        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return kdf.derive(machine_id.encode('utf-8'))

    def _get_machine_id(self) -> str:
        """Get unique machine identifier for key derivation"""
        import platform
        import socket

        # Combine multiple machine identifiers
        identifiers = [
            platform.node(),  # Hostname
            platform.machine(),  # Machine type
            socket.gethostname(),  # Network hostname
        ]

        # Try to get MAC address (most stable identifier)
        try:
            import uuid
            mac = uuid.getnode()
            identifiers.append(str(mac))
        except:
            pass

        # Hash all identifiers together
        combined = '|'.join(identifiers)
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()

    def encrypt_screenshot(self,
                          image_path: str,
                          output_path: Optional[str] = None,
                          compress: bool = True,
                          max_size: Tuple[int, int] = (1920, 1080),
                          quality: int = 75) -> Tuple[str, dict]:
        """
        Encrypt a screenshot file

        Args:
            image_path: Path to input image
            output_path: Path for encrypted output (default: image_path + '.enc')
            compress: Whether to compress image before encryption
            max_size: Maximum image dimensions (width, height)
            quality: JPEG quality (1-100)

        Returns:
            Tuple of (output_path, metadata_dict)
        """
        if output_path is None:
            output_path = image_path + '.enc'

        # Read and optionally compress image
        img_data, metadata = self._process_image(
            image_path,
            compress=compress,
            max_size=max_size,
            quality=quality
        )

        # Generate random nonce (12 bytes for GCM)
        nonce = os.urandom(12)

        # Encrypt image data
        ciphertext = self.aesgcm.encrypt(nonce, img_data, None)

        # Create encrypted file with format:
        # [4 bytes: version] [12 bytes: nonce] [N bytes: ciphertext]
        version = b'\x00\x01\x00\x00'  # Version 1.0.0

        with open(output_path, 'wb') as f:
            f.write(version)
            f.write(nonce)
            f.write(ciphertext)

        # Update metadata
        metadata['encrypted'] = True
        metadata['encryption_version'] = '1.0.0'
        metadata['encrypted_size'] = os.path.getsize(output_path)
        metadata['nonce'] = base64.b64encode(nonce).decode('utf-8')

        return output_path, metadata

    def decrypt_screenshot(self,
                          encrypted_path: str,
                          output_path: Optional[str] = None) -> str:
        """
        Decrypt an encrypted screenshot

        Args:
            encrypted_path: Path to encrypted file
            output_path: Path for decrypted output (default: removes '.enc' extension)

        Returns:
            Path to decrypted file
        """
        if output_path is None:
            if encrypted_path.endswith('.enc'):
                output_path = encrypted_path[:-4]
            else:
                output_path = encrypted_path + '.dec'

        with open(encrypted_path, 'rb') as f:
            # Read version (4 bytes)
            version = f.read(4)
            if version != b'\x00\x01\x00\x00':
                raise ValueError(f"Unsupported encryption version: {version.hex()}")

            # Read nonce (12 bytes)
            nonce = f.read(12)

            # Read ciphertext (rest of file)
            ciphertext = f.read()

        # Decrypt
        plaintext = self.aesgcm.decrypt(nonce, ciphertext, None)

        # Write decrypted image
        with open(output_path, 'wb') as f:
            f.write(plaintext)

        return output_path

    def encrypt_to_memory(self,
                         image_path: str,
                         compress: bool = True,
                         max_size: Tuple[int, int] = (1920, 1080),
                         quality: int = 75) -> Tuple[bytes, dict]:
        """
        Encrypt screenshot to memory buffer (for upload without temp files)

        Args:
            image_path: Path to input image
            compress: Whether to compress image before encryption
            max_size: Maximum image dimensions
            quality: JPEG quality

        Returns:
            Tuple of (encrypted_bytes, metadata_dict)
        """
        # Process image
        img_data, metadata = self._process_image(
            image_path,
            compress=compress,
            max_size=max_size,
            quality=quality
        )

        # Generate nonce and encrypt
        nonce = os.urandom(12)
        ciphertext = self.aesgcm.encrypt(nonce, img_data, None)

        # Create encrypted buffer
        version = b'\x00\x01\x00\x00'
        encrypted_data = version + nonce + ciphertext

        # Update metadata
        metadata['encrypted'] = True
        metadata['encryption_version'] = '1.0.0'
        metadata['encrypted_size'] = len(encrypted_data)
        metadata['nonce'] = base64.b64encode(nonce).decode('utf-8')

        return encrypted_data, metadata

    def decrypt_from_memory(self, encrypted_data: bytes) -> bytes:
        """
        Decrypt screenshot from memory buffer

        Args:
            encrypted_data: Encrypted bytes

        Returns:
            Decrypted image bytes
        """
        # Parse encrypted data
        version = encrypted_data[:4]
        if version != b'\x00\x01\x00\x00':
            raise ValueError(f"Unsupported encryption version: {version.hex()}")

        nonce = encrypted_data[4:16]
        ciphertext = encrypted_data[16:]

        # Decrypt
        plaintext = self.aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext

    def _process_image(self,
                      image_path: str,
                      compress: bool = True,
                      max_size: Tuple[int, int] = (1920, 1080),
                      quality: int = 75) -> Tuple[bytes, dict]:
        """
        Process image (compress, resize, convert format)

        Args:
            image_path: Path to input image
            compress: Whether to compress
            max_size: Maximum dimensions
            quality: JPEG quality

        Returns:
            Tuple of (image_bytes, metadata_dict)
        """
        original_size = os.path.getsize(image_path)

        if not compress:
            # Just read raw file
            with open(image_path, 'rb') as f:
                img_data = f.read()

            metadata = {
                'original_size': original_size,
                'compressed': False,
                'format': 'raw'
            }
            return img_data, metadata

        # Load and process image
        img = Image.open(image_path)
        original_dims = img.size

        # Convert RGBA to RGB if necessary
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        elif img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')

        # Resize if too large
        if img.width > max_size[0] or img.height > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Compress to JPEG in memory
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True)
        img_data = buffer.getvalue()

        compressed_size = len(img_data)
        compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0

        metadata = {
            'original_size': original_size,
            'compressed_size': compressed_size,
            'compression_ratio': round(compression_ratio, 2),
            'original_dimensions': f"{original_dims[0]}x{original_dims[1]}",
            'final_dimensions': f"{img.width}x{img.height}",
            'compressed': True,
            'format': 'jpeg',
            'quality': quality
        }

        return img_data, metadata

    @staticmethod
    def generate_master_key() -> str:
        """
        Generate a new random 256-bit master key

        Returns:
            Base64-encoded master key
        """
        key = os.urandom(32)  # 256 bits
        return base64.b64encode(key).decode('utf-8')


# Convenience functions for quick encryption/decryption
def encrypt_screenshot_file(image_path: str,
                            output_path: Optional[str] = None,
                            master_key: Optional[str] = None,
                            compress: bool = True) -> Tuple[str, dict]:
    """
    Quick function to encrypt a screenshot file

    Args:
        image_path: Path to image file
        output_path: Path for encrypted output
        master_key: Optional encryption key
        compress: Whether to compress before encryption

    Returns:
        Tuple of (encrypted_file_path, metadata)
    """
    crypto = ScreenshotCrypto(master_key)
    return crypto.encrypt_screenshot(image_path, output_path, compress=compress)


def decrypt_screenshot_file(encrypted_path: str,
                            output_path: Optional[str] = None,
                            master_key: Optional[str] = None) -> str:
    """
    Quick function to decrypt a screenshot file

    Args:
        encrypted_path: Path to encrypted file
        output_path: Path for decrypted output
        master_key: Optional decryption key

    Returns:
        Path to decrypted file
    """
    crypto = ScreenshotCrypto(master_key)
    return crypto.decrypt_screenshot(encrypted_path, output_path)


if __name__ == '__main__':
    # Test the encryption module
    print("Screenshot Encryption Module Test")
    print("=" * 50)

    # Generate a test key
    test_key = ScreenshotCrypto.generate_master_key()
    print(f"Generated Master Key: {test_key[:20]}...")

    # Initialize crypto
    crypto = ScreenshotCrypto()
    print(f"Initialized with machine-derived key")
    print(f"Machine ID: {crypto._get_machine_id()[:20]}...")

    print("\nReady for screenshot encryption!")
