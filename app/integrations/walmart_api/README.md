# Walmart Retail Link API Integration

A Flask-based REST API for integrating with Walmart's Retail Link Event Management System. This module provides secure, session-based access to Walmart's Event Detail Reports (EDR) and related data.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [API Endpoints](#api-endpoints)
- [Usage Examples](#usage-examples)
- [Session Management](#session-management)
- [Error Handling](#error-handling)
- [Security](#security)
- [Development](#development)

## Overview

This module provides a clean separation between Walmart's Retail Link systems and Crossmark's internal scheduling application. It handles:

- **Multi-factor authentication** with Walmart Retail Link
- **Session management** with automatic timeout and refresh
- **EDR data retrieval** for individual or batch events
- **PDF generation** for event documentation
- **User isolation** with per-user session tracking

## Features

- ✅ **Separate Authentication Flow**: Authentication is independent of data operations
- ✅ **Session Reusability**: One authentication session supports multiple operations
- ✅ **Auto-Refresh Sessions**: 10-minute timeout that refreshes on activity
- ✅ **Thread-Safe**: Concurrent user sessions with proper locking
- ✅ **User Isolation**: Each user maintains their own Walmart session
- ✅ **Comprehensive Logging**: Full audit trail of all operations
- ✅ **Error Handling**: Detailed error responses with proper HTTP status codes
- ✅ **PDF Generation**: Automated EDR report generation
- ✅ **Batch Operations**: Download multiple EDRs in a single request

## Architecture

### Module Structure

```
scheduler_app/walmart_api/
├── __init__.py              # Module initialization and exports
├── routes.py                # Flask Blueprint with API endpoints
├── session_manager.py       # User session management
├── authenticator.py         # Walmart authentication logic
├── pdf_generator.py         # PDF generation for EDR reports
└── README.md               # This file
```

### Component Responsibilities

#### `routes.py`
- Flask Blueprint registration (`/api/walmart/*`)
- Endpoint handlers for authentication and data retrieval
- Request validation and response formatting
- Integration with Flask-Login for user authentication

#### `session_manager.py`
- `WalmartSession`: Individual user session with timeout tracking
- `WalmartSessionManager`: Global session storage and cleanup
- Thread-safe session operations
- Automatic timeout and refresh logic

#### `authenticator.py`
- Multi-step Walmart authentication flow
- MFA code handling
- Auth token management
- EDR data retrieval from Walmart API

#### `pdf_generator.py`
- EDR data formatting
- PDF document generation
- Event detail tables
- Signature sections

## Installation

### Prerequisites

- Python 3.8+
- Flask 2.0+
- Flask-Login
- Playwright (for browser automation)
- ReportLab (for PDF generation)

### Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Install Playwright Browsers**:
   ```bash
   playwright install chromium
   ```

3. **Configure Environment Variables** (see Configuration section)

4. **Register Blueprint** in your Flask app:
   ```python
   from scheduler_app.walmart_api import walmart_bp

   app.register_blueprint(walmart_bp)
   ```

## Configuration

Add the following to your Flask application configuration:

### Environment Variables

```bash
# Walmart Retail Link Credentials
WALMART_EDR_USERNAME="your.email@company.com"
WALMART_EDR_PASSWORD="your_password"
WALMART_EDR_MFA_CREDENTIAL_ID="your_credential_id"

# Upload folder for PDFs
UPLOAD_FOLDER="uploads"
```

### Flask Config (config.py)

```python
import os

class Config:
    # Walmart API Configuration
    WALMART_EDR_USERNAME = os.environ.get('WALMART_EDR_USERNAME')
    WALMART_EDR_PASSWORD = os.environ.get('WALMART_EDR_PASSWORD')
    WALMART_EDR_MFA_CREDENTIAL_ID = os.environ.get('WALMART_EDR_MFA_CREDENTIAL_ID')

    # Upload configuration
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
```

### Finding Your MFA Credential ID

1. Log in to Walmart Retail Link
2. Open browser developer tools (F12)
3. Go to Network tab
4. Complete MFA authentication
5. Find the `/mfa/send-code` request
6. Look for the `credentialId` parameter in the request payload

## API Endpoints

### Base URL
All endpoints are prefixed with `/api/walmart`

### Authentication Endpoints

#### 1. Request MFA Code
```http
POST /api/walmart/auth/request-mfa
```

**Description**: Initiates authentication and sends MFA code to registered phone.

**Authentication**: Requires Flask-Login session

**Response**:
```json
{
  "success": true,
  "message": "MFA code sent to registered phone",
  "session_info": {
    "user_id": "user123",
    "created_at": "2025-10-05T12:00:00",
    "expires_at": "2025-10-05T12:10:00",
    "time_remaining_seconds": 600,
    "is_authenticated": false
  }
}
```

#### 2. Complete Authentication
```http
POST /api/walmart/auth/authenticate
Content-Type: application/json

{
  "mfa_code": "123456"
}
```

**Description**: Completes authentication with MFA code.

**Authentication**: Requires Flask-Login session and active Walmart session

**Response**:
```json
{
  "success": true,
  "message": "Authentication successful",
  "session_info": {
    "user_id": "user123",
    "is_authenticated": true,
    "time_remaining_seconds": 600
  }
}
```

#### 3. Logout
```http
POST /api/walmart/auth/logout
```

**Description**: Ends the Walmart session.

**Response**:
```json
{
  "success": true,
  "message": "Logged out successfully"
}
```

#### 4. Session Status
```http
GET /api/walmart/auth/session-status
```

**Description**: Checks current session status.

**Response** (with active session):
```json
{
  "has_session": true,
  "session_info": {
    "user_id": "user123",
    "created_at": "2025-10-05T12:00:00",
    "last_activity": "2025-10-05T12:05:00",
    "expires_at": "2025-10-05T12:15:00",
    "is_authenticated": true,
    "time_remaining_seconds": 300
  }
}
```

### EDR Data Endpoints

#### 5. Get Single EDR
```http
GET /api/walmart/edr/<event_id>
```

**Description**: Retrieves EDR data for a specific event.

**Authentication**: Requires authenticated Walmart session

**Response**:
```json
{
  "success": true,
  "event_id": "12345",
  "edr_data": {
    "demoId": "12345",
    "demoName": "Product Demo Event",
    "demoDate": "2025-10-05",
    "itemDetails": [...]
  }
}
```

#### 6. Batch Download EDRs
```http
POST /api/walmart/edr/batch-download
Content-Type: application/json

{
  "date": "2025-10-05"
}
```

**Or**:

```json
{
  "event_ids": ["12345", "12346", "12347"]
}
```

**Description**: Downloads and generates PDFs for multiple events.

**Response**:
```json
{
  "success": true,
  "total": 3,
  "successful": 2,
  "failed": 1,
  "results": [
    {
      "event_id": "12345",
      "success": true,
      "filename": "EDR_12345_John_Doe.pdf",
      "employee_name": "John Doe"
    },
    {
      "event_id": "12346",
      "success": false,
      "error": "EDR data not found"
    }
  ],
  "output_directory": "uploads/walmart_edrs/20251005"
}
```

### Utility Endpoints

#### 7. Health Check
```http
GET /api/walmart/health
```

**Description**: Service health check (no authentication required).

**Response**:
```json
{
  "status": "healthy",
  "walmart_configured": true,
  "active_sessions": 3
}
```

## Usage Examples

### Example 1: Download EDRs for a Specific Date

```python
import requests

# Assuming you're logged into the main app
session = requests.Session()

# Step 1: Request MFA code
response = session.post('http://localhost:5000/api/walmart/auth/request-mfa')
print(response.json())
# Output: {"success": true, "message": "MFA code sent to registered phone"}

# Step 2: Wait for SMS, then authenticate
mfa_code = input("Enter MFA code: ")
response = session.post(
    'http://localhost:5000/api/walmart/auth/authenticate',
    json={'mfa_code': mfa_code}
)
print(response.json())
# Output: {"success": true, "message": "Authentication successful"}

# Step 3: Download EDRs for a date
response = session.post(
    'http://localhost:5000/api/walmart/edr/batch-download',
    json={'date': '2025-10-05'}
)
print(response.json())
# Output: {"success": true, "total": 5, "successful": 5, "failed": 0, ...}

# Step 4: Logout
response = session.post('http://localhost:5000/api/walmart/auth/logout')
```

### Example 2: Get Single EDR

```python
import requests

session = requests.Session()

# Authenticate (steps 1-2 from Example 1)
# ...

# Get specific EDR
event_id = "12345"
response = session.get(f'http://localhost:5000/api/walmart/edr/{event_id}')
data = response.json()

if data['success']:
    edr = data['edr_data']
    print(f"Event: {edr['demoName']}")
    print(f"Date: {edr['demoDate']}")
    print(f"Items: {len(edr['itemDetails'])}")
```

### Example 3: Check Session Status

```python
import requests

session = requests.Session()

# Check status
response = session.get('http://localhost:5000/api/walmart/auth/session-status')
status = response.json()

if status['has_session']:
    info = status['session_info']
    print(f"Session expires in {info['time_remaining_seconds']} seconds")
    print(f"Authenticated: {info['is_authenticated']}")
else:
    print("No active session")
```

## Session Management

### Session Lifecycle

1. **Creation**: When user requests MFA code
2. **Authentication**: After MFA code validation
3. **Active Use**: Session refreshes on every API call
4. **Expiration**: After 10 minutes of inactivity
5. **Cleanup**: Automatic removal of expired sessions

### Session Timeout

- **Duration**: 10 minutes
- **Refresh**: Automatic on any endpoint call
- **Expiration**: Automatic after timeout
- **Manual End**: Via logout endpoint

### Session Cleanup

The session manager periodically cleans up expired sessions. To enable automatic cleanup:

```python
from scheduler_app.walmart_api import session_manager
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(
    func=session_manager.cleanup_expired_sessions,
    trigger="interval",
    minutes=1
)
scheduler.start()
```

## Error Handling

### HTTP Status Codes

- `200 OK`: Request successful
- `400 Bad Request`: Invalid request parameters
- `401 Unauthorized`: Invalid authentication
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

### Error Response Format

```json
{
  "success": false,
  "message": "Detailed error message",
  "error": "Error type (optional)"
}
```

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| No active session | Session expired or not created | Request new MFA code |
| Session not authenticated | MFA not completed | Complete authentication with MFA code |
| Invalid MFA code | Wrong code entered | Check SMS and retry |
| EDR data not found | Event doesn't exist in Walmart | Verify event ID |
| Configuration missing | Credentials not set | Add environment variables |

## Security

### Authentication Layers

1. **Flask-Login**: User must be logged into main application
2. **Walmart Session**: User must have active Walmart session
3. **MFA**: Multi-factor authentication required

### Session Security

- ✅ User-isolated sessions (no cross-user access)
- ✅ Automatic timeout after inactivity
- ✅ Thread-safe session storage
- ✅ Credentials never exposed in responses
- ✅ Sessions stored in memory (not persistent)

### Best Practices

1. **Use HTTPS** in production
2. **Rotate credentials** regularly
3. **Monitor session activity** via logs
4. **Implement rate limiting** on authentication endpoints
5. **Set strong passwords** for Walmart account

## Development

### Running Tests

```bash
# Test authentication
pytest tests/test_walmart_auth.py

# Test session management
pytest tests/test_walmart_sessions.py

# Test EDR retrieval
pytest tests/test_walmart_edr.py
```

### Logging

All operations are logged. To view logs:

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('scheduler_app.walmart_api')
```

### Adding New Endpoints

To add a new Walmart operation:

1. **Add method to `authenticator.py`**:
   ```python
   def get_inventory_data(self, item_id):
       # Implementation
       pass
   ```

2. **Add endpoint to `routes.py`**:
   ```python
   @walmart_bp.route('/inventory/<item_id>', methods=['GET'])
   @login_required
   def get_inventory(item_id):
       session = session_manager.get_session(str(current_user.id))
       # ... validate session ...
       data = session.authenticator.get_inventory_data(item_id)
       return jsonify({'success': True, 'data': data})
   ```

3. **Update documentation**

### Debugging

Enable debug logging:

```python
import logging

logging.getLogger('scheduler_app.walmart_api').setLevel(logging.DEBUG)
```

Common debug scenarios:

```python
# Check active sessions
from scheduler_app.walmart_api import session_manager
print(f"Active sessions: {session_manager.get_active_session_count()}")

# Get session details
session_info = session_manager.get_session_info('user123')
print(session_info)

# Manual cleanup
session_manager.cleanup_expired_sessions()
```

## Troubleshooting

### Issue: "Configuration missing"

**Cause**: Walmart credentials not configured

**Solution**: Set environment variables:
```bash
export WALMART_EDR_USERNAME="your.email@company.com"
export WALMART_EDR_PASSWORD="your_password"
export WALMART_EDR_MFA_CREDENTIAL_ID="your_credential_id"
```

### Issue: "MFA code request failed"

**Cause**: Invalid credentials or Walmart system issue

**Solution**:
1. Verify credentials are correct
2. Try logging in manually to Walmart Retail Link
3. Check logs for detailed error

### Issue: "Session expired"

**Cause**: 10 minutes of inactivity

**Solution**: Request new MFA code and re-authenticate

### Issue: "EDR data not found"

**Cause**: Event doesn't exist or is not accessible

**Solution**:
1. Verify event ID is correct
2. Check if event exists in Walmart system
3. Ensure you have access to the event

## Version History

- **1.0.0** (2025-10-05): Initial release
  - Multi-factor authentication
  - Session management with auto-refresh
  - EDR data retrieval
  - Batch PDF generation
  - Health check endpoint

## License

Internal use only - Crossmark Schedule Management System

## Support

For issues or questions:
1. Check this documentation
2. Review application logs
3. Contact the development team
