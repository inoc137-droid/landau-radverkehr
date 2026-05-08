import json
import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# Import the module to test
import monitor


class TestFetchErrorHandling(unittest.TestCase):
    """Test that fetch handles HTTP errors gracefully"""

    @patch('monitor.requests.get')
    def test_fetch_500_error_returns_none(self, mock_get):
        """Test that 500 error returns None instead of raising"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("500 Server Error")
        mock_get.return_value = mock_response
        
        result = monitor.fetch("https://example.com")
        assert result is None, "fetch should return None on HTTP error"

    @patch('monitor.requests.get')
    def test_fetch_success_returns_response(self, mock_get):
        """Test that successful requests return the response"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = monitor.fetch("https://example.com")
        assert result is not None, "fetch should return response on success"
        assert result.status_code == 200

    @patch('monitor.fetch')
    def test_snapshot_handles_failed_fetch(self, mock_fetch):
        """Test that snapshot handles failed fetches gracefully"""
        mock_fetch.return_value = None
        
        result = monitor.snapshot()
        
        # Should have entries for all targets
        assert len(result) == len(monitor.TARGETS), "snapshot should have entries for all targets"
        
        # Failed fetch should result in error entry
        for item in result.values():
            if item.get("type") == "error":
                assert item["status_code"] is None
                assert "error" in item
                return
        
        # At least one should be an error since we mocked all to fail
        self.fail("snapshot should include error entries for failed fetches")


if __name__ == "__main__":
    unittest.main()
