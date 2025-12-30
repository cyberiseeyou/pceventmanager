"""
API Routes for Paperwork Template Management
==============================================

Handles CRUD operations for paperwork templates including:
- List all templates
- Create new template
- Update template (name, order, active status)
- Delete template
- Reorder templates
- Upload template file
"""

from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
import os
from datetime import datetime

api_paperwork_templates_bp = Blueprint('api_paperwork_templates', __name__, url_prefix='/api/paperwork-templates')


def allowed_file(filename):
    """Check if file has allowed extension (PDF only)"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'


@api_paperwork_templates_bp.route('/', methods=['GET'])
def get_templates():
    """
    Get all paperwork templates ordered by display_order

    Returns:
        JSON: List of templates with their properties including file_exists status
    """
    try:
        db = current_app.extensions['sqlalchemy']
        PaperworkTemplate = current_app.config['PaperworkTemplate']

        templates = PaperworkTemplate.query.order_by(PaperworkTemplate.display_order).all()

        # Get docs directory path
        docs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'docs')

        # Add file_exists flag to each template
        templates_with_status = []
        for template in templates:
            template_dict = template.to_dict()
            template_path = os.path.join(docs_dir, template.file_path)
            template_dict['file_exists'] = os.path.exists(template_path)
            templates_with_status.append(template_dict)

        return jsonify({
            'success': True,
            'templates': templates_with_status
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching templates: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_paperwork_templates_bp.route('/', methods=['POST'])
def create_template():
    """
    Create a new paperwork template

    Request Body:
        {
            "name": "Template Name",
            "description": "Optional description",
            "file_path": "filename.pdf",
            "display_order": 3,
            "is_active": true
        }

    Returns:
        JSON: Created template object
    """
    try:
        db = current_app.extensions['sqlalchemy']
        PaperworkTemplate = current_app.config['PaperworkTemplate']

        data = request.get_json()

        # Validate required fields
        if not data.get('name'):
            return jsonify({'success': False, 'error': 'Name is required'}), 400
        if not data.get('file_path'):
            return jsonify({'success': False, 'error': 'File path is required'}), 400

        # Check if name already exists
        existing = PaperworkTemplate.query.filter_by(name=data['name']).first()
        if existing:
            return jsonify({'success': False, 'error': 'Template with this name already exists'}), 400

        # Get max display_order if not provided
        display_order = data.get('display_order')
        if display_order is None:
            max_order = db.session.query(db.func.max(PaperworkTemplate.display_order)).scalar()
            display_order = (max_order or 0) + 1

        # Create new template
        template = PaperworkTemplate(
            name=data['name'],
            description=data.get('description', ''),
            file_path=data['file_path'],
            category=data.get('category', 'event'),
            display_order=display_order,
            is_active=data.get('is_active', True)
        )

        db.session.add(template)
        db.session.commit()

        return jsonify({
            'success': True,
            'template': template.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating template: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_paperwork_templates_bp.route('/<int:template_id>', methods=['PUT'])
def update_template(template_id):
    """
    Update an existing paperwork template

    Args:
        template_id: ID of template to update

    Request Body:
        {
            "name": "Updated Name",
            "description": "Updated description",
            "file_path": "updated_file.pdf",
            "display_order": 2,
            "is_active": false
        }

    Returns:
        JSON: Updated template object
    """
    try:
        db = current_app.extensions['sqlalchemy']
        PaperworkTemplate = current_app.config['PaperworkTemplate']

        template = PaperworkTemplate.query.get(template_id)
        if not template:
            return jsonify({'success': False, 'error': 'Template not found'}), 404

        data = request.get_json()

        # Update fields if provided
        if 'name' in data:
            # Check if new name already exists (excluding current template)
            existing = PaperworkTemplate.query.filter(
                PaperworkTemplate.name == data['name'],
                PaperworkTemplate.id != template_id
            ).first()
            if existing:
                return jsonify({'success': False, 'error': 'Template with this name already exists'}), 400
            template.name = data['name']

        if 'description' in data:
            template.description = data['description']
        if 'file_path' in data:
            template.file_path = data['file_path']
        if 'display_order' in data:
            template.display_order = data['display_order']
        if 'is_active' in data:
            template.is_active = data['is_active']

        template.updated_at = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'success': True,
            'template': template.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating template: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_paperwork_templates_bp.route('/<int:template_id>', methods=['DELETE'])
def delete_template(template_id):
    """
    Delete a paperwork template

    Args:
        template_id: ID of template to delete

    Returns:
        JSON: Success message
    """
    try:
        db = current_app.extensions['sqlalchemy']
        PaperworkTemplate = current_app.config['PaperworkTemplate']

        template = PaperworkTemplate.query.get(template_id)
        if not template:
            return jsonify({'success': False, 'error': 'Template not found'}), 404

        # Optionally delete the physical file
        # docs_dir = os.path.join(os.path.dirname(current_app.root_path), 'docs')
        # file_path = os.path.join(docs_dir, template.file_path)
        # if os.path.exists(file_path):
        #     os.remove(file_path)

        db.session.delete(template)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Template deleted successfully'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting template: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_paperwork_templates_bp.route('/reorder', methods=['POST'])
def reorder_templates():
    """
    Reorder templates by updating display_order

    Request Body:
        {
            "template_ids": [3, 1, 2, 4]  # Array of template IDs in desired order
        }

    Returns:
        JSON: Success message
    """
    try:
        db = current_app.extensions['sqlalchemy']
        PaperworkTemplate = current_app.config['PaperworkTemplate']

        data = request.get_json()
        template_ids = data.get('template_ids', [])

        if not template_ids:
            return jsonify({'success': False, 'error': 'template_ids array is required'}), 400

        # Update display_order for each template
        for index, template_id in enumerate(template_ids):
            template = PaperworkTemplate.query.get(template_id)
            if template:
                template.display_order = index + 1
                template.updated_at = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Templates reordered successfully'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error reordering templates: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_paperwork_templates_bp.route('/upload', methods=['POST'])
def upload_template_file():
    """
    Upload a PDF file for a paperwork template

    Form Data:
        file: PDF file to upload
        name: Template name (optional, will use filename if not provided)
        description: Template description (optional)
        overwrite: Boolean flag to allow overwriting existing files (optional)

    Returns:
        JSON: Created template object with file path, or conflict info if file exists
    """
    try:
        db = current_app.extensions['sqlalchemy']
        PaperworkTemplate = current_app.config['PaperworkTemplate']

        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Only PDF files are allowed'}), 400

        # Secure the filename
        filename = secure_filename(file.filename)

        # Save to docs directory
        docs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'docs')
        if not os.path.exists(docs_dir):
            os.makedirs(docs_dir)

        file_path = os.path.join(docs_dir, filename)

        # Check if overwrite is allowed
        overwrite = request.form.get('overwrite', '').lower() == 'true'

        # Check if file already exists
        if os.path.exists(file_path) and not overwrite:
            # Find existing template record if any
            existing_template = PaperworkTemplate.query.filter_by(file_path=filename).first()

            return jsonify({
                'success': False,
                'conflict': True,
                'filename': filename,
                'existing_template': existing_template.to_dict() if existing_template else None,
                'message': f'File {filename} already exists. Would you like to overwrite it?'
            }), 409  # 409 Conflict status code

        # Save the file (overwrites if exists and overwrite=true)
        file.save(file_path)

        # Get template name from form or use filename
        template_name = request.form.get('name', filename.rsplit('.', 1)[0])
        template_description = request.form.get('description', '')
        template_category = request.form.get('category', 'event')  # Default to 'event'

        # Check if template with this file_path already exists (when overwriting)
        existing_by_file = PaperworkTemplate.query.filter_by(file_path=filename).first()

        if existing_by_file and overwrite:
            # Update existing template record
            existing_by_file.updated_at = datetime.utcnow()
            # Optionally update name and description if provided and different
            if request.form.get('name'):
                existing_by_file.name = template_name
            if request.form.get('description'):
                existing_by_file.description = template_description

            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'File overwritten successfully',
                'template': existing_by_file.to_dict(),
                'overwritten': True
            }), 200

        # Check if template with this name already exists (for new uploads)
        existing_by_name = PaperworkTemplate.query.filter_by(name=template_name).first()
        if existing_by_name:
            # Delete uploaded file since template name exists
            os.remove(file_path)
            return jsonify({
                'success': False,
                'error': f'Template with name "{template_name}" already exists'
            }), 400

        # Get next display order
        max_order = db.session.query(db.func.max(PaperworkTemplate.display_order)).scalar()
        display_order = (max_order or 0) + 1

        # Create new template record
        template = PaperworkTemplate(
            name=template_name,
            description=template_description,
            file_path=filename,  # Store relative path
            category=template_category,
            display_order=display_order,
            is_active=True
        )

        db.session.add(template)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'File uploaded successfully',
            'template': template.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error uploading file: {str(e)}")

        # Try to clean up uploaded file if exists
        try:
            if 'filename' in locals() and 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass

        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
