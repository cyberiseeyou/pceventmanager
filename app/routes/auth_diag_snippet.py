
@auth_bp.route('/api/auth/diag')
def auth_diag():
    """Diagnostic endpoint to check Redis connection"""
    status = {
        'redis': 'unknown',
        'env_redis_url_set': bool(current_app.config.get('REDIS_URL')),
        'env_redis_password_set': bool(current_app.config.get('REDIS_PASSWORD')),
        'error': None
    }
    
    try:
        client = get_redis_client()
        client.ping()
        status['redis'] = 'connected'
    except Exception as e:
        status['redis'] = 'failed'
        status['error'] = str(e)
        
    return jsonify(status)
