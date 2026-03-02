/**
 * Chart rendering for chat messages.
 * Detects ```chart code blocks and renders them as Chart.js line charts.
 */

const chartRenderer = {
    /** Counter for unique chart container IDs */
    _idCounter: 0,

    /** Default line colors for multiple datasets */
    colors: [
        '#10a37f', '#3b82f6', '#f59e0b', '#ef4444',
        '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'
    ],

    /**
     * Generate a unique chart container ID
     */
    nextId() {
        return 'chart-' + (++this._idCounter);
    },

    /**
     * Initialize any unrendered chart containers in the given element.
     * Called after innerHTML is set with rendered markdown.
     */
    renderCharts(parentEl) {
        const containers = parentEl.querySelectorAll('.chart-container:not(.chart-rendered)');
        containers.forEach(container => {
            container.classList.add('chart-rendered');
            try {
                const raw = container.getAttribute('data-chart');
                const data = JSON.parse(raw);
                this.createChart(container, data);
            } catch (e) {
                container.textContent = 'Failed to render chart: ' + e.message;
                container.classList.add('chart-error');
            }
        });
    },

    /**
     * Create a Chart.js line chart inside the container.
     * Expected data format:
     * {
     *   title: "Chart Title",        // optional
     *   labels: ["Jan", "Feb", ...],  // x-axis labels
     *   datasets: [
     *     { label: "Series 1", data: [10, 20, ...] }
     *   ]
     * }
     */
    createChart(container, data) {
        if (!data.labels || !data.datasets || !Array.isArray(data.datasets)) {
            container.textContent = 'Invalid chart data: needs "labels" and "datasets" arrays.';
            container.classList.add('chart-error');
            return;
        }

        const canvas = document.createElement('canvas');
        container.appendChild(canvas);

        const datasets = data.datasets.map((ds, i) => ({
            label: ds.label || `Series ${i + 1}`,
            data: ds.data,
            borderColor: ds.color || this.colors[i % this.colors.length],
            backgroundColor: (ds.color || this.colors[i % this.colors.length]) + '1a',
            borderWidth: 2,
            pointRadius: 3,
            pointHoverRadius: 5,
            tension: 0.3,
            fill: data.datasets.length === 1
        }));

        new Chart(canvas, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    title: {
                        display: !!data.title,
                        text: data.title || '',
                        color: getComputedStyle(document.documentElement)
                            .getPropertyValue('--text-primary').trim() || '#1f2937',
                        font: { size: 14, weight: '500' }
                    },
                    legend: {
                        display: datasets.length > 1,
                        labels: {
                            color: getComputedStyle(document.documentElement)
                                .getPropertyValue('--text-secondary').trim() || '#4b5563',
                            boxWidth: 12,
                            padding: 16
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: getComputedStyle(document.documentElement)
                                .getPropertyValue('--text-muted').trim() || '#9ca3af'
                        },
                        grid: {
                            color: getComputedStyle(document.documentElement)
                                .getPropertyValue('--border').trim() || '#e5e7eb'
                        }
                    },
                    y: {
                        ticks: {
                            color: getComputedStyle(document.documentElement)
                                .getPropertyValue('--text-muted').trim() || '#9ca3af'
                        },
                        grid: {
                            color: getComputedStyle(document.documentElement)
                                .getPropertyValue('--border').trim() || '#e5e7eb'
                        }
                    }
                }
            }
        });
    }
};
