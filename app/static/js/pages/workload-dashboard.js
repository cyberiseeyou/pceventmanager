/**
 * Workload Dashboard JavaScript
 *
 * Handles date range selection, AJAX data loading, and Chart.js visualization
 * for employee workload distribution dashboard.
 *
 * Epic 2, Story 2.6: Create Workload Dashboard Frontend View
 */

let workloadChart = null;

/**
 * Initialize dashboard functionality when DOM is ready
 */
document.addEventListener('DOMContentLoaded', () => {
  console.log('[Workload Dashboard] Initializing...');

  // Initialize with default range (this week)
  loadWorkloadData('this-week');

  // Add click handlers for date range buttons
  document.querySelectorAll('.range-btn').forEach(button => {
    button.addEventListener('click', (e) => {
      // Update active state
      document.querySelectorAll('.range-btn').forEach(btn => btn.classList.remove('active'));
      button.classList.add('active');

      // Get selected range
      const range = button.dataset.range;

      // Show/hide custom range inputs
      const customInputs = document.getElementById('custom-range-inputs');
      if (range === 'custom') {
        customInputs.style.display = 'flex';
      } else {
        customInputs.style.display = 'none';
        loadWorkloadData(range);
      }
    });
  });

  // Add click handler for custom range apply button
  document.getElementById('apply-custom-range').addEventListener('click', () => {
    loadWorkloadData('custom');
  });

  console.log('[Workload Dashboard] Initialized successfully');
});

/**
 * Load workload data for the specified date range
 * @param {string} range - Date range identifier ('this-week', 'last-week', 'this-month', 'custom')
 */
async function loadWorkloadData(range = 'this-week') {
  console.log(`[Workload Dashboard] Loading data for range: ${range}`);

  const dateRange = getDateRange(range);
  const spinner = document.getElementById('loading-spinner');
  const chartContainer = document.querySelector('.chart-container');
  const tableContainer = document.querySelector('.table-container');
  const emptyState = document.getElementById('empty-state');

  // Show loading spinner, hide content
  spinner.style.display = 'block';
  chartContainer.style.display = 'none';
  tableContainer.style.display = 'none';
  emptyState.style.display = 'none';

  try {
    const response = await fetch(`/api/workload?start_date=${dateRange.start_date}&end_date=${dateRange.end_date}`);

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    console.log('[Workload Dashboard] Data loaded:', data);

    spinner.style.display = 'none';

    if (data.employees.length === 0) {
      emptyState.style.display = 'block';
    } else {
      chartContainer.style.display = 'block';
      tableContainer.style.display = 'block';
      createWorkloadChart(data);
      populateTable(data);
    }
  } catch (error) {
    console.error('[Workload Dashboard] Error loading workload data:', error);
    alert('Failed to load workload data. Please try again.');
    spinner.style.display = 'none';
  }
}

/**
 * Calculate start and end dates for the specified range
 * @param {string} range - Date range identifier
 * @returns {Object} Object with start_date and end_date strings (YYYY-MM-DD)
 */
function getDateRange(range) {
  const today = new Date();
  let startDate, endDate;

  switch(range) {
    case 'this-week':
      // Monday of this week
      const dayOfWeek = today.getDay();
      const diff = today.getDate() - dayOfWeek + (dayOfWeek === 0 ? -6 : 1);
      startDate = new Date(today);
      startDate.setDate(diff);
      endDate = new Date(startDate);
      endDate.setDate(startDate.getDate() + 6); // Sunday
      break;

    case 'last-week':
      // Monday of last week
      const lastWeekDayOfWeek = today.getDay();
      const lastWeekDiff = today.getDate() - lastWeekDayOfWeek - 6 + (lastWeekDayOfWeek === 0 ? -6 : 1);
      startDate = new Date(today);
      startDate.setDate(lastWeekDiff);
      endDate = new Date(startDate);
      endDate.setDate(startDate.getDate() + 6); // Sunday
      break;

    case 'this-month':
      startDate = new Date(today.getFullYear(), today.getMonth(), 1);
      endDate = new Date(today.getFullYear(), today.getMonth() + 1, 0);
      break;

    case 'custom':
      // Get from input fields
      const startInput = document.getElementById('start-date').value;
      const endInput = document.getElementById('end-date').value;

      if (!startInput || !endInput) {
        alert('Please select both start and end dates.');
        return null;
      }

      startDate = new Date(startInput);
      endDate = new Date(endInput);
      break;

    default:
      // Default to this week
      const defaultDayOfWeek = today.getDay();
      const defaultDiff = today.getDate() - defaultDayOfWeek + (defaultDayOfWeek === 0 ? -6 : 1);
      startDate = new Date(today);
      startDate.setDate(defaultDiff);
      endDate = new Date(startDate);
      endDate.setDate(startDate.getDate() + 6);
  }

  return {
    start_date: startDate.toISOString().split('T')[0],
    end_date: endDate.toISOString().split('T')[0]
  };
}

/**
 * Create horizontal bar chart using Chart.js
 * @param {Object} data - Workload data from API
 */
function createWorkloadChart(data) {
  console.log('[Workload Dashboard] Creating chart with data:', data);

  const ctx = document.getElementById('workload-chart').getContext('2d');

  // Extract data
  const labels = data.employees.map(emp => emp.name);
  const eventCounts = data.employees.map(emp => emp.event_count);
  const colors = data.employees.map(emp => getStatusColor(emp.status));

  // Destroy existing chart if exists
  if (workloadChart) {
    workloadChart.destroy();
  }

  workloadChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Event Count',
        data: eventCounts,
        backgroundColor: colors,
        borderColor: colors,
        borderWidth: 1
      }]
    },
    options: {
      indexAxis: 'y', // Horizontal bar chart
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          callbacks: {
            label: function(context) {
              const emp = data.employees[context.dataIndex];
              return `${emp.event_count} events (${emp.total_hours}h)`;
            }
          }
        }
      },
      scales: {
        x: {
          beginAtZero: true,
          title: {
            display: true,
            text: 'Number of Events'
          },
          ticks: {
            precision: 0 // Show only whole numbers
          }
        },
        y: {
          title: {
            display: true,
            text: 'Employee'
          }
        }
      }
    }
  });

  console.log('[Workload Dashboard] Chart created successfully');
}

/**
 * Get color for workload status
 * @param {string} status - Status code ('normal', 'high', 'overloaded')
 * @returns {string} Hex color code
 */
function getStatusColor(status) {
  const colors = {
    'normal': '#10B981',    // Green
    'high': '#FBBF24',      // Yellow
    'overloaded': '#DC2626' // Red
  };
  return colors[status] || colors.normal;
}

/**
 * Populate data table with employee workload information
 * @param {Object} data - Workload data from API
 */
function populateTable(data) {
  console.log('[Workload Dashboard] Populating table');

  const tbody = document.querySelector('#workload-table tbody');
  tbody.innerHTML = '';

  data.employees.forEach(emp => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${emp.name}</td>
      <td>${emp.event_count}</td>
      <td>${emp.total_hours}</td>
      <td>
        <span class="status-badge status-${emp.status}">
          ${emp.status.toUpperCase()}
        </span>
      </td>
    `;
    tbody.appendChild(row);
  });

  console.log('[Workload Dashboard] Table populated successfully');
}
