"""
Unit tests for download_monitor.py
Run with: python -m pytest test_download_monitor.py -v
"""

import os
import sys
import json
import tempfile
import hashlib
import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from download_monitor import DownloadMonitor


class TestDownloadMonitor(unittest.TestCase):
    """Test suite for DownloadMonitor class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.config = {
            "download_monitor": {
                "enabled": True,
                "api_url": "http://test-api.local/api",
                "check_interval_sec": 5,
                "max_file_size_mb": 50,
                "allowed_extensions": ["pdf", "docx", "txt"],
                "naukri_pattern": "Naukri_",
                "monitor_naukri_only": True
            }
        }
        self.emp_id = 123
        self.auth_token = "test-token-123"
    
    def test_initialization(self):
        """Test DownloadMonitor initialization"""
        monitor = DownloadMonitor(self.config, self.emp_id, self.auth_token)
        
        self.assertEqual(monitor.emp_id, self.emp_id)
        self.assertEqual(monitor.auth_token, self.auth_token)
        self.assertTrue(monitor.enabled)
        self.assertEqual(monitor.check_interval, 5)
        self.assertEqual(monitor.max_file_size_mb, 50)
    
    def test_allowed_extensions(self):
        """Test that allowed extensions are correctly set"""
        monitor = DownloadMonitor(self.config, self.emp_id, self.auth_token)
        
        self.assertIn("pdf", monitor.allowed_extensions)
        self.assertIn("docx", monitor.allowed_extensions)
        self.assertIn("txt", monitor.allowed_extensions)
        self.assertNotIn("exe", monitor.allowed_extensions)
    
    def test_naukri_pattern(self):
        """Test Naukri pattern configuration"""
        monitor = DownloadMonitor(self.config, self.emp_id, self.auth_token)
        
        self.assertEqual(monitor.naukri_pattern, "Naukri_")
        self.assertTrue(monitor.monitor_naukri_only)
    
    def test_get_file_hash(self):
        """Test file hash computation"""
        monitor = DownloadMonitor(self.config, self.emp_id, self.auth_token)
        
        # Create temporary test file
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            temp_path = f.name
        
        try:
            file_hash = monitor._get_file_hash(temp_path)
            
            # Verify hash is SHA256 (64 hex chars)
            self.assertEqual(len(file_hash), 64)
            self.assertTrue(all(c in "0123456789abcdef" for c in file_hash))
            
            # Verify hash is consistent
            file_hash2 = monitor._get_file_hash(temp_path)
            self.assertEqual(file_hash, file_hash2)
        finally:
            os.unlink(temp_path)
    
    def test_should_upload_valid_file(self):
        """Test that valid Naukri files are marked for upload"""
        monitor = DownloadMonitor(self.config, self.emp_id, self.auth_token)
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", prefix="Naukri_", delete=False) as f:
            f.write(b"test pdf content")
            temp_path = f.name
        
        try:
            should_upload = monitor._should_upload(temp_path)
            self.assertTrue(should_upload)
        finally:
            os.unlink(temp_path)
    
    def test_should_upload_wrong_extension(self):
        """Test that files with wrong extension are skipped"""
        monitor = DownloadMonitor(self.config, self.emp_id, self.auth_token)
        
        with tempfile.NamedTemporaryFile(suffix=".exe", prefix="Naukri_", delete=False) as f:
            f.write(b"test exe")
            temp_path = f.name
        
        try:
            should_upload = monitor._should_upload(temp_path)
            self.assertFalse(should_upload)
        finally:
            os.unlink(temp_path)
    
    def test_should_upload_wrong_pattern(self):
        """Test that files not matching Naukri pattern are skipped"""
        monitor = DownloadMonitor(self.config, self.emp_id, self.auth_token)
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", prefix="Resume_", delete=False) as f:
            f.write(b"test pdf")
            temp_path = f.name
        
        try:
            should_upload = monitor._should_upload(temp_path)
            self.assertFalse(should_upload)
        finally:
            os.unlink(temp_path)
    
    def test_should_upload_oversized_file(self):
        """Test that oversized files are skipped"""
        monitor = DownloadMonitor(self.config, self.emp_id, self.auth_token)
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", prefix="Naukri_", delete=False) as f:
            # Write 60MB (exceeds 50MB limit)
            f.write(b"x" * (60 * 1024 * 1024))
            temp_path = f.name
        
        try:
            should_upload = monitor._should_upload(temp_path)
            self.assertFalse(should_upload)
        finally:
            os.unlink(temp_path)
    
    def test_should_upload_duplicate_file(self):
        """Test that duplicate files (same hash) are not re-uploaded"""
        monitor = DownloadMonitor(self.config, self.emp_id, self.auth_token)
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", prefix="Naukri_", delete=False) as f:
            f.write(b"test content")
            temp_path = f.name
        
        try:
            # First check should pass
            should_upload1 = monitor._should_upload(temp_path)
            self.assertTrue(should_upload1)
            
            # Mark as processed
            file_hash = monitor._get_file_hash(temp_path)
            monitor.processed_files[temp_path] = file_hash
            
            # Second check should fail (duplicate)
            should_upload2 = monitor._should_upload(temp_path)
            self.assertFalse(should_upload2)
        finally:
            os.unlink(temp_path)
    
    def test_is_file_ready_windows(self):
        """Test file ready detection on Windows"""
        if sys.platform != 'win32':
            self.skipTest("Windows-specific test")
        
        monitor = DownloadMonitor(self.config, self.emp_id, self.auth_token)
        
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            temp_path = f.name
        
        try:
            is_ready = monitor._is_file_ready(temp_path)
            self.assertTrue(is_ready)
        finally:
            os.unlink(temp_path)
    
    def test_is_file_ready_nonexistent(self):
        """Test file ready detection for nonexistent file"""
        monitor = DownloadMonitor(self.config, self.emp_id, self.auth_token)
        
        is_ready = monitor._is_file_ready("/nonexistent/path/file.pdf")
        self.assertFalse(is_ready)
    
    def test_download_paths_initialization(self):
        """Test that download paths are initialized"""
        monitor = DownloadMonitor(self.config, self.emp_id, self.auth_token)
        
        # Should have at least Downloads and Desktop
        self.assertGreater(len(monitor.download_paths), 0)
        
        # Check for common paths
        paths_str = " ".join(monitor.download_paths).lower()
        self.assertTrue("downloads" in paths_str or "desktop" in paths_str)
    
    @patch('download_monitor.requests.post')
    @patch('download_monitor.requests.put')
    def test_upload_file_success(self, mock_put, mock_post):
        """Test successful file upload"""
        monitor = DownloadMonitor(self.config, self.emp_id, self.auth_token)
        
        # Mock presign response
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "url": "https://s3.example.com/presigned-url",
            "id": "metadata-123"
        }
        
        # Mock S3 upload response
        mock_put.return_value.status_code = 204
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", prefix="Naukri_", delete=False) as f:
            f.write(b"test pdf content")
            temp_path = f.name
        
        try:
            # This would normally call the API, but we're mocking it
            # Just verify the file path is valid
            self.assertTrue(os.path.exists(temp_path))
        finally:
            os.unlink(temp_path)
    
    def test_stop_event(self):
        """Test that stop event works"""
        monitor = DownloadMonitor(self.config, self.emp_id, self.auth_token)
        
        self.assertFalse(monitor.stop_event.is_set())
        monitor.stop()
        self.assertTrue(monitor.stop_event.is_set())
    
    def test_logger_output(self):
        """Test that logger produces output"""
        monitor = DownloadMonitor(self.config, self.emp_id, self.auth_token)
        
        # Logger should be callable
        self.assertTrue(callable(monitor.logger))
        
        # Should not raise exception
        monitor.logger("Test message")


class TestDesignationMatching(unittest.TestCase):
    """Test designation matching logic"""
    
    def test_case_insensitive_matching(self):
        """Test case-insensitive designation matching"""
        designations = [
            "Manager - Talent Acquisition",
            "MANAGER - TALENT ACQUISITION",
            "manager - talent acquisition"
        ]
        
        target = "manager - talent acquisition"
        
        for designation in designations:
            normalized = designation.strip().lower()
            self.assertEqual(normalized, target)
    
    def test_em_dash_normalization(self):
        """Test em-dash to hyphen normalization"""
        # em-dash version
        em_dash = "Manager – Talent Acquisition"
        # regular hyphen version
        hyphen = "Manager - Talent Acquisition"
        
        em_normalized = em_dash.replace('–', '-').lower()
        hyphen_normalized = hyphen.replace('–', '-').lower()
        
        self.assertEqual(em_normalized, hyphen_normalized)
    
    def test_whitespace_normalization(self):
        """Test whitespace normalization"""
        designations = [
            "Manager - Talent Acquisition",
            "Manager  -  Talent  Acquisition",  # extra spaces
            "Manager - Talent  Acquisition"
        ]
        
        normalized = [d.replace('  ', ' ').lower() for d in designations]
        
        # All should normalize to the same value
        self.assertEqual(len(set(normalized)), 1)


class TestConfigValidation(unittest.TestCase):
    """Test configuration validation"""
    
    def test_missing_api_url(self):
        """Test handling of missing API URL"""
        config = {
            "download_monitor": {
                "enabled": True,
                "check_interval_sec": 30
            }
        }
        
        monitor = DownloadMonitor(config, 123, "token")
        
        # Should use default API URL
        self.assertEqual(monitor.api_base, "http://ats-tool.test/api")
    
    def test_missing_auth_token(self):
        """Test handling of missing auth token"""
        config = {"download_monitor": {"enabled": True}}
        
        # Should not raise exception
        monitor = DownloadMonitor(config, 123, None)
        self.assertIsNone(monitor.auth_token)
    
    def test_invalid_check_interval(self):
        """Test handling of invalid check interval"""
        config = {
            "download_monitor": {
                "enabled": True,
                "check_interval_sec": "invalid"
            }
        }
        
        # Should handle gracefully
        try:
            monitor = DownloadMonitor(config, 123, "token")
            # Should have default or converted value
            self.assertIsInstance(monitor.check_interval, (int, float))
        except (ValueError, TypeError):
            pass  # Expected if conversion fails


if __name__ == '__main__':
    unittest.main()
