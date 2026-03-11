const USE_MOCK = new URLSearchParams(window.location.search).has('mock');

const MOCK_DATA = {
  users: [{ username: 'talkasab', name: 'Tarik Alkasab', email: 'tarik@alkasab.org' }],
  report: {
    id: 'mock-report-1',
    report_text: 'Sample report.',
    source_ref: null,
    patient_id: null,
    created_at: new Date().toISOString(),
  },
  job: (id) => {
    const params = new URLSearchParams(window.location.search);
    if (params.has('runningStage')) {
      return {
        job_id: id,
        status: 'running',
        status_message: '[stage:extract_sections] calling_model',
      };
    }
    if (params.has('warnings')) {
      return {
        job_id: id,
        status: 'completed_with_warnings',
        extraction_id: 'mock-extraction-warnings',
        warnings: ['1 finding dropped due to verbatim mismatch', 'Coverage below threshold (85%)'],
      };
    }
    return { job_id: id, status: 'completed', extraction_id: 'mock-extraction-1' };
  },
  extraction: {
    id: 'mock-extraction-1',
    report_id: 'mock-report-1',
    model_name: 'mock-model',
    reasoning_effort: null,
    study_description_hint: null,
    created_at: new Date().toISOString(),
    extraction: {
      exam_info: { study_description: 'CT Abdomen', modality: 'CT', body_part: 'abdomen', study_date: null },
      findings: [
        {
          finding_name: 'Kidney stone',
          presence: 'present',
          location: { body_region: 'abdomen', specific_anatomy: 'left kidney', laterality: 'left' },
          attributes: [{ key: 'size', value: '3 mm' }],
          report_text: 'Left kidney stone measuring 3mm.',
          coding: {
            finding_code: {
              status: 'coded',
              oifm_id: 'OIFM_GMTS_016552',
              oifm_name: 'urinary tract calculus',
              method: 'exact',
              reason: null,
              candidates: [],
            },
            location_code: {
              status: 'coded',
              location_id: 'RID29662',
              location_name: 'left kidney',
              method: 'search',
              reason: null,
              candidates: [],
            },
          },
        },
      ],
      non_finding_text: [],
    },
    validation_result: null,
  },
};

MOCK_DATA.extractionWithWarnings = {
  ...MOCK_DATA.extraction,
  id: 'mock-extraction-warnings',
  validation_result: {
    is_valid: true,
    verbatim_errors: [],
    coverage_warnings: [
      'Text segment not covered by any finding: "Clinical history: recurrent nephrolithiasis"',
      'Coverage ratio 78% is below 85% threshold',
    ],
  },
};

async function mockApiFetch(path, options = {}) {
  await new Promise((r) => setTimeout(r, 50));
  const method = options.method || 'GET';
  const idMatch = (pattern) => path.match(pattern);
  const requestBody = options.body ? JSON.parse(options.body) : {};
  if (method === 'GET' && path === '/users') return MOCK_DATA.users;
  if (method === 'POST' && path === '/reports') return { ...MOCK_DATA.report, id: 'mock-' + Date.now() };
  if (method === 'GET' && path.startsWith('/reports') && !idMatch(/^\/reports\/[^/]+/)) return [MOCK_DATA.report];
  if (method === 'GET' && idMatch(/^\/reports\/([^/]+)$/) && !path.includes('/extract'))
    return { ...MOCK_DATA.report, id: idMatch(/^\/reports\/([^/]+)$/)[1] };
  if (method === 'GET' && idMatch(/^\/reports\/[^/]+\/extractions$/))
    return [{ id: 'mock-extraction-1', status: 'completed', created_at: new Date().toISOString() }];
  if (method === 'POST' && idMatch(/^\/reports\/([^/]+)\/extract$/)) {
    const rid = idMatch(/^\/reports\/([^/]+)\/extract$/)[1];
    return { job_id: 'mock-job-' + Date.now(), report_id: rid, status: 'pending' };
  }
  if (method === 'GET' && idMatch(/^\/jobs\/(.+)$/)) return MOCK_DATA.job(idMatch(/^\/jobs\/(.+)$/)[1]);
  if (method === 'GET' && idMatch(/^\/extractions\/([^/]+)$/) && !path.includes('/corrections')) {
    const extractionId = idMatch(/^\/extractions\/([^/]+)$/)[1];
    if (extractionId === 'mock-extraction-warnings') return { ...MOCK_DATA.extractionWithWarnings };
    return { ...MOCK_DATA.extraction, id: extractionId };
  }
  if (method === 'GET' && path.includes('/corrections')) return [];
  if (method === 'POST' && path.includes('/corrections'))
    return {
      id: 'mock-correction-1',
      author: {
        username: requestBody.username || 'talkasab',
        name: requestBody.username === 'talkasab' ? 'Tarik Alkasab' : requestBody.username || 'Tarik Alkasab',
        email:
          requestBody.username === 'talkasab'
            ? 'tarik@alkasab.org'
            : `${requestBody.username || 'talkasab'}@example.org`,
      },
      created_by: null,
      created_at: new Date().toISOString(),
    };
  return {};
}

function extractorApp() {
  return {
    currentView: 'submit',
    error: null,
    loading: false,
    darkMode: document.documentElement.classList.contains('dark'),

    submitForm: { reportText: '', sourceRef: '', patientId: '', examDescription: '', model: '', reasoning: '' },
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
    correctionForm: { comment: '', username: '' },
    correctionLoading: false,

    users: [],
    usersLoading: false,
    usersError: null,

    findingEditState: {},
    findingEditForms: {},

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
            patient_id: this.submitForm.patientId.trim() || null,
          }),
        });
        this.lastSubmittedReport = result;
        this.submitForm = {
          reportText: '',
          sourceRef: '',
          patientId: '',
          examDescription: '',
          model: '',
          reasoning: '',
        };
      } catch (e) {
        this.error = e.message || 'An unexpected error occurred';
      } finally {
        this.submitLoading = false;
      }
    },

    buildExtractBody(opts) {
      const body = {};
      if (opts.examDescription?.trim()) body.study_description = opts.examDescription.trim();
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
            patient_id: this.submitForm.patientId.trim() || null,
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

        this.submitForm = {
          reportText: '',
          sourceRef: '',
          patientId: '',
          examDescription: '',
          model: '',
          reasoning: '',
        };
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
        } else if (result.status === 'completed' || result.status === 'completed_with_warnings') {
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
        await this.loadUsers();
        await this.loadCorrections(extractionId);
      } catch (e) {
        this.error = e.message || 'An unexpected error occurred';
      } finally {
        this.extractionLoading = false;
      }
    },

    async loadUsers() {
      try {
        this.usersLoading = true;
        this.usersError = null;
        this.users = await this.apiFetch('/users');
        // Default selection: prefer 'talkasab', else first user
        const defaultUser = this.users.find((u) => u.username === 'talkasab') || this.users[0];
        this.correctionForm.username = defaultUser ? defaultUser.username : '';
      } catch (e) {
        this.usersError = e.message || 'Failed to load users';
        this.users = [];
        this.correctionForm.username = '';
      } finally {
        this.usersLoading = false;
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
      if (!this.correctionForm.username.trim()) {
        this.error = 'Username is required.';
        return;
      }

      try {
        this.correctionLoading = true;
        await this.apiFetch(`/extractions/${this.currentExtraction.id}/corrections`, {
          method: 'POST',
          body: JSON.stringify({
            correction_type: 'comment',
            comment: this.correctionForm.comment,
            username: this.correctionForm.username.trim(),
          }),
        });
        this.correctionForm = { comment: '', username: this.correctionForm.username.trim() || 'talkasab' };
        await this.loadCorrections(this.currentExtraction.id);
      } catch (e) {
        this.error = e.message || 'An unexpected error occurred';
      } finally {
        this.correctionLoading = false;
      }
    },

    startFindingEdit(fIdx, finding) {
      this.findingEditState[fIdx] = true;
      this.findingEditForms[fIdx] = {
        presence: finding.presence || 'present',
        location_body_region: finding.location?.body_region || '',
        location_specific_anatomy: finding.location?.specific_anatomy || '',
        location_laterality: finding.location?.laterality || '',
        attributes_json: JSON.stringify(
          (finding.attributes || []).reduce((acc, attr) => {
            acc[attr.key] = attr.value;
            return acc;
          }, {}),
          null,
          2,
        ),
        comment: '',
      };
    },

    cancelFindingEdit(fIdx) {
      this.findingEditState[fIdx] = false;
      delete this.findingEditForms[fIdx];
    },

    async submitFindingEdit(fIdx) {
      const form = this.findingEditForms[fIdx];
      if (!form) {
        this.error = 'No edit form found for this finding.';
        return;
      }

      // Get the original finding to preserve unchanged fields
      const originalFinding = this.currentExtraction.findings[fIdx];
      if (!originalFinding) {
        this.error = 'Original finding not found.';
        return;
      }

      // Parse attributes JSON if provided
      let attributesObj = {};
      if (form.attributes_json.trim()) {
        try {
          attributesObj = JSON.parse(form.attributes_json);
          if (typeof attributesObj !== 'object' || Array.isArray(attributesObj)) {
            this.error = 'Attributes must be a JSON object (e.g., {"size": "3mm"})';
            return;
          }
        } catch (e) {
          this.error = 'Invalid JSON in attributes field: ' + e.message;
          return;
        }
      }

      // Convert attributes object to array of {key, value} pairs
      const attributesArray = Object.entries(attributesObj).map(([key, value]) => ({
        key,
        value: String(value),
      }));

      // Construct proposed_finding with edited values
      const proposed_finding = {
        finding_name: originalFinding.finding_name,
        presence: form.presence,
        location:
          form.location_body_region || form.location_specific_anatomy || form.location_laterality
            ? {
                body_region: form.location_body_region || null,
                specific_anatomy: form.location_specific_anatomy || null,
                laterality: form.location_laterality || null,
              }
            : null,
        attributes: attributesArray,
        report_text: originalFinding.report_text || null,
      };

      const payload = {
        correction_type: 'update_finding',
        target_finding_index: fIdx,
        proposed_finding: proposed_finding,
        comment: form.comment || null,
        username: this.correctionForm.username.trim() || 'talkasab',
      };

      try {
        this.correctionLoading = true;
        await this.apiFetch(`/extractions/${this.currentExtraction.id}/corrections`, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        this.cancelFindingEdit(fIdx);
        await this.loadCorrections(this.currentExtraction.id);
        this.success = 'Finding correction submitted successfully.';
      } catch (e) {
        this.error = e.message || 'Failed to submit finding correction';
      } finally {
        this.correctionLoading = false;
      }
    },

    parseStageStatus(statusMessage, statusEvent = null) {
      if (statusEvent && statusEvent.stage) {
        return {
          stage: String(statusEvent.stage).toLowerCase(),
          detail: statusEvent.detail || null,
        };
      }
      if (!statusMessage) return null;

      const trimmed = statusMessage.trim();

      const match = trimmed.match(/^\[stage:([a-z_]+)\]\s*(.*)$/i);
      if (match) {
        return {
          stage: match[1].toLowerCase(),
          detail: (match[2] || '').trim(),
        };
      }

      return {
        stage: null,
        detail: trimmed,
      };
    },

    formatStageDetail(detail) {
      if (!detail) return null;
      const humanize = (value) =>
        value
          .split('_')
          .filter(Boolean)
          .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
          .join(' ');
      const DETAIL_LABELS = {
        starting: 'Starting extraction',
        retrieving_report: 'Retrieving report',
        validating_model_configuration: 'Validating model configuration',
        start: 'Starting stage',
        calling_model: 'Calling model',
        model_call_complete: 'Model call complete',
        model_retrying: 'Retrying model call',
        agent_status: 'Agent status update',
        validating_extraction_results: 'Validating extraction results',
        saving_extraction_results: 'Saving extraction results',
        extraction_complete: 'Extraction complete',
        extraction_failed: 'Extraction failed',
      };
      if (DETAIL_LABELS[detail]) return DETAIL_LABELS[detail];
      if (detail.startsWith('extraction_failed:')) {
        return `Failure code: ${detail}`;
      }
      return humanize(detail);
    },

    stageLabel(statusMessage, statusEvent = null) {
      const parsed = this.parseStageStatus(statusMessage, statusEvent);
      if (!parsed) return null;
      const STAGE_LABELS = {
        queued: 'Queued',
        preflight: 'Preflight checks',
        sectionize: 'Parsing report sections',
        extract_sections: 'Extracting findings',
        merge_dedupe: 'Merging results',
        repair_failed_sections: 'Repairing failed sections',
        review: 'Reviewing extractions',
        validate_output: 'Validating output',
        persist: 'Saving results',
        completed: 'Complete',
        completed_with_warnings: 'Complete (warnings)',
        failed: 'Failed',
      };
      if (parsed.stage && STAGE_LABELS[parsed.stage]) return STAGE_LABELS[parsed.stage];
      if (parsed.stage)
        return parsed.stage
          .split('_')
          .filter(Boolean)
          .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
          .join(' ');
      return this.formatStageDetail(parsed.detail);
    },

    stageDetail(statusMessage, statusEvent = null) {
      const parsed = this.parseStageStatus(statusMessage, statusEvent);
      if (!parsed || !parsed.detail) return null;
      return this.formatStageDetail(parsed.detail);
    },

    codingForFinding(fIdx) {
      const finding = this.currentExtraction?.findings?.[fIdx];
      const coding = finding?.coding?.finding_code;
      if (!coding || coding.status !== 'coded') return null;
      return coding;
    },

    locationCodingForFinding(fIdx) {
      const finding = this.currentExtraction?.findings?.[fIdx];
      const coding = finding?.coding?.location_code;
      if (!coding || coding.status !== 'coded') return null;
      return coding;
    },

    codingSummary() {
      const findings = this.currentExtraction?.findings || [];
      let codedCount = 0;
      let unresolvedCount = 0;
      let sawCoding = false;
      const unresolved = [];
      for (let i = 0; i < findings.length; i++) {
        const finding = findings[i];
        const findingCode = finding?.coding?.finding_code;
        if (!findingCode) continue;
        sawCoding = true;
        if (findingCode.status === 'coded') {
          codedCount += 1;
        } else if (findingCode.status === 'unmapped') {
          unresolvedCount += 1;
          unresolved.push({
            finding_name: finding.finding_name || '(unnamed finding)',
            finding_index: i,
          });
        }
      }
      if (!sawCoding) return null;
      return { codedCount, unresolvedCount, unresolved };
    },

    codingMethodBadgeClass(method) {
      switch (method) {
        case 'exact':
          return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300';
        case 'synonym':
          return 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-300';
        case 'search':
          return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300';
        case 'agent':
          return 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300';
        default:
          return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';
      }
    },

    hasValidationIssues() {
      return this.validationWarningCount() > 0;
    },

    validationWarningCount() {
      const vr = this.currentExtraction?.validation_result;
      if (!vr) return 0;
      return (vr.coverage_warnings?.length || 0) + (vr.verbatim_errors?.length || 0);
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
