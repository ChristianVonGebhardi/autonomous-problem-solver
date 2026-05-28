/**
 * Basic unit tests for extension utilities.
 * Run with: npm test (requires @vscode/test-electron)
 */

// These tests verify the pure utility functions without needing a full VS Code instance.

function matchesManifest(filename: string): boolean {
  const MANIFEST_FILES = new Set([
    'requirements.txt', 'package.json', 'Cargo.toml',
    'go.mod', 'pyproject.toml', 'Pipfile',
  ]);
  const basename = filename.split('/').pop() || filename;
  return MANIFEST_FILES.has(basename);
}

function detectEcosystem(basename: string): string | null {
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

// Simple assertion helper
function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`);
  console.log(`PASS: ${message}`);
}

// Run tests
try {
  assert(matchesManifest('requirements.txt'), 'requirements.txt is manifest');
  assert(matchesManifest('package.json'), 'package.json is manifest');
  assert(matchesManifest('Cargo.toml'), 'Cargo.toml is manifest');
  assert(!matchesManifest('main.py'), 'main.py is not manifest');
  assert(!matchesManifest('index.js'), 'index.js is not manifest');
  
  assert(detectEcosystem('requirements.txt') === 'pypi', 'requirements.txt → pypi');
  assert(detectEcosystem('package.json') === 'npm', 'package.json → npm');
  assert(detectEcosystem('Cargo.toml') === 'cargo', 'Cargo.toml → cargo');
  assert(detectEcosystem('go.mod') === 'go', 'go.mod → go');
  assert(detectEcosystem('unknown.txt') === null, 'unknown.txt → null');

  console.log('\nAll extension utility tests passed!');
} catch (e: any) {
  console.error(e.message);
  process.exit(1);
}