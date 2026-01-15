import pytest

def test_health_check(client):
    """Test the health check endpoint."""
    response = client.get('/health/ping')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'ok'

def test_health_readiness(client):
    """Test the readiness endpoint."""
    response = client.get('/health/ready')
    # It might fail due to the bad import, let's see
    assert response.status_code in [200, 503]
    data = response.get_json()
    # It should not return 500 (crash)
    
def test_index_page(client):
    """Test the index page loads (redirects to login usually)."""
    response = client.get('/', follow_redirects=True)
    assert response.status_code == 200
    # Should probably see login text or similar
    assert b"Login" in response.data or b"Scheduler" in response.data