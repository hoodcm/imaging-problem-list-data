const USE_MOCK = new URLSearchParams(window.location.search).has('mock');

const MOCK_DATA = {
    report: { id: 'mock-report-1', report_text: 'Sample report.', source_ref: null, created_at: new Date().toISOString() },
    job: (id) => ({ job_id: id, status: 'completed', extraction_id: 'mock-extraction-1' }),
    extraction: {
        id: 'mock-extraction-1', report_id: 'mock-report-1',
        model_name: 'mock-model', reasoning_effort: null, exam_description_hint: null,
        created_at: new Date().toISOString(),
        extraction: {
            exam_info: { study_description: 'CT Abdomen', modality: 'CT', body_part: 'abdomen', study_date: null },
            findings: [{
                finding_name: 'Kidney stone',
                presence: 'present', location: { body_region: 'abdomen', specific_anatomy: 'left kidney', laterality: 'left' },
                attributes: [{ key: 'size', value: '3 mm' }], report_text: 'Left kidney stone measuring 3mm.'
            }],
            non_finding_text: [],
        },
        validation_result: null
    }
};

async function mockApiFetch(path, options = {}) {
    await new Promise(r => setTimeout(r, 50));
    const method = options.method || 'GET';
    const idMatch = (pattern) => path.match(pattern);
    if (method === 'POST' && path === '/reports') return { ...MOCK_DATA.report, id: 'mock-' + Date.now() };
    if (method === 'GET' && path.startsWith('/reports') && !idMatch(/^\/reports\/[^/]+/)) return [MOCK_DATA.report];
    if (method === 'GET' && idMatch(/^\/reports\/([^/]+)$/) && !path.includes('/extract')) return { ...MOCK_DATA.report, id: idMatch(/^\/reports\/([^/]+)$/)[1] };
    if (method === 'GET' && idMatch(/^\/reports\/[^/]+\/extractions$/)) return [{ id: 'mock-extraction-1', status: 'completed', created_at: new Date().toISOString() }];
    if (method === 'POST' && idMatch(/^\/reports\/([^/]+)\/extract$/)) {
        const rid = idMatch(/^\/reports\/([^/]+)\/extract$/)[1];
        return { job_id: 'mock-job-' + Date.now(), report_id: rid, status: 'pending' };
    }
    if (method === 'GET' && idMatch(/^\/jobs\/(.+)$/)) return MOCK_DATA.job(idMatch(/^\/jobs\/(.+)$/)[1]);
    if (method === 'GET' && idMatch(/^\/extractions\/([^/]+)$/) && !path.includes('/corrections')) return { ...MOCK_DATA.extraction, id: idMatch(/^\/extractions\/([^/]+)$/)[1] };
    if (method === 'GET' && path.includes('/corrections')) return [];
    if (method === 'POST' && path.includes('/corrections')) return { id: 'mock-correction-1', created_at: new Date().toISOString() };
    return {};
}

function extractorApp() {
    return {
        currentView: 'submit',
        error: null,
        loading: false,
        darkMode: document.documentElement.classList.contains('dark'),

        submitForm: { reportText: '', sourceRef: '', examDescription: '', model: '', reasoning: '' },
        submitLoading: false,
        lastSubmittedReport: null,

        reports: [],
        reportsLoading: false,
        reportsLimit: 20,
        reportsOffset: 0,

        currentReport: null,
        reportExtractions: [],
        reportLoading: false,
        extractLoading: false,
        extractForm: { examDescription: '', model: '', reasoning: '' },

        currentJob: null,
        pollTimer: null,
        pollInFlight: false,

        currentExtraction: null,
        corrections: [],
        extractionLoading: false,
        correctionForm: { comment: '', createdBy: '' },
        correctionLoading: false,

        init() {
            this.$watch('darkMode', (enabled) => {
                document.documentElement.classList.toggle('dark', enabled);
                localStorage.setItem('color-theme', enabled ? 'dark' : 'light');
            });
            this.navigateFromHash();
            window.addEventListener('hashchange', () => this.navigateFromHash());
        },

        navigateFromHash() {
            const hash = window.location.hash || '#/';
            let match;

            if (hash === '#/' || hash === '#' || hash === '') {
                this.navigate('submit');
                return;
            }

            match = hash.match(/^#\/reports\/([^/]+)\/extracting\/([^/]+)$/);
            if (match) {
                this.navigate('extracting', { reportId: match[1], jobId: match[2] });
                return;
            }

            match = hash.match(/^#\/reports\/([^/]+)$/);
            if (match) {
                this.navigate('reportDetail', { reportId: match[1] });
                return;
            }

            if (hash === '#/reports') {
                this.navigate('reports');
                return;
            }

            match = hash.match(/^#\/extractions\/([^/]+)$/);
            if (match) {
                this.navigate('extractionDetail', { extractionId: match[1] });
                return;
            }

            window.location.hash = '#/';
        },

        navigate(view, params = {}) {
            this.stopPolling();
            this.error = null;
            this.currentView = view;

            switch (view) {
                case 'reports':
                    this.loadReports();
                    break;
                case 'reportDetail':
                    this.loadReport(params.reportId);
                    break;
                case 'extracting':
                    this.startPolling(params.jobId, params.reportId);
                    break;
                case 'extractionDetail':
                    this.loadExtraction(params.extractionId);
                    break;
            }
        },

        async apiFetch(path, options = {}) {
            if (USE_MOCK) {
                return mockApiFetch(path, options);
            }

            const resp = await fetch(`/api${path}`, {
                headers: { 'Content-Type': 'application/json', ...options.headers },
                ...options,
            });

            if (!resp.ok) {
                const body = await resp.json().catch(() => ({}));
                const msg = body.detail || `Request failed (${resp.status})`;
                throw { status: resp.status, message: msg };
            }

            return resp.json();
        },

        async submitReport() {
            if (!this.submitForm.reportText.trim()) {
                this.error = 'Report text is required.';
                return;
            }

            try {
                this.submitLoading = true;
                const result = await this.apiFetch('/reports', {
                    method: 'POST',
                    body: JSON.stringify({
                        report_text: this.submitForm.reportText,
                        source_ref: this.submitForm.sourceRef.trim() || null,
                    }),
                });
                this.lastSubmittedReport = result;
                this.submitForm = { reportText: '', sourceRef: '', examDescription: '', model: '', reasoning: '' };
            } catch (e) {
                this.error = e.message || 'An unexpected error occurred';
            } finally {
                this.submitLoading = false;
            }
        },

        buildExtractBody(opts) {
            const body = {};
            if (opts.examDescription?.trim()) body.exam_description = opts.examDescription.trim();
            if (opts.model?.trim()) body.model = opts.model.trim();
            if (opts.reasoning?.trim()) body.reasoning = opts.reasoning.trim();
            return body;
        },

        async submitAndExtract() {
            if (!this.submitForm.reportText.trim()) {
                this.error = 'Report text is required.';
                return;
            }

            try {
                this.submitLoading = true;

                const report = await this.apiFetch('/reports', {
                    method: 'POST',
                    body: JSON.stringify({
                        report_text: this.submitForm.reportText,
                        source_ref: this.submitForm.sourceRef.trim() || null,
                    }),
                });

                this.lastSubmittedReport = report;
                const extractBody = this.buildExtractBody(this.submitForm);

                let extraction;
                try {
                    extraction = await this.apiFetch(`/reports/${report.id}/extract`, {
                        method: 'POST',
                        body: JSON.stringify(extractBody),
                    });
                } catch (extractErr) {
                    if (extractErr.status === 503) {
                        this.error = 'Extraction service is temporarily unavailable. Please try again later.';
                        return;
                    }
                    throw extractErr;
                }

                this.submitForm = { reportText: '', sourceRef: '', examDescription: '', model: '', reasoning: '' };
                window.location.hash = `#/reports/${report.id}/extracting/${extraction.job_id}`;
            } catch (e) {
                this.error = e.message || 'An unexpected error occurred';
            } finally {
                this.submitLoading = false;
            }
        },

        async loadReports() {
            try {
                this.reportsLoading = true;
                this.reports = await this.apiFetch(`/reports?limit=${this.reportsLimit}&offset=${this.reportsOffset}`);
            } catch (e) {
                this.error = e.message || 'An unexpected error occurred';
            } finally {
                this.reportsLoading = false;
            }
        },

        async loadReport(reportId) {
            try {
                this.reportLoading = true;
                this.currentReport = await this.apiFetch(`/reports/${reportId}`);
                this.reportExtractions = await this.apiFetch(`/reports/${reportId}/extractions`);
            } catch (e) {
                this.error = e.message || 'An unexpected error occurred';
            } finally {
                this.reportLoading = false;
            }
        },

        async triggerExtraction(reportId) {
            try {
                this.extractLoading = true;
                const extractBody = this.buildExtractBody(this.extractForm);
                const result = await this.apiFetch(`/reports/${reportId}/extract`, {
                    method: 'POST',
                    body: JSON.stringify(extractBody),
                });
                this.extractForm = { examDescription: '', model: '', reasoning: '' };
                window.location.hash = `#/reports/${reportId}/extracting/${result.job_id}`;
            } catch (e) {
                if (e.status === 503) {
                    this.error = 'Extraction service is temporarily unavailable. Please try again later.';
                } else {
                    this.error = e.message || 'An unexpected error occurred';
                }
            } finally {
                this.extractLoading = false;
            }
        },

        startPolling(jobId, reportId) {
            this.currentJob = { job_id: jobId, report_id: reportId, status: 'pending' };
            this.pollJob();
        },

        async pollJob() {
            if (this.pollInFlight) return;

            this.pollInFlight = true;
            try {
                const result = await this.apiFetch(`/jobs/${this.currentJob.job_id}`);
                this.currentJob = { ...this.currentJob, ...result };

                if (result.status === 'pending' || result.status === 'running') {
                    const delay = result.retry_after ? result.retry_after * 1000 : 2000;
                    this.pollTimer = setTimeout(() => this.pollJob(), delay);
                } else if (result.status === 'completed') {
                    this.stopPolling();
                    window.location.hash = `#/extractions/${result.extraction_id}`;
                } else if (result.status === 'failed') {
                    this.stopPolling();
                    this.error = result.error || 'Extraction job failed.';
                }
            } catch (e) {
                this.stopPolling();
                this.error = e.message || 'An unexpected error occurred while polling job status.';
            } finally {
                this.pollInFlight = false;
            }
        },

        stopPolling() {
            clearTimeout(this.pollTimer);
            this.pollTimer = null;
            this.pollInFlight = false;
        },

        async loadExtraction(extractionId) {
            try {
                this.extractionLoading = true;
                const detail = await this.apiFetch(`/extractions/${extractionId}`);
                // Flatten: extraction sub-object (exam_info, findings, non_finding_text) to top level
                this.currentExtraction = { ...detail, ...detail.extraction };
                await this.loadCorrections(extractionId);
            } catch (e) {
                this.error = e.message || 'An unexpected error occurred';
            } finally {
                this.extractionLoading = false;
            }
        },

        async loadCorrections(extractionId) {
            try {
                this.corrections = await this.apiFetch(`/extractions/${extractionId}/corrections`);
            } catch (e) {
                this.error = e.message || 'Failed to load corrections.';
            }
        },

        async submitCorrection() {
            if (!this.correctionForm.comment.trim()) {
                this.error = 'Correction comment is required.';
                return;
            }

            try {
                this.correctionLoading = true;
                await this.apiFetch(`/extractions/${this.currentExtraction.id}/corrections`, {
                    method: 'POST',
                    body: JSON.stringify({
                        correction_type: 'comment',
                        comment: this.correctionForm.comment,
                        created_by: this.correctionForm.createdBy.trim() || null,
                    }),
                });
                this.correctionForm = { comment: '', createdBy: '' };
                await this.loadCorrections(this.currentExtraction.id);
            } catch (e) {
                this.error = e.message || 'An unexpected error occurred';
            } finally {
                this.correctionLoading = false;
            }
        },

        formatDate(str) {
            try {
                return new Date(str).toLocaleString();
            } catch {
                return str;
            }
        },

        truncateId(id) {
            if (!id) return '';
            return id.length > 8 ? id.substring(0, 8) + '...' : id;
        },

    };
}
