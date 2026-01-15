"""
Shift Block Settings API Endpoints
Manages the 8 active shift blocks for Core event scheduling
"""
from flask import Blueprint, request, jsonify, current_app
from app.routes.auth import require_authentication
import logging

logger = logging.getLogger(__name__)

api_shift_blocks_bp = Blueprint('api_shift_blocks', __name__, url_prefix='/api/shift-blocks')


@api_shift_blocks_bp.route('/', methods=['GET'])
@require_authentication()
def get_all_shift_blocks():
    """
    Get all 8 shift blocks configuration.

    Priority:
    1. Database values (if they exist)
    2. Environment variables from .env (for display only, not persisted)
    3. Empty values

    Returns:
        JSON with all shift blocks and a 'source' field indicating data origin
    """
    ShiftBlockSetting = current_app.config.get('ShiftBlockSetting')

    if not ShiftBlockSetting:
        return jsonify({
            'success': False,
            'error': 'ShiftBlockSetting model not available'
        }), 500

    try:
        # First, try to get from database
        blocks = ShiftBlockSetting.get_all_blocks()

        # If database has all 8 blocks, return them
        if blocks and len(blocks) >= 8:
            return jsonify({
                'success': True,
                'blocks': [block.to_json() for block in blocks],
                'source': 'database'
            })

        # Otherwise, get defaults from .env for display (without persisting)
        from app.services.shift_block_config import ShiftBlockConfig
        env_blocks = ShiftBlockConfig.get_all_blocks_from_env()

        if env_blocks:
            # Convert to JSON format matching database structure
            blocks_json = []
            for block in env_blocks:
                blocks_json.append({
                    'block': block['block'],
                    'arrive': block['arrive_str'],
                    'on_floor': block['on_floor_str'],
                    'lunch_begin': block['lunch_begin_str'],
                    'lunch_end': block['lunch_end_str'],
                    'off_floor': block['off_floor_str'],
                    'depart': block['depart_str'],
                    'is_active': True,
                    'updated_at': None,
                    'updated_by': None
                })

            logger.info(f"Returning {len(env_blocks)} shift blocks from .env (not yet saved to database)")
            return jsonify({
                'success': True,
                'blocks': blocks_json,
                'source': 'environment'
            })

        # If no .env values either, return empty blocks
        logger.warning("No shift blocks found in database or .env")
        return jsonify({
            'success': True,
            'blocks': [],
            'source': 'none'
        })

    except Exception as e:
        logger.error(f"Error fetching shift blocks: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_shift_blocks_bp.route('/<int:block_number>', methods=['GET'])
@require_authentication()
def get_shift_block(block_number):
    """
    Get a specific shift block.

    Args:
        block_number: Block number 1-8

    Returns:
        JSON with shift block data
    """
    if not 1 <= block_number <= 8:
        return jsonify({
            'success': False,
            'error': 'Block number must be between 1 and 8'
        }), 400

    ShiftBlockSetting = current_app.config.get('ShiftBlockSetting')

    if not ShiftBlockSetting:
        return jsonify({
            'success': False,
            'error': 'ShiftBlockSetting model not available'
        }), 500

    try:
        block = ShiftBlockSetting.get_block(block_number)

        if not block:
            return jsonify({
                'success': False,
                'error': f'Block {block_number} not found'
            }), 404

        return jsonify({
            'success': True,
            'block': block.to_json()
        })

    except Exception as e:
        logger.error(f"Error fetching shift block {block_number}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_shift_blocks_bp.route('/<int:block_number>', methods=['PUT'])
@require_authentication()
def update_shift_block(block_number):
    """
    Update a specific shift block.

    Args:
        block_number: Block number 1-8

    Request Body:
        {
            "arrive": "10:15",
            "on_floor": "10:30",
            "lunch_begin": "12:30",
            "lunch_end": "13:00",
            "off_floor": "16:30",
            "depart": "16:45"
        }

    Returns:
        JSON with updated shift block
    """
    if not 1 <= block_number <= 8:
        return jsonify({
            'success': False,
            'error': 'Block number must be between 1 and 8'
        }), 400

    ShiftBlockSetting = current_app.config.get('ShiftBlockSetting')

    if not ShiftBlockSetting:
        return jsonify({
            'success': False,
            'error': 'ShiftBlockSetting model not available'
        }), 500

    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400

        # Validate required fields
        required_fields = ['arrive', 'on_floor', 'lunch_begin', 'lunch_end', 'off_floor', 'depart']
        missing = [f for f in required_fields if f not in data]

        if missing:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing)}'
            }), 400

        # Validate time format (HH:MM)
        for field in required_fields:
            time_str = data[field]
            if not validate_time_format(time_str):
                return jsonify({
                    'success': False,
                    'error': f'Invalid time format for {field}: {time_str}. Use HH:MM format.'
                }), 400

        # Update the block
        block = ShiftBlockSetting.set_block(
            block_number=block_number,
            arrive=data['arrive'],
            on_floor=data['on_floor'],
            lunch_begin=data['lunch_begin'],
            lunch_end=data['lunch_end'],
            off_floor=data['off_floor'],
            depart=data['depart'],
            user='admin'  # TODO: Get from session
        )

        # Clear the ShiftBlockConfig cache so it picks up changes
        from app.services.shift_block_config import ShiftBlockConfig
        ShiftBlockConfig.clear_cache()

        logger.info(f"Updated shift block {block_number}")

        return jsonify({
            'success': True,
            'message': f'Block {block_number} updated successfully',
            'block': block.to_json()
        })

    except Exception as e:
        logger.error(f"Error updating shift block {block_number}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_shift_blocks_bp.route('/', methods=['PUT'])
@require_authentication()
def update_all_shift_blocks():
    """
    Update all 8 shift blocks at once.

    Request Body:
        {
            "blocks": [
                {"block": 1, "arrive": "10:15", ...},
                {"block": 2, "arrive": "10:15", ...},
                ...
            ]
        }

    Returns:
        JSON with all updated shift blocks
    """
    ShiftBlockSetting = current_app.config.get('ShiftBlockSetting')

    if not ShiftBlockSetting:
        return jsonify({
            'success': False,
            'error': 'ShiftBlockSetting model not available'
        }), 500

    try:
        data = request.get_json()

        if not data or 'blocks' not in data:
            return jsonify({
                'success': False,
                'error': 'No blocks data provided'
            }), 400

        blocks_data = data['blocks']

        if not isinstance(blocks_data, list):
            return jsonify({
                'success': False,
                'error': 'blocks must be an array'
            }), 400

        # Validate all blocks first
        required_fields = ['arrive', 'on_floor', 'lunch_begin', 'lunch_end', 'off_floor', 'depart']

        for block_data in blocks_data:
            block_num = block_data.get('block')
            if not block_num or not 1 <= block_num <= 8:
                return jsonify({
                    'success': False,
                    'error': f'Invalid block number: {block_num}'
                }), 400

            missing = [f for f in required_fields if f not in block_data]
            if missing:
                return jsonify({
                    'success': False,
                    'error': f'Block {block_num} missing fields: {", ".join(missing)}'
                }), 400

            for field in required_fields:
                if not validate_time_format(block_data[field]):
                    return jsonify({
                        'success': False,
                        'error': f'Block {block_num}: Invalid time format for {field}'
                    }), 400

        # Update all blocks
        updated_blocks = []
        for block_data in blocks_data:
            block = ShiftBlockSetting.set_block(
                block_number=block_data['block'],
                arrive=block_data['arrive'],
                on_floor=block_data['on_floor'],
                lunch_begin=block_data['lunch_begin'],
                lunch_end=block_data['lunch_end'],
                off_floor=block_data['off_floor'],
                depart=block_data['depart'],
                user='admin'
            )
            updated_blocks.append(block.to_json())

        # Clear the ShiftBlockConfig cache
        from app.services.shift_block_config import ShiftBlockConfig
        ShiftBlockConfig.clear_cache()

        logger.info(f"Updated {len(updated_blocks)} shift blocks")

        return jsonify({
            'success': True,
            'message': f'Updated {len(updated_blocks)} shift blocks',
            'blocks': updated_blocks
        })

    except Exception as e:
        logger.error(f"Error updating shift blocks: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_shift_blocks_bp.route('/initialize', methods=['POST'])
@require_authentication()
def initialize_from_env():
    """
    Initialize shift blocks from environment variables.
    Useful for initial setup or resetting to defaults.

    Request Body:
        {
            "force": false  // If true, overwrite existing blocks
        }

    Returns:
        JSON with initialization result
    """
    ShiftBlockSetting = current_app.config.get('ShiftBlockSetting')

    if not ShiftBlockSetting:
        return jsonify({
            'success': False,
            'error': 'ShiftBlockSetting model not available'
        }), 500

    try:
        data = request.get_json() or {}
        force = data.get('force', False)

        count = ShiftBlockSetting.initialize_from_env(force=force)

        # Clear the ShiftBlockConfig cache
        from app.services.shift_block_config import ShiftBlockConfig
        ShiftBlockConfig.clear_cache()

        if count > 0:
            return jsonify({
                'success': True,
                'message': f'Initialized {count} shift blocks from environment',
                'count': count
            })
        else:
            return jsonify({
                'success': True,
                'message': 'No blocks needed initialization (already exist or not configured in .env)',
                'count': 0
            })

    except Exception as e:
        logger.error(f"Error initializing shift blocks: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def validate_time_format(time_str):
    """
    Validate time string is in HH:MM format.

    Args:
        time_str: Time string to validate

    Returns:
        bool: True if valid, False otherwise
    """
    if not time_str or not isinstance(time_str, str):
        return False

    parts = time_str.split(':')
    if len(parts) != 2:
        return False

    try:
        hour = int(parts[0])
        minute = int(parts[1])
        return 0 <= hour <= 23 and 0 <= minute <= 59
    except ValueError:
        return False
