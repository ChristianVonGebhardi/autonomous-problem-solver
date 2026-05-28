/**
 * GuardRail VS Code Extension
 *
 * Provides real-time detection of AI-hallucinated package dependencies.
 * Hooks into document save events and surfaces inline diagnostics.
 */
import * as vscode from 'vscode';
import * as cp from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

// ─── Types ────────────────────────────────────────────────────────────────────

interface GuardRailResult {
  package_name: string;
  ecosystem: string;
  risk_score: number;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  exists_on_registry: boolean;
  flags: string[];
  remediation?: string;
  heuristics?: {
    similar_packages: string[];
    edit_distance?: number;
  };
}

interface GuardRailReport {
  manifest_path: string;
  ecosystem: string;
  summary: {
    total: number;
    blocked: number;
    warned: number;
    clean: number;
  };
  results: GuardRailResult[];
  scan_duration_ms: number;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const MANIFEST_FILES = new Set([
  'requirements.txt',
  'package.json',
  'Cargo.toml',
  'go.mod',
  'pyproject.toml',
  'Pipfile',
]);

const RISK_SEVERITY: Record<string, vscode.DiagnosticSeverity> = {
  LOW: vscode.DiagnosticSeverity.Information,
  MEDIUM: vscode.DiagnosticSeverity.Warning,
  HIGH: vscode.DiagnosticSeverity.Warning,
  CRITICAL: vscode.DiagnosticSeverity.Error,
};

// ─── Extension State ──────────────────────────────────────────────────────────

let diagnosticCollection: vscode.DiagnosticCollection;
let statusBarItem: vscode.StatusBarItem;
let outputChannel: vscode.OutputChannel;
let scanDebounceTimers = new Map<string, NodeJS.Timeout>();

// ─── Activation ───────────────────────────────────────────────────────────────

export function activate(context: vscode.ExtensionContext) {
  diagnosticCollection = vscode.languages.createDiagnosticCollection('guardrail');
  outputChannel = vscode.window.createOutputChannel('GuardRail');

  statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left,
    100
  );
  statusBarItem.command = 'guardrail.scanManifest';
  statusBarItem.text = '$(shield) GuardRail';
  statusBarItem.tooltip = 'Click to scan dependencies';
  statusBarItem.show();

  // Register commands
  context.subscriptions.push(
    vscode.commands.registerCommand('guardrail.scanManifest', scanCurrentDocument),
    vscode.commands.registerCommand('guardrail.checkPackage', checkPackageUnderCursor),
    vscode.commands.registerCommand('guardrail.clearCache', clearCache),

    // Auto-scan on save
    vscode.workspace.onDidSaveTextDocument(onDocumentSaved),

    // Scan already-open manifest files
    vscode.workspace.onDidOpenTextDocument(onDocumentOpened),

    diagnosticCollection,
    statusBarItem,
    outputChannel,
  );

  // Scan all currently open manifest files
  vscode.workspace.textDocuments.forEach(doc => {
    if (isManifestFile(doc)) {
      scheduleScan(doc);
    }
  });

  outputChannel.appendLine('GuardRail extension activated');
}

export function deactivate() {
  scanDebounceTimers.forEach(t => clearTimeout(t));
  diagnosticCollection.clear();
}

// ─── Event Handlers ───────────────────────────────────────────────────────────

function onDocumentSaved(doc: vscode.TextDocument) {
  const config = getConfig();
  if (!config.enable || !config.scanOnSave) return;
  if (isManifestFile(doc)) {
    scheduleScan(doc);
  }
}

function onDocumentOpened(doc: vscode.TextDocument) {
  const config = getConfig();
  if (!config.enable) return;
  if (isManifestFile(doc)) {
    scheduleScan(doc, 2000); // Delay scan slightly on open
  }
}

function scheduleScan(doc: vscode.TextDocument, delay = 500) {
  const key = doc.uri.toString();
  const existing = scanDebounceTimers.get(key);
  if (existing) clearTimeout(existing);

  const timer = setTimeout(() => {
    scanDebounceTimers.delete(key);
    scanDocument(doc).catch(err => {
      outputChannel.appendLine(`Scan error: ${err.message}`);
    });
  }, delay);

  scanDebounceTimers.set(key, timer);
}

// ─── Core Scan Logic ──────────────────────────────────────────────────────────

async function scanDocument(doc: vscode.TextDocument): Promise<void> {
  const config = getConfig();
  if (!config.enable) return;

  const fileName = path.basename(doc.uri.fsPath);
  if (!MANIFEST_FILES.has(fileName)) return;

  updateStatusBar('scanning');
  outputChannel.appendLine(`Scanning: ${doc.uri.fsPath}`);

  try {
    const report = await runGuardRail(doc.uri.fsPath, config);
    if (!report) {
      updateStatusBar('idle');
      return;
    }

    applyDiagnostics(doc, report);

    const { blocked, warned } = report.summary;
    if (blocked > 0) {
      updateStatusBar('blocked', blocked);
    } else if (warned > 0) {
      updateStatusBar('warned', warned);
    } else {
      updateStatusBar('clean');
    }

    outputChannel.appendLine(
      `Scan complete: ${report.summary.total} packages, ` +
      `${blocked} blocked, ${warned} warned (${report.scan_duration_ms.toFixed(0)}ms)`
    );
  } catch (err: any) {
    outputChannel.appendLine(`Scan failed: ${err.message}`);
    updateStatusBar('error');
  }
}

async function runGuardRail(
  filePath: string,
  config: ReturnType<typeof getConfig>
): Promise<GuardRailReport | null> {
  return new Promise((resolve, reject) => {
    const args = [
      'scan', filePath,
      '--format', 'json',
    ];

    if (config.policyServer) {
      args.push('--policy-server', config.policyServer);
    }

    const proc = cp.spawn(config.guardrailPath, args, {
      cwd: path.dirname(filePath),
      env: { ...process.env },
    });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (chunk: Buffer) => { stdout += chunk.toString(); });
    proc.stderr.on('data', (chunk: Buffer) => { stderr += chunk.toString(); });

    proc.on('close', (code) => {
      if (stderr) outputChannel.appendLine(`[stderr] ${stderr.trim()}`);

      if (!stdout.trim()) {
        if (code === 2) {
          reject(new Error(`GuardRail config error: ${stderr}`));
        } else {
          resolve(null);
        }
        return;
      }

      try {
        const report: GuardRailReport = JSON.parse(stdout);
        resolve(report);
      } catch {
        reject(new Error(`Failed to parse GuardRail output: ${stdout.slice(0, 200)}`));
      }
    });

    proc.on('error', (err) => {
      if ((err as any).code === 'ENOENT') {
        reject(new Error(
          `GuardRail CLI not found at '${config.guardrailPath}'. ` +
          `Install with: pip install guardrail-cli`
        ));
      } else {
        reject(err);
      }
    });

    // Timeout after 30 seconds
    setTimeout(() => {
      proc.kill();
      reject(new Error('GuardRail scan timed out after 30s'));
    }, 30_000);
  });
}

function applyDiagnostics(doc: vscode.TextDocument, report: GuardRailReport) {
  const diagnostics: vscode.Diagnostic[] = [];
  const config = getConfig();

  for (const result of report.results) {
    if (result.risk_level === 'LOW') continue;

    // Find the package name in the document text
    const line = findPackageLine(doc, result.package_name);
    if (line === -1) continue;

    const lineText = doc.lineAt(line).text;
    const col = lineText.indexOf(result.package_name);
    const range = new vscode.Range(
      line, Math.max(0, col),
      line, col + result.package_name.length
    );

    const severity = getSeverity(result.risk_level, config.failLevel);
    const message = buildDiagnosticMessage(result);

    const diagnostic = new vscode.Diagnostic(range, message, severity);
    diagnostic.source = 'GuardRail';
    diagnostic.code = {
      value: `GR-${result.risk_level}`,
      target: vscode.Uri.parse(
        `https://github.com/guardrail-dev/guardrail/wiki/${result.risk_level}`
      ),
    };

    // Add related information
    if (result.heuristics?.similar_packages?.length) {
      diagnostic.relatedInformation = result.heuristics.similar_packages
        .slice(0, 3)
        .map(pkg => new vscode.DiagnosticRelatedInformation(
          new vscode.Location(doc.uri, range),
          `Similar known package: ${pkg}`
        ));
    }

    diagnostics.push(diagnostic);
  }

  diagnosticCollection.set(doc.uri, diagnostics);
}

// ─── Commands ─────────────────────────────────────────────────────────────────

async function scanCurrentDocument() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage('No active editor');
    return;
  }
  await scanDocument(editor.document);
}

async function checkPackageUnderCursor() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return;

  const position = editor.selection.active;
  const wordRange = editor.document.getWordRangeAtPosition(position, /[\w\-\.\/\@]+/);
  if (!wordRange) {
    vscode.window.showWarningMessage('No package name found under cursor');
    return;
  }

  const packageName = editor.document.getText(wordRange);
  const ecosystem = detectEcosystem(editor.document);
  if (!ecosystem) {
    vscode.window.showWarningMessage('Cannot detect ecosystem for this file');
    return;
  }

  const config = getConfig();
  updateStatusBar('scanning');

  return new Promise<void>((resolve) => {
    const args = ['check', packageName, '--ecosystem', ecosystem, '--format', 'json'];
    if (config.policyServer) args.push('--policy-server', config.policyServer);

    const proc = cp.spawn(config.guardrailPath, args);
    let stdout = '';
    proc.stdout.on('data', (d: Buffer) => stdout += d.toString());
    proc.on('close', () => {
      try {
        const result: GuardRailResult = JSON.parse(stdout);
        updateStatusBar(result.risk_level === 'LOW' ? 'clean' : 'warned', 1);

        const icon = result.risk_level === 'LOW' ? '✅' :
                     result.risk_level === 'CRITICAL' ? '🚫' : '⚠️';
        const msg = `${icon} ${result.package_name} — ${result.risk_level} (score: ${result.risk_score.toFixed(3)})`;

        if (result.risk_level === 'LOW') {
          vscode.window.showInformationMessage(msg);
        } else {
          vscode.window.showWarningMessage(
            result.remediation ? `${msg}\n${result.remediation}` : msg
          );
        }
      } catch {
        vscode.window.showErrorMessage('Could not parse GuardRail result');
      }
      resolve();
    });
    proc.on('error', () => {
      vscode.window.showErrorMessage('GuardRail CLI not found. Install with: pip install guardrail-cli');
      resolve();
    });
  });
}

async function clearCache() {
  const config = getConfig();
  const proc = cp.spawn(config.guardrailPath, ['--help']);
  // Clear by removing cache file
  const cacheDir = path.join(
    process.env.HOME || process.env.USERPROFILE || '',
    '.guardrail'
  );
  const cacheDb = path.join(cacheDir, 'cache.db');
  if (fs.existsSync(cacheDb)) {
    fs.unlinkSync(cacheDb);
    vscode.window.showInformationMessage('GuardRail cache cleared');
  } else {
    vscode.window.showInformationMessage('No cache to clear');
  }
}

// ─── Utilities ────────────────────────────────────────────────────────────────

function isManifestFile(doc: vscode.TextDocument): boolean {
  return MANIFEST_FILES.has(path.basename(doc.uri.fsPath));
}

function findPackageLine(doc: vscode.TextDocument, packageName: string): number {
  const text = doc.getText();
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes(packageName)) {
      return i;
    }
  }
  return -1;
}

function detectEcosystem(doc: vscode.TextDocument): string | null {
  const basename = path.basename(doc.uri.fsPath);
  const map: Record<string, string> = {
    'requirements.txt': 'pypi',
    'pyproject.toml': 'pypi',
    'Pipfile': 'pypi',
    'package.json': 'npm',
    'Cargo.toml': 'cargo',
    'go.mod': 'go',
  };
  return map[basename] || null;
}

function getSeverity(
  riskLevel: string,
  failLevel: string
): vscode.DiagnosticSeverity {
  if (failLevel === 'never') return vscode.DiagnosticSeverity.Information;

  if (riskLevel === 'CRITICAL') {
    return vscode.DiagnosticSeverity.Error;
  }
  if (riskLevel === 'HIGH') {
    return failLevel === 'warn'
      ? vscode.DiagnosticSeverity.Error
      : vscode.DiagnosticSeverity.Warning;
  }
  return vscode.DiagnosticSeverity.Warning;
}

function buildDiagnosticMessage(result: GuardRailResult): string {
  let msg = `[GuardRail] ${result.risk_level} risk (score: ${result.risk_score.toFixed(3)})`;

  if (!result.exists_on_registry) {
    msg += ` — Package not found on registry`;
  }

  if (result.heuristics?.similar_packages?.length) {
    msg += ` — Similar to: ${result.heuristics.similar_packages.slice(0, 2).join(', ')}`;
  }

  if (result.remediation) {
    msg += `\n${result.remediation}`;
  }

  return msg;
}

function updateStatusBar(
  state: 'idle' | 'scanning' | 'clean' | 'warned' | 'blocked' | 'error',
  count?: number
) {
  switch (state) {
    case 'scanning':
      statusBarItem.text = '$(shield) GuardRail $(sync~spin)';
      statusBarItem.backgroundColor = undefined;
      break;
    case 'clean':
      statusBarItem.text = '$(shield) GuardRail $(check)';
      statusBarItem.backgroundColor = undefined;
      statusBarItem.tooltip = 'All packages clean';
      break;
    case 'warned':
      statusBarItem.text = `$(shield) GuardRail $(warning) ${count || ''} warning(s)`;
      statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
      break;
    case 'blocked':
      statusBarItem.text = `$(shield) GuardRail $(error) ${count || ''} BLOCKED`;
      statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
      break;
    case 'error':
      statusBarItem.text = '$(shield) GuardRail $(error)';
      statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
      break;
    default:
      statusBarItem.text = '$(shield) GuardRail';
      statusBarItem.backgroundColor = undefined;
  }
}

function getConfig() {
  const cfg = vscode.workspace.getConfiguration('guardrail');
  return {
    enable: cfg.get<boolean>('enable', true),
    guardrailPath: cfg.get<string>('guardrailPath', 'guardrail'),
    scanOnSave: cfg.get<boolean>('scanOnSave', true),
    failLevel: cfg.get<string>('failLevel', 'block'),
    policyServer: cfg.get<string>('policyServer', ''),
    showInlineHints: cfg.get<boolean>('showInlineHints', true),
  };
}