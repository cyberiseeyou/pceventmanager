// Employee Management - Redesigned with MVRetail Integration

document.addEventListener('DOMContentLoaded', function () {
    loadEmployees();
    setupModalHandlers();
});

// ========================================
// Load and Display Employees
// ========================================

function loadEmployees() {
    const grid = document.getElementById('employees-grid');
    grid.innerHTML = '<div class="loading">Loading employees</div>';

    fetch('/api/employees')
        .then(response => response.json())
        .then(employees => {
            renderEmployees(employees);
        })
        .catch(error => {
            console.error('Error loading employees:', error);
            grid.innerHTML = '<div class="alert alert-error">Error loading employees. Please refresh the page.</div>';
        });
}

function renderEmployees(employees) {
    const grid = document.getElementById('employees-grid');

    if (employees.length === 0) {
        grid.innerHTML = '<p style="color: #6c757d; text-align: center; padding: 40px;">No employees found. Click "Add Employee" to get started.</p>';
        updateStatistics(employees);
        return;
    }

    grid.innerHTML = employees.map(emp => createEmployeeCard(emp)).join('');
    updateStatistics(employees);
}

function updateStatistics(employees) {
    // Calculate statistics
    const totalEmployees = employees.length;
    const juicers = employees.filter(emp => emp.job_title === 'Juicer Barista').length;
    const eventSpecialists = employees.filter(emp => emp.job_title === 'Event Specialist').length;
    const leadSpecialists = employees.filter(emp => emp.job_title === 'Lead Event Specialist').length;
    const abTrained = employees.filter(emp => emp.adult_beverage_trained).length;
    const juicerTrained = employees.filter(emp => emp.juicer_trained).length;

    // Update DOM
    document.getElementById('stat-total').textContent = totalEmployees;
    document.getElementById('stat-juicers').textContent = juicers;
    document.getElementById('stat-es').textContent = eventSpecialists;
    document.getElementById('stat-leads').textContent = leadSpecialists;
    document.getElementById('stat-ab').textContent = abTrained;
}

function getJobTitleBadgeClass(jobTitle) {
    const jobTitleMap = {
        'Lead Event Specialist': 'badge-lead-event-specialist',
        'Club Supervisor': 'badge-club-supervisor',
        'Juicer Barista': 'badge-juicer-barista',
        'Event Specialist': 'badge-event-specialist'
    };
    return jobTitleMap[jobTitle] || 'badge-event-specialist';
}

function createEmployeeCard(employee) {
    const badges = [];

    // Job title badge
    const jobTitleClass = getJobTitleBadgeClass(employee.job_title);
    badges.push(`<span class="employee-badge ${jobTitleClass}">${employee.job_title.toUpperCase()}</span>`);

    // Additional badges
    if (employee.adult_beverage_trained) {
        badges.push('<span class="employee-badge badge-ab-trained">AB TRAINED</span>');
    }
    if (employee.juicer_trained) {
        badges.push('<span class="employee-badge badge-juicer-trained">JUICER TRAINED</span>');
    }
    if (!employee.is_active) {
        badges.push('<span class="employee-badge badge-inactive">INACTIVE</span>');
    }

    const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
    const availabilityGrid = days.map(day => {
        const isAvailable = employee.weekly_availability[day];
        const cellClass = isAvailable ? 'day-available' : 'day-unavailable';
        const status = isAvailable ? 'Y' : 'N';
        return `<div class="day-cell ${cellClass}">${status}</div>`;
    }).join('');

    return `
        <div class="employee-card" data-employee-id="${employee.id}">
            <div class="employee-header">
                <div>
                    <h3 class="employee-name">${employee.name}</h3>
                    ${employee.id ? `<div class="employee-id">ID: ${employee.id}</div>` : ''}
                </div>
                <div>${badges.join(' ')}</div>
            </div>

            ${employee.email || employee.phone ? `
            <div style="margin: 10px 0; font-size: 14px; color: #6c757d;">
                ${employee.email ? `<div>📧 ${employee.email}</div>` : ''}
                ${employee.phone ? `<div>📞 ${employee.phone}</div>` : ''}
            </div>
            ` : ''}

            <h4 style="margin-top: 15px; margin-bottom: 10px; color: var(--primary-color); font-size: 14px;">Weekly Availability</h4>
            <div class="availability-grid">
                <div class="day-cell day-header">Mon</div>
                <div class="day-cell day-header">Tue</div>
                <div class="day-cell day-header">Wed</div>
                <div class="day-cell day-header">Thu</div>
                <div class="day-cell day-header">Fri</div>
                <div class="day-cell day-header">Sat</div>
                <div class="day-cell day-header">Sun</div>
                ${availabilityGrid}
            </div>

            <div class="employee-actions">
                <div class="employee-actions-left">
                    <button type="button" class="btn btn-small btn-primary" onclick="editEmployee('${employee.id}')">Edit</button>
                    <button type="button" class="btn btn-small btn-secondary" onclick="toggleEmployeeStatus('${employee.id}', ${!employee.is_active})">
                        ${employee.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                    <button type="button" class="btn btn-small btn-danger" onclick="deleteEmployee('${employee.id}')">Delete</button>
                </div>
            </div>
        </div>
    `;
}

// ========================================
// Modal Handlers
// ========================================

function setupModalHandlers() {
    // Add Employee button
    document.getElementById('add-employee-btn').addEventListener('click', openAddEmployeeModal);

    // Import Employees button
    document.getElementById('import-employees-btn').addEventListener('click', openImportEmployeesModal);

    // Add Employee form submission
    document.getElementById('add-employee-form').addEventListener('submit', handleAddEmployeeSubmit);

    // Close modal when clicking outside
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', function (e) {
            if (e.target === this) {
                closeAddEmployeeModal();
                closeImportEmployeesModal();
            }
        });
    });
}

// ========================================
// Add Employee Modal
// ========================================

function openAddEmployeeModal() {
    document.getElementById('add-employee-modal').classList.add('modal-open');
    document.getElementById('modal-alerts').innerHTML = '';

    // Reset form if not editing
    const form = document.getElementById('add-employee-form');
    if (!form.dataset.editingEmployeeId) {
        form.reset();
        document.getElementById('is-active').checked = true;

        // Check all availability by default
        ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].forEach(day => {
            document.getElementById(`avail-${day}`).checked = true;
        });

        // Set modal title to "Add New Employee"
        document.querySelector('#add-employee-modal .modal-header h2').textContent = 'Add New Employee';
    }
}

function closeAddEmployeeModal() {
    document.getElementById('add-employee-modal').classList.remove('modal-open');
    const form = document.getElementById('add-employee-form');
    delete form.dataset.editingEmployeeId;
    form.reset();
}

async function handleAddEmployeeSubmit(e) {
    e.preventDefault();

    const form = e.target;
    const modalAlerts = document.getElementById('modal-alerts');
    modalAlerts.innerHTML = '';

    const employeeIdInput = document.getElementById('employee-id').value.trim();
    const employeeName = document.getElementById('employee-name').value.trim();

    if (!employeeName) {
        showModalAlert('Employee name is required', 'error');
        return;
    }

    const formData = {
        id: employeeIdInput || null,
        name: employeeName,
        email: document.getElementById('employee-email').value.trim() || null,
        phone: document.getElementById('employee-phone').value.trim() || null,
        job_title: document.getElementById('job-title').value,
        is_active: document.getElementById('is-active').checked,
        adult_beverage_trained: document.getElementById('adult-beverage-trained').checked,
        juicer_trained: document.getElementById('juicer-trained').checked,
        weekly_availability: {
            monday: document.getElementById('avail-monday').checked,
            tuesday: document.getElementById('avail-tuesday').checked,
            wednesday: document.getElementById('avail-wednesday').checked,
            thursday: document.getElementById('avail-thursday').checked,
            friday: document.getElementById('avail-friday').checked,
            saturday: document.getElementById('avail-saturday').checked,
            sunday: document.getElementById('avail-sunday').checked
        }
    };

    // Check if editing
    const editingEmployeeId = form.dataset.editingEmployeeId;
    if (editingEmployeeId) {
        formData.editing_employee_id = editingEmployeeId;
    }

    try {
        const response = await fetch('/api/employees', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify(formData)
        });

        const data = await response.json();

        if (data.error) {
            showModalAlert(`Error: ${data.error}`, 'error');
            return;
        }

        // Close modal immediately
        closeAddEmployeeModal();

        // Success! Show success message
        const savedEmployeeId = data.employee_id || editingEmployeeId;
        showFlashMessage(`Employee ${editingEmployeeId ? 'updated' : 'saved'} successfully`, 'success');

        // Lookup employee in MVRetail system
        showFlashMessage('Looking up scheduling ID from MVRetail...', 'info');
        await lookupEmployeeExternalId(savedEmployeeId, employeeName, employeeIdInput);

        // Reload employees list
        loadEmployees();

    } catch (error) {
        console.error('Error saving employee:', error);
        showModalAlert('Error saving employee. Please try again.', 'error');
    }
}

async function lookupEmployeeExternalId(employeeId, employeeName, employeeIdInput) {
    try {
        const response = await fetch('/api/lookup_employee_id', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                employee_id: employeeId,
                name: employeeName,
                crossmark_id: employeeIdInput
            })
        });

        const result = await response.json();

        if (result.found) {
            showFlashMessage(`Found in MVRetail! Scheduling ID: ${result.external_id}`, 'success');
        } else {
            showFlashMessage(`Employee not found in MVRetail system - cannot be scheduled until added to MVRetail`, 'warning');
        }

    } catch (error) {
        console.error('Error looking up employee external ID:', error);
        showFlashMessage('Could not verify employee in MVRetail system', 'warning');
    }
}

// ========================================
// Import Employees Modal
// ========================================

async function openImportEmployeesModal() {
    const modal = document.getElementById('import-employees-modal');
    const list = document.getElementById('import-employee-list');
    const alerts = document.getElementById('import-modal-alerts');

    modal.classList.add('modal-open');
    alerts.innerHTML = '';
    list.innerHTML = '<div class="loading">Loading employees from MVRetail and syncing with local database...</div>';

    try {
        const response = await fetch('/api/get_available_reps');
        const data = await response.json();

        if (data.error) {
            list.innerHTML = `<div class="alert alert-error">${data.error}</div>`;
            return;
        }

        // Show sync results
        renderImportEmployeeResults(data);

    } catch (error) {
        console.error('Error loading MVRetail employees:', error);
        list.innerHTML = '<div class="alert alert-error">Error loading employees from MVRetail. Please try again.</div>';
    }
}

function closeImportEmployeesModal() {
    document.getElementById('import-employees-modal').classList.remove('modal-open');
}

function renderImportEmployeeResults(data) {
    const list = document.getElementById('import-employee-list');
    const alerts = document.getElementById('import-modal-alerts');

    let html = '';
    const hasExisting = data.existing_employees && data.existing_employees.length > 0;
    const hasNew = data.new_employees && data.new_employees.length > 0;
    const updatedEmployees = hasExisting ? data.existing_employees.filter(e => e.was_updated) : [];

    // Clear alerts
    alerts.innerHTML = '';

    // Summary bar at top
    html += `
        <div class="import-summary" style="display: flex; gap: 12px; margin-bottom: 20px; padding: 12px; background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%); border-radius: 8px;">
            <div style="flex: 1; text-align: center; padding: 8px;">
                <div style="font-size: 24px; font-weight: 700; color: #1e40af;">${data.total_from_api || 0}</div>
                <div style="font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">From MVRetail</div>
            </div>
            <div style="width: 1px; background: #cbd5e1;"></div>
            <div style="flex: 1; text-align: center; padding: 8px;">
                <div style="font-size: 24px; font-weight: 700; color: #059669;">${hasExisting ? data.existing_employees.length : 0}</div>
                <div style="font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Already Synced</div>
            </div>
            <div style="width: 1px; background: #cbd5e1;"></div>
            <div style="flex: 1; text-align: center; padding: 8px;">
                <div style="font-size: 24px; font-weight: 700; color: #dc2626;">${hasNew ? data.new_employees.length : 0}</div>
                <div style="font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">New to Import</div>
            </div>
        </div>
    `;

    // Updated notification if any were updated
    if (updatedEmployees.length > 0) {
        html += `
            <div style="background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 6px; padding: 10px 14px; margin-bottom: 16px; display: flex; align-items: center; gap: 10px;">
                <span style="color: #059669; font-size: 18px;">&#10003;</span>
                <span style="color: #047857; font-size: 13px;"><strong>${updatedEmployees.length}</strong> employee(s) updated with latest MVRetail data</span>
            </div>
        `;
    }

    // Existing employees section (collapsible)
    if (hasExisting) {
        html += `
            <details class="import-section-details" style="margin-bottom: 16px; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                <summary style="padding: 12px 16px; background: #f8fafc; cursor: pointer; display: flex; align-items: center; gap: 10px; font-weight: 600; color: #334155; user-select: none;">
                    <span style="color: #059669;">&#10003;</span>
                    Already in System (${data.existing_employees.length})
                    <span style="margin-left: auto; font-size: 12px; color: #94a3b8; font-weight: 400;">Click to expand</span>
                </summary>
                <div style="max-height: 200px; overflow-y: auto; padding: 8px;">
        `;

        for (const emp of data.existing_employees) {
            const updateBadge = emp.was_updated
                ? '<span style="background: #059669; color: white; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 600; text-transform: uppercase;">Updated</span>'
                : '';

            html += `
                <div style="display: flex; align-items: center; padding: 10px 12px; border-bottom: 1px solid #f1f5f9;">
                    <div style="width: 36px; height: 36px; background: #e0f2fe; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 12px;">
                        <span style="color: #0284c7; font-weight: 600; font-size: 14px;">${emp.name.charAt(0).toUpperCase()}</span>
                    </div>
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-weight: 500; color: #1e293b; display: flex; align-items: center; gap: 8px;">
                            ${emp.name} ${updateBadge}
                        </div>
                        <div style="font-size: 11px; color: #94a3b8;">ID: ${emp.crossmark_employee_id || emp.id}</div>
                    </div>
                    <span style="color: #059669; font-size: 18px;">&#10003;</span>
                </div>
            `;
        }

        html += '</div></details>';
    }

    // New employees section
    if (hasNew) {
        html += `
            <div class="import-section-new" style="border: 2px solid #3b82f6; border-radius: 8px; overflow: hidden;">
                <div style="padding: 12px 16px; background: #eff6ff; display: flex; align-items: center; justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="font-size: 20px;">&#128229;</span>
                        <span style="font-weight: 600; color: #1e40af;">Available to Import (${data.new_employees.length})</span>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <button type="button" onclick="selectAllImportEmployees()" style="padding: 6px 12px; font-size: 12px; background: white; border: 1px solid #cbd5e1; border-radius: 4px; cursor: pointer; color: #475569;">Select All</button>
                        <button type="button" onclick="deselectAllImportEmployees()" style="padding: 6px 12px; font-size: 12px; background: white; border: 1px solid #cbd5e1; border-radius: 4px; cursor: pointer; color: #475569;">Clear</button>
                    </div>
                </div>
                <div id="new-employees-list" style="max-height: 250px; overflow-y: auto; padding: 8px;">
        `;

        for (const emp of data.new_employees) {
            const repData = JSON.stringify(emp).replace(/'/g, '&#39;');
            html += `
                <label style="display: flex; align-items: center; padding: 12px; margin: 4px; background: white; border: 2px solid #e2e8f0; border-radius: 8px; cursor: pointer; transition: all 0.15s ease;"
                       onmouseover="this.style.borderColor='#3b82f6'; this.style.background='#f8fafc';"
                       onmouseout="if(!this.querySelector('input').checked) { this.style.borderColor='#e2e8f0'; this.style.background='white'; }">
                    <input type="checkbox" value="${emp.rep_id}" data-rep='${repData}'
                           style="width: 20px; height: 20px; margin-right: 12px; accent-color: #3b82f6; cursor: pointer;"
                           onchange="this.parentElement.style.borderColor = this.checked ? '#3b82f6' : '#e2e8f0'; this.parentElement.style.background = this.checked ? '#eff6ff' : 'white';">
                    <div style="width: 40px; height: 40px; background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 12px;">
                        <span style="color: #2563eb; font-weight: 600; font-size: 16px;">${emp.name.charAt(0).toUpperCase()}</span>
                    </div>
                    <div style="flex: 1;">
                        <div style="font-weight: 600; color: #1e293b; font-size: 14px;">${emp.name}</div>
                        <div style="font-size: 12px; color: #64748b;">
                            <span style="display: inline-block; padding: 2px 6px; background: #f1f5f9; border-radius: 3px; margin-right: 6px;">Rep: ${emp.rep_id}</span>
                            <span style="display: inline-block; padding: 2px 6px; background: #f1f5f9; border-radius: 3px;">${emp.employee_id || 'No Employee ID'}</span>
                        </div>
                    </div>
                </label>
            `;
        }

        html += '</div></div>';
    } else if (!hasExisting) {
        html = `
            <div style="text-align: center; padding: 40px 20px; color: #64748b;">
                <div style="font-size: 48px; margin-bottom: 16px;">&#128269;</div>
                <div style="font-size: 16px; font-weight: 500; color: #334155; margin-bottom: 8px;">No Employees Found</div>
                <div style="font-size: 14px;">Check your MVRetail session and try again.</div>
            </div>
        `;
    } else {
        html += `
            <div style="text-align: center; padding: 30px 20px; background: #f0fdf4; border-radius: 8px; margin-top: 10px;">
                <div style="font-size: 36px; margin-bottom: 12px;">&#9989;</div>
                <div style="font-size: 15px; font-weight: 500; color: #166534;">All employees are synced!</div>
                <div style="font-size: 13px; color: #4ade80; margin-top: 4px;">Nothing new to import from MVRetail.</div>
            </div>
        `;
    }

    list.innerHTML = html;

    // Update button visibility
    const importBtn = document.querySelector('#import-employees-modal .btn-primary');
    if (importBtn) {
        if (hasNew) {
            importBtn.style.display = 'inline-flex';
            importBtn.innerHTML = '<span style="margin-right: 6px;">&#128229;</span> Import Selected';
        } else {
            importBtn.style.display = 'none';
        }
    }
}

function selectAllImportEmployees() {
    document.querySelectorAll('#new-employees-list input[type="checkbox"]').forEach(cb => {
        cb.checked = true;
        const label = cb.closest('label');
        if (label) {
            label.style.borderColor = '#3b82f6';
            label.style.background = '#eff6ff';
        }
    });
}

function deselectAllImportEmployees() {
    document.querySelectorAll('#new-employees-list input[type="checkbox"]').forEach(cb => {
        cb.checked = false;
        const label = cb.closest('label');
        if (label) {
            label.style.borderColor = '#e2e8f0';
            label.style.background = 'white';
        }
    });
}

async function importSelectedEmployees() {
    const checkboxes = document.querySelectorAll('#new-employees-list input[type="checkbox"]:checked');

    if (checkboxes.length === 0) {
        showImportAlert('Please select at least one employee to import', 'warning');
        return;
    }

    const selectedReps = Array.from(checkboxes).map(cb => JSON.parse(cb.dataset.rep));

    showImportAlert(`Importing ${selectedReps.length} employee(s)...`, 'info');

    try {
        const response = await fetch('/api/import_employees', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ employees: selectedReps })
        });

        const data = await response.json();

        if (data.error) {
            showImportAlert(`Error: ${data.error}`, 'error');
            return;
        }

        let message = `Successfully imported ${data.imported} employee(s).`;
        if (data.errors && data.errors.length > 0) {
            message += ` ${data.errors.length} error(s) occurred.`;
        }
        showImportAlert(message, 'success');

        // Close modal and reload after short delay
        setTimeout(() => {
            closeImportEmployeesModal();
            loadEmployees();
            showFlashMessage(message, 'success');
        }, 2000);

    } catch (error) {
        console.error('Error importing employees:', error);
        showImportAlert('Error importing employees. Please try again.', 'error');
    }
}

// ========================================
// Edit Employee
// ========================================

async function editEmployee(employeeId) {
    try {
        const response = await fetch('/api/employees');
        const employees = await response.json();
        const employee = employees.find(emp => emp.id === employeeId);

        if (!employee) {
            showFlashMessage('Employee not found', 'error');
            return;
        }

        // Populate form
        document.getElementById('employee-id').value = employee.id || '';
        document.getElementById('employee-name').value = employee.name;
        document.getElementById('employee-email').value = employee.email || '';
        document.getElementById('employee-phone').value = employee.phone || '';
        document.getElementById('job-title').value = employee.job_title;
        document.getElementById('is-active').checked = employee.is_active;
        document.getElementById('adult-beverage-trained').checked = employee.adult_beverage_trained;
        document.getElementById('juicer-trained').checked = employee.juicer_trained;

        // Set availability
        ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].forEach(day => {
            document.getElementById(`avail-${day}`).checked = employee.weekly_availability[day];
        });

        // Set editing mode
        const form = document.getElementById('add-employee-form');
        form.dataset.editingEmployeeId = employeeId;

        // Update modal title
        document.querySelector('#add-employee-modal .modal-header h2').textContent = `Editing ${employee.name}`;

        // Open modal
        openAddEmployeeModal();

    } catch (error) {
        console.error('Error loading employee for edit:', error);
        showFlashMessage('Error loading employee data', 'error');
    }
}

// ========================================
// Toggle Employee Status
// ========================================

async function toggleEmployeeStatus(employeeId, newActiveStatus) {
    const action = newActiveStatus ? 'activate' : 'deactivate';

    if (!confirm(`Are you sure you want to ${action} this employee?`)) {
        return;
    }

    try {
        // First, fetch the employee to get their name (required by the API)
        const employeesResponse = await fetch('/api/employees');
        const employees = await employeesResponse.json();
        const employee = employees.find(emp => emp.id === employeeId);

        if (!employee) {
            showFlashMessage('Employee not found', 'error');
            return;
        }

        const response = await fetch('/api/employees', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                id: employeeId,
                name: employee.name,  // Include name (required by API)
                is_active: newActiveStatus
            })
        });

        const data = await response.json();

        if (data.error) {
            showFlashMessage(`Error: ${data.error}`, 'error');
        } else {
            showFlashMessage(`Employee ${action}d successfully`, 'success');
            loadEmployees();
        }

    } catch (error) {
        console.error(`Error ${action}ing employee:`, error);
        showFlashMessage(`Error ${action}ing employee`, 'error');
    }
}

// ========================================
// Delete Employee
// ========================================

async function deleteEmployee(employeeId) {
    try {
        const response = await fetch('/api/employees');
        const employees = await response.json();
        const employee = employees.find(emp => emp.id === employeeId);
        const employeeName = employee ? employee.name : employeeId;

        if (!confirm(`Are you sure you want to permanently DELETE ${employeeName}?\n\nThis action cannot be undone.`)) {
            return;
        }

        const deleteResponse = await fetch(`/api/employees/${employeeId}`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        });

        const data = await deleteResponse.json();

        if (data.error) {
            showFlashMessage(`Error: ${data.error}`, 'error');
        } else {
            showFlashMessage(data.message, 'success');
            loadEmployees();
        }

    } catch (error) {
        console.error('Error deleting employee:', error);
        showFlashMessage('Error deleting employee', 'error');
    }
}

// ========================================
// Alert/Message Functions
// ========================================

function showModalAlert(message, type) {
    const alerts = document.getElementById('modal-alerts');
    alerts.innerHTML = `<div class="alert alert-${type}">${message}</div>`;
}

function showImportAlert(message, type) {
    const alerts = document.getElementById('import-modal-alerts');
    alerts.innerHTML = `<div class="alert alert-${type}">${message}</div>`;
}

function showFlashMessage(message, type) {
    const flashContainer = document.getElementById('flash-messages');
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type}`;
    alertDiv.textContent = message;
    flashContainer.appendChild(alertDiv);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
}

// ========================================
// Utility Functions
// ========================================

function getCsrfToken() {
    // Try to get from global function (csrf_helper.js) first, then from cookie, then from input
    if (typeof window.getCsrfToken === 'function' && window.getCsrfToken !== getCsrfToken) {
        return window.getCsrfToken();
    }

    // Fallback: read from csrf_token cookie
    const name = 'csrf_token=';
    const decodedCookie = decodeURIComponent(document.cookie);
    const cookieArray = decodedCookie.split(';');
    for (let i = 0; i < cookieArray.length; i++) {
        let cookie = cookieArray[i].trim();
        if (cookie.indexOf(name) === 0) {
            return cookie.substring(name.length);
        }
    }

    // Fallback: try to get from input element
    const input = document.querySelector('input[name="csrf_token"]');
    return input ? input.value : '';
}

