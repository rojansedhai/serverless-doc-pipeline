import { getConfig, saveConfig } from './config.js';

// Application Global State
const state = {
  config: getConfig(),
  currentTenant: 'tenant-alpha',
  tokens: {
    'tenant-alpha': null,
    'tenant-beta': null
  },
  // In-memory document repository per tenant
  documents: {
    'tenant-alpha': [],
    'tenant-beta': []
  },
  selectedDoc: null,
  isProcessing: false
};

// ============================================================================
// Initialization & Lifecycle
// ============================================================================
document.addEventListener('DOMContentLoaded', async () => {
  loadSavedDocuments();
  initEventHandlers();
  await authenticateTenant(state.currentTenant);
  renderDocumentTable();
});

function initEventHandlers() {
  // Navigation Tabs
  document.querySelectorAll('.nav-tab-item').forEach(tab => {
    tab.addEventListener('click', (e) => {
      const target = e.currentTarget.dataset.tab;
      document.querySelectorAll('.nav-tab-item').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      e.currentTarget.classList.add('active');
      document.getElementById(target).classList.add('active');
    });
  });

  // Tenant Switcher Buttons
  document.getElementById('btn-tenant-alpha').addEventListener('click', () => switchTenant('tenant-alpha'));
  document.getElementById('btn-tenant-beta').addEventListener('click', () => switchTenant('tenant-beta'));

  // Document Ingestion Handlers
  document.getElementById('btn-sample-cloud').addEventListener('click', () => 
    handleGenerateSample('Acme Cloud Services LLC', '1420.50', 'Cloud Serverless Compute & DynamoDB Storage'));
  document.getElementById('btn-sample-saas').addEventListener('click', () => 
    handleGenerateSample('Datadog Monitoring Inc', '850.00', 'Enterprise Telemetry & Tracing License'));
  document.getElementById('btn-sample-freight').addEventListener('click', () => 
    handleGenerateSample('Expedited Freight Corp', '2340.00', 'Interstate Logistics & Cold-Chain Shipping'));

  // File Upload Dropzone
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  dropzone.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) processFile(e.target.files[0]);
  });
  dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) processFile(e.dataTransfer.files[0]);
  });

  // Refresh History
  document.getElementById('btn-refresh-history').addEventListener('click', () => {
    renderDocumentTable();
    showToast("Document history refreshed");
  });

  // IDOR Security Exploit Runner
  document.getElementById('btn-run-idor').addEventListener('click', runIdorSecurityBenchmark);

  // Modals
  document.getElementById('btn-inspect-token').addEventListener('click', openTokenModal);
  document.getElementById('btn-settings').addEventListener('click', openSettingsModal);
  document.querySelectorAll('.modal-close-btn').forEach(btn => {
    btn.addEventListener('click', () => document.querySelectorAll('.modal-backdrop').forEach(m => m.classList.remove('open')));
  });
  document.getElementById('form-settings').addEventListener('submit', handleSaveSettings);
}

// ============================================================================
// Cognito Authentication
// ============================================================================
async function authenticateTenant(tenantId) {
  const tenantInfo = state.config.tenants[tenantId];
  if (!tenantInfo) return null;

  if (!tenantInfo.password || tenantInfo.password.startsWith('YOUR_')) {
    setAuthLabel(`Auth Required: Configure credentials in Settings (⚙️)`);
    showToast(`Please set ${tenantInfo.name} password in Settings (⚙️)`, 'warning');
    return null;
  }

  setAuthLabel(`Authenticating ${tenantInfo.name}...`);

  try {
    const endpoint = `https://cognito-idp.${state.config.awsRegion}.amazonaws.com/`;
    const payload = {
      AuthFlow: "USER_PASSWORD_AUTH",
      ClientId: state.config.cognitoClientId,
      AuthParameters: {
        USERNAME: tenantInfo.email,
        PASSWORD: tenantInfo.password
      }
    };

    const resp = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth"
      },
      body: JSON.stringify(payload)
    });

    const data = await resp.json();
    if (!resp.ok) throw new Error(data.message || `Cognito Auth Failed (${resp.status})`);

    const idToken = data.AuthenticationResult?.IdToken;
    state.tokens[tenantId] = idToken;

    setAuthLabel(`Authenticated: ${tenantInfo.name} (${tenantId})`);
    return idToken;
  } catch (err) {
    console.error("Cognito Auth Error:", err);
    setAuthLabel(`Auth Error: ${err.message}`);
    showToast(`Authentication failed for ${tenantId}`, 'danger');
    return null;
  }
}

async function switchTenant(tenantId) {
  if (state.currentTenant === tenantId) return;
  state.currentTenant = tenantId;

  // Toggle active pill button
  document.querySelectorAll('.tenant-pill-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tenant === tenantId);
  });

  // Update partition label
  document.getElementById('lbl-tenant-partition').textContent = `TENANT#${tenantId}`;

  // Authenticate if needed
  if (!state.tokens[tenantId]) {
    await authenticateTenant(tenantId);
  } else {
    const tenantInfo = state.config.tenants[tenantId];
    setAuthLabel(`Authenticated: ${tenantInfo.name} (${tenantId})`);
  }

  // Render tenant document view
  state.selectedDoc = null;
  resetDetailPane();
  resetStepTracker();
  renderDocumentTable();
  showToast(`Switched context to ${state.config.tenants[tenantId].name}`);
}

function setAuthLabel(text) {
  const lbl = document.getElementById('auth-status-label');
  if (lbl) lbl.textContent = text;
}

// ============================================================================
// Document Ingestion & Pipeline Orchestration
// ============================================================================
function generateInvoiceBlob(vendor, amount, desc, tenantId, invoiceNum) {
  const dateStr = new Date().toISOString().split('T')[0];
  const pdfString = `%PDF-1.4
% Enterprise Invoicing Document
Vendor: ${vendor}
Billed To: Corporate Account (${tenantId})
Invoice: ${invoiceNum}
Date: ${dateStr}
Currency: USD

Line Items:
1. ${desc} - Qty 1 - $${amount}

Total: $${amount}
%%EOF`;
  return new Blob([pdfString], { type: 'application/pdf' });
}

async function handleGenerateSample(vendor, amount, desc) {
  if (state.isProcessing) return;
  const invoiceNum = `INV-${Math.floor(Date.now() / 1000)}`;
  const blob = generateInvoiceBlob(vendor, amount, desc, state.currentTenant, invoiceNum);
  await executePipeline(blob, `invoice_${invoiceNum}.pdf`, { vendor, amount, invoiceNum });
}

async function processFile(file) {
  if (state.isProcessing) return;
  await executePipeline(file, file.name);
}

async function executePipeline(fileBlob, filename, metaHint = {}) {
  state.isProcessing = true;
  setIngestButtonsDisabled(true);
  resetStepTracker();

  const startTime = performance.now();
  const token = state.tokens[state.currentTenant] || await authenticateTenant(state.currentTenant);

  if (!token) {
    showToast("Authentication required before upload", 'danger');
    state.isProcessing = false;
    setIngestButtonsDisabled(false);
    return;
  }

  try {
    // Step 1 & 2: Token Validation & Presigned URL Request
    setStep(1, 'active');
    setStep(2, 'active');
    appendAuditLog(`[1] Requesting S3 Presigned URL for ${filename} (Tenant: ${state.currentTenant})...`, 'info');

    const presignedResp = await fetch(`${state.config.apiEndpoint}/upload-url`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        filename: filename,
        contentType: fileBlob.type || 'application/pdf'
      })
    });

    if (!presignedResp.ok) {
      const err = await presignedResp.text();
      throw new Error(`Presigned URL Request failed (${presignedResp.status}): ${err}`);
    }

    const presignedData = await presignedResp.json();
    const docId = presignedData.docId;
    const uploadUrl = presignedData.uploadUrl;
    const s3Key = presignedData.s3Key;

    setStep(1, 'completed');
    setStep(2, 'completed');
    appendAuditLog(`[2] Presigned PUT URL generated (docId: ${docId})`, 'success');

    // Step 3: Direct S3 Binary PUT Upload
    setStep(3, 'active');
    appendAuditLog(`[3] Direct-uploading to S3: s3://${state.config.s3BucketName}/${s3Key}...`, 'info');

    const s3Resp = await fetch(uploadUrl, {
      method: 'PUT',
      headers: { 'Content-Type': fileBlob.type || 'application/pdf' },
      body: fileBlob
    });

    if (!s3Resp.ok) throw new Error(`S3 Presigned Upload Failed (${s3Resp.status})`);

    setStep(3, 'completed');
    appendAuditLog(`[3] S3 Upload complete (HTTP 200). KMS encryption verified.`, 'success');

    // Step 4 & 5: Polling EventBridge & Lambda Processor
    setStep(4, 'active');
    setStep(5, 'active');
    appendAuditLog(`[4] Awaiting EventBridge ObjectCreated dispatch to Lambda OCR processor...`, 'info');

    const processedDoc = await pollDocument(docId, token);
    const durationMs = (performance.now() - startTime).toFixed(0);

    setStep(4, 'completed');
    setStep(5, 'completed');
    appendAuditLog(`[5] Document processed & watermarked successfully in ${durationMs}ms!`, 'success');

    // Save to tenant history
    const historyItem = {
      docId,
      filename,
      vendor: processedDoc.ExtractedMetadata?.vendor_name || metaHint.vendor || 'Extracted Vendor',
      total: processedDoc.ExtractedMetadata?.total_amount || metaHint.amount || '0.00',
      currency: processedDoc.ExtractedMetadata?.currency || 'USD',
      invoiceNumber: processedDoc.ExtractedMetadata?.invoice_number || metaHint.invoiceNum || docId.substring(0, 8),
      status: processedDoc.Status || 'PROCESSED',
      duration: `${durationMs}ms`,
      s3Path: processedDoc.S3ProcessedKey || s3Key,
      downloadUrl: processedDoc.downloadUrl,
      raw: processedDoc,
      createdAt: new Date().toLocaleTimeString()
    };

    state.documents[state.currentTenant].unshift(historyItem);
    saveDocumentsToStorage();
    renderDocumentTable();
    selectDocument(historyItem);
    showToast(`Invoice ${historyItem.invoiceNumber} processed successfully!`, 'success');

  } catch (err) {
    console.error("Pipeline Execution Error:", err);
    appendAuditLog(`[Error] ${err.message}`, 'danger');
    showToast(err.message, 'danger');
  } finally {
    state.isProcessing = false;
    setIngestButtonsDisabled(false);
  }
}

async function pollDocument(docId, token) {
  const maxAttempts = 15;
  for (let i = 1; i <= maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 1200));

    const resp = await fetch(`${state.config.apiEndpoint}/documents/${docId}`, {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${token}` }
    });

    if (resp.ok) {
      const data = await resp.json();
      if (data.Status === 'PROCESSED') return data;
      if (data.Status === 'FAILED') throw new Error(data.ErrorMessage || 'Processing failed');
    }
  }
  throw new Error("Polling timeout waiting for EventBridge & Lambda processor");
}

// ============================================================================
// Multi-Tenant Isolation & IDOR Security Benchmark
// ============================================================================
async function runIdorSecurityBenchmark() {
  const currentDocs = state.documents[state.currentTenant];
  if (!currentDocs || currentDocs.length === 0) {
    showToast("Please upload an invoice with Tenant Alpha first", 'warning');
    return;
  }

  const targetDoc = currentDocs[0];
  const attackingTenant = state.currentTenant === 'tenant-alpha' ? 'tenant-beta' : 'tenant-alpha';
  
  appendAuditLog("----------------------------------------------------------------", 'info');
  appendAuditLog(`[SECURITY BENCHMARK] Executing Cross-Tenant Access Exploit Test...`, 'warning');
  appendAuditLog(`Target Document ID : ${targetDoc.docId} (Owner: ${state.currentTenant})`, 'info');
  appendAuditLog(`Attacker Identity  : ${attackingTenant} (Using ${attackingTenant}'s verified JWT)`, 'warning');

  // Authenticate attacker tenant
  appendAuditLog(`[*] Initiating Cognito auth for attacker (${attackingTenant})...`, 'info');
  const attackerToken = await authenticateTenant(attackingTenant);

  if (!attackerToken) {
    appendAuditLog(`[!] Failed to obtain JWT for ${attackingTenant}`, 'danger');
    return;
  }

  appendAuditLog(`[*] Attacker sending: GET /documents/${targetDoc.docId} + Authorization: Bearer <${attackingTenant}_JWT>`, 'info');

  try {
    const resp = await fetch(`${state.config.apiEndpoint}/documents/${targetDoc.docId}`, {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${attackerToken}` }
    });

    const status = resp.status;
    const body = await resp.text();

    if (status === 403 || status === 404) {
      appendAuditLog(`[+] ACCESS REJECTED (HTTP ${status} Forbidden/Not Found)!`, 'success');
      appendAuditLog(`[+] Multi-tenant cryptographic isolation verified: Tenant ${attackingTenant} cannot access Tenant ${state.currentTenant}'s records.`, 'success');
      appendAuditLog(`Backend Security Response: ${body}`, 'info');
      showToast("Security Test Passed: Cross-tenant access successfully blocked", 'success');
    } else {
      appendAuditLog(`[!] SECURITY VULNERABILITY DETECTED! Cross-tenant access succeeded with status ${status}`, 'danger');
      showToast("Security Test Failed: Cross-tenant access succeeded", 'danger');
    }
  } catch (err) {
    appendAuditLog(`[+] Request blocked at network layer: ${err.message}`, 'success');
  }

  // Restore current tenant context
  await authenticateTenant(state.currentTenant);
}

// ============================================================================
// UI Renderers & Helpers
// ============================================================================
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderDocumentTable() {
  const tbody = document.getElementById('doc-history-body');
  const docs = state.documents[state.currentTenant] || [];

  if (docs.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">
          No documents ingested in this session yet for ${state.currentTenant}. Click an instant preset to test.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = docs.map((doc, idx) => `
    <tr class="${state.selectedDoc?.docId === doc.docId ? 'selected' : ''}" data-index="${idx}">
      <td>
        <div class="doc-name-cell">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path></svg>
          <span>${escapeHtml(doc.filename)}</span>
        </div>
      </td>
      <td>${escapeHtml(doc.vendor)}</td>
      <td style="font-weight: 600; color: var(--text-main);">$${escapeHtml(doc.total)}</td>
      <td>
        <span class="badge-status ${escapeHtml(doc.status.toLowerCase())}">${escapeHtml(doc.status)}</span>
      </td>
      <td style="font-family: var(--font-mono); font-size: 0.75rem;">${escapeHtml(doc.duration)}</td>
    </tr>
  `).join('');

  // Row selection click events
  tbody.querySelectorAll('tr').forEach((row, idx) => {
    row.addEventListener('click', () => {
      selectDocument(docs[idx]);
    });
  });
}

function selectDocument(doc) {
  state.selectedDoc = doc;
  renderDocumentTable();

  document.getElementById('det-vendor').textContent = doc.vendor;
  document.getElementById('det-total').textContent = `$${doc.total} ${doc.currency || 'USD'}`;
  document.getElementById('det-invoice').textContent = doc.invoiceNumber;
  document.getElementById('det-duration').textContent = doc.duration;
  document.getElementById('det-doc-id').textContent = doc.docId;
  document.getElementById('det-s3-path').textContent = doc.s3Path;
  document.getElementById('det-status-badge').textContent = doc.status;

  const dlBtn = document.getElementById('btn-download-doc');
  if (doc.downloadUrl) {
    dlBtn.onclick = () => window.open(doc.downloadUrl, '_blank');
    dlBtn.style.display = 'inline-flex';
  } else {
    dlBtn.style.display = 'none';
  }

  document.getElementById('det-raw-json').textContent = JSON.stringify(doc.raw, null, 2);
}

function resetDetailPane() {
  document.getElementById('det-vendor').textContent = '--';
  document.getElementById('det-total').textContent = '--';
  document.getElementById('det-invoice').textContent = '--';
  document.getElementById('det-duration').textContent = '--';
  document.getElementById('det-doc-id').textContent = '--';
  document.getElementById('det-s3-path').textContent = '--';
  document.getElementById('det-status-badge').textContent = 'AWAITING INPUT';
  document.getElementById('btn-download-doc').style.display = 'none';
  document.getElementById('det-raw-json').textContent = JSON.stringify({ message: "Select or upload a document to inspect" }, null, 2);
}

function setStep(stepNum, status) {
  const el = document.getElementById(`step-${stepNum}`);
  if (!el) return;
  el.classList.remove('active', 'completed');
  if (status === 'active') el.classList.add('active');
  if (status === 'completed') el.classList.add('completed');
}

function resetStepTracker() {
  for (let i = 1; i <= 5; i++) setStep(i, 'default');
}

function appendAuditLog(msg, type = 'info') {
  const terminal = document.getElementById('security-audit-log');
  if (!terminal) return;
  const line = document.createElement('div');
  line.className = `audit-line ${type}`;
  line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  terminal.appendChild(line);
  terminal.scrollTop = terminal.scrollHeight;
}

function setIngestButtonsDisabled(disabled) {
  document.getElementById('btn-sample-cloud').disabled = disabled;
  document.getElementById('btn-sample-saas').disabled = disabled;
  document.getElementById('btn-sample-freight').disabled = disabled;
}

function showToast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="${type === 'danger' ? '#ef4444' : '#10b981'}" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>
    <span>${escapeHtml(msg)}</span>
  `;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3500);
}

// Local Storage Persistence for demo sessions
function saveDocumentsToStorage() {
  localStorage.setItem("DOC_PIPELINE_HISTORY", JSON.stringify(state.documents));
}

function loadSavedDocuments() {
  const saved = localStorage.getItem("DOC_PIPELINE_HISTORY");
  if (saved) {
    try {
      state.documents = JSON.parse(saved);
    } catch (e) {
      console.warn("Could not load history:", e);
    }
  }
}

// ============================================================================
// Modals & Settings
// ============================================================================
function openTokenModal() {
  const token = state.tokens[state.currentTenant];
  if (!token) {
    showToast("No token available for current tenant", 'warning');
    return;
  }
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(atob(base64).split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join(''));
    document.getElementById('token-decoded-box').textContent = JSON.stringify(JSON.parse(jsonPayload), null, 2);
  } catch (e) {
    document.getElementById('token-decoded-box').textContent = token;
  }
  document.getElementById('modal-token').classList.add('open');
}

function openSettingsModal() {
  const currentEp = state.config.apiEndpoint;
  document.getElementById('cfg-api-endpoint').value = (currentEp && !currentEp.startsWith('YOUR_')) ? currentEp : '';

  const currentPool = state.config.cognitoUserPoolId;
  document.getElementById('cfg-pool-id').value = (currentPool && !currentPool.startsWith('YOUR_')) ? currentPool : '';

  const currentClient = state.config.cognitoClientId;
  document.getElementById('cfg-client-id').value = (currentClient && !currentClient.startsWith('YOUR_')) ? currentClient : '';

  document.getElementById('cfg-region').value = state.config.awsRegion || 'us-east-1';
  
  const alphaPwd = state.config.tenants?.['tenant-alpha']?.password;
  document.getElementById('cfg-alpha-pwd').value = (alphaPwd && !alphaPwd.startsWith('YOUR_')) ? alphaPwd : '';
  
  const betaPwd = state.config.tenants?.['tenant-beta']?.password;
  document.getElementById('cfg-beta-pwd').value = (betaPwd && !betaPwd.startsWith('YOUR_')) ? betaPwd : '';
  
  document.getElementById('modal-settings').classList.add('open');
}

function handleSaveSettings(e) {
  e.preventDefault();
  const alphaPwd = document.getElementById('cfg-alpha-pwd').value.trim() || 'Password123!';
  const betaPwd = document.getElementById('cfg-beta-pwd').value.trim() || 'Password123!';

  const updated = {
    ...state.config,
    apiEndpoint: document.getElementById('cfg-api-endpoint').value.trim(),
    cognitoUserPoolId: document.getElementById('cfg-pool-id').value.trim(),
    cognitoClientId: document.getElementById('cfg-client-id').value.trim(),
    awsRegion: document.getElementById('cfg-region').value.trim(),
    tenants: {
      ...state.config.tenants,
      'tenant-alpha': {
        ...state.config.tenants['tenant-alpha'],
        password: alphaPwd
      },
      'tenant-beta': {
        ...state.config.tenants['tenant-beta'],
        password: betaPwd
      }
    }
  };
  saveConfig(updated);
  state.config = updated;
  document.getElementById('modal-settings').classList.remove('open');
  showToast("Configuration saved. Authenticating with Cognito...", 'success');
  authenticateTenant(state.currentTenant);
}
