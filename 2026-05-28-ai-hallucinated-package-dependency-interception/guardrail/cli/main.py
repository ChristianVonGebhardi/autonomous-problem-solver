"""
GuardRail CLI — main entry point.

Commands:
  guardrail scan <manifest>      Scan a manifest file
  guardrail check <package>      Check a single package
  guardrail install-shim <pm>    Install package manager shim
  guardrail server               Start policy server proxy
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

console = Console(stderr=False)
err_console = Console(stderr=True)


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@click.group()
@click.version_option("0.1.0", prog_name="guardrail")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx, verbose):
    """GuardRail — AI Package Hallucination Interception Tool.
    
    Validates AI-generated package dependencies against live registries,
    heuristics, and reputation data to prevent supply-chain attacks.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logging(verbose)


@cli.command("scan")
@click.argument("manifest", type=click.Path(exists=True))
@click.option("--ecosystem", "-e", default=None,
              type=click.Choice(["pypi", "npm", "cargo", "go", "maven"]),
              help="Force ecosystem (auto-detected from filename if omitted)")
@click.option("--format", "-f", "output_format", default="table",
              type=click.Choice(["table", "json", "sarif", "summary"]),
              help="Output format")
@click.option("--strict", is_flag=True,
              help="Exit with code 1 if any warnings found (not just blocks)")
@click.option("--fail-on", default="block",
              type=click.Choice(["warn", "block", "never"]),
              help="When to exit with non-zero code")
@click.option("--policy-server", default=None,
              envvar="GUARDRAIL_POLICY_SERVER",
              help="Policy server URL")
@click.option("--no-cache", is_flag=True, help="Bypass local cache")
@click.option("--output", "-o", default=None, help="Write output to file")
@click.pass_context
def scan_cmd(ctx, manifest, ecosystem, output_format, strict, fail_on, policy_server, no_cache, output):
    """Scan a manifest file for suspicious dependencies."""
    asyncio.run(_scan_async(
        ctx, manifest, ecosystem, output_format, strict, fail_on,
        policy_server, no_cache, output
    ))


async def _scan_async(
    ctx, manifest, ecosystem, output_format, strict, fail_on,
    policy_server, no_cache, output
):
    from core.validator import Validator
    from core.cache import Cache
    from core.models import Ecosystem, RiskLevel
    from core.policy import PolicyClient

    verbose = ctx.obj.get("verbose", False)

    # Resolve ecosystem
    eco = None
    if ecosystem:
        eco = Ecosystem(ecosystem)
    else:
        eco = Ecosystem.from_manifest(manifest)
        if eco is None:
            err_console.print(f"[red]Cannot auto-detect ecosystem from: {manifest}[/red]")
            err_console.print("Use --ecosystem to specify: pypi, npm, cargo, go, maven")
            sys.exit(2)

    # Setup components
    cache = Cache() if not no_cache else None
    policy_client = None
    if policy_server:
        policy_client = PolicyClient(policy_server)

    if cache is None:
        from core.cache import Cache as _Cache
        # Create a temp in-memory-like cache with very short TTL
        cache = _Cache(db_path=":memory:", ttl=0)

    async with Validator(cache=cache, policy_client=policy_client) as validator:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=err_console,
            transient=True,
        ) as progress:
            task = progress.add_task(f"Scanning {manifest}...", total=None)
            report = await validator.scan_manifest(manifest, eco)
            progress.update(task, completed=True)

    # Render output
    if output_format == "json":
        out = json.dumps(report.to_dict(), indent=2)
        if output:
            Path(output).write_text(out)
        else:
            console.print(out)
    elif output_format == "sarif":
        sarif = _generate_sarif(report)
        out = json.dumps(sarif, indent=2)
        if output:
            Path(output).write_text(out)
        else:
            console.print(out)
    elif output_format == "summary":
        _print_summary(report)
    else:
        _print_table(report)
        _print_summary(report)

    # Determine exit code
    if fail_on == "never":
        return
    
    has_blocks = report.blocked_count > 0
    has_warns = report.warned_count > 0
    
    if fail_on == "block" and has_blocks:
        sys.exit(1)
    elif (fail_on == "warn" or strict) and (has_blocks or has_warns):
        sys.exit(1)


@cli.command("check")
@click.argument("package")
@click.option("--ecosystem", "-e", required=True,
              type=click.Choice(["pypi", "npm", "cargo", "go", "maven"]),
              help="Package ecosystem")
@click.option("--format", "-f", "output_format", default="table",
              type=click.Choice(["table", "json"]),
              help="Output format")
@click.option("--policy-server", default=None,
              envvar="GUARDRAIL_POLICY_SERVER",
              help="Policy server URL")
@click.pass_context
def check_cmd(ctx, package, ecosystem, output_format, policy_server):
    """Check a single package name against the validation engine."""
    asyncio.run(_check_async(ctx, package, ecosystem, output_format, policy_server))


async def _check_async(ctx, package, ecosystem, output_format, policy_server):
    from core.validator import Validator
    from core.cache import Cache
    from core.models import Ecosystem, RiskLevel
    from core.policy import PolicyClient

    eco = Ecosystem(ecosystem)
    cache = Cache()
    policy_client = PolicyClient(policy_server) if policy_server else None

    async with Validator(cache=cache, policy_client=policy_client) as validator:
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[progress.description]Checking {package} ({ecosystem})..."),
            TimeElapsedColumn(),
            console=err_console,
            transient=True,
        ) as progress:
            progress.add_task("", total=None)
            result = await validator.validate(package, eco)

    if output_format == "json":
        console.print(json.dumps(result.to_dict(), indent=2))
    else:
        _print_single_result(result)

    if result.should_block:
        sys.exit(1)


@cli.command("install-shim")
@click.argument("package_manager", type=click.Choice(["pip", "npm"]))
@click.option("--uninstall", is_flag=True, help="Remove the shim")
@click.pass_context
def install_shim_cmd(ctx, package_manager, uninstall):
    """Install (or remove) a package manager shim.
    
    The shim intercepts install commands and validates dependencies before
    allowing installation to proceed.
    """
    _install_shim(package_manager, uninstall)


def _install_shim(package_manager: str, uninstall: bool):
    """Install shim script to PATH."""
    import shutil
    import stat

    shim_dir = Path.home() / ".guardrail" / "shims"
    shim_dir.mkdir(parents=True, exist_ok=True)

    if package_manager == "pip":
        shim_name = "pip"
        shim_content = _pip_shim_content()
    elif package_manager == "npm":
        shim_name = "npm"
        shim_content = _npm_shim_content()
    else:
        err_console.print(f"[red]Unknown package manager: {package_manager}[/red]")
        sys.exit(1)

    shim_path = shim_dir / shim_name

    if uninstall:
        if shim_path.exists():
            shim_path.unlink()
            console.print(f"[green]✓ Removed {package_manager} shim[/green]")
        else:
            console.print(f"[yellow]No shim found for {package_manager}[/yellow]")
        return

    shim_path.write_text(shim_content)
    shim_path.chmod(shim_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    console.print(Panel(
        f"[green]✓ Installed {package_manager} shim to {shim_path}[/green]\n\n"
        f"Add this directory to your PATH to activate:\n"
        f"  [bold]export PATH=\"{shim_dir}:$PATH\"[/bold]\n\n"
        f"Or add to your shell profile (~/.bashrc, ~/.zshrc).",
        title=f"GuardRail {package_manager.upper()} Shim Installed",
        border_style="green",
    ))


def _pip_shim_content() -> str:
    guardrail_path = sys.executable.replace("python", "guardrail")
    return f"""#!/usr/bin/env python3
# GuardRail pip shim — intercepts pip install to validate dependencies
import sys
import subprocess
import os

REAL_PIP = subprocess.check_output(
    ["python3", "-m", "pip", "--version"], stderr=subprocess.DEVNULL
)

def main():
    args = sys.argv[1:]
    
    # Only intercept install commands
    if len(args) < 1 or args[0] != "install":
        os.execv(sys.executable, [sys.executable, "-m", "pip"] + args)
        return
    
    # Extract package names from args
    packages = []
    skip_next = False
    for i, arg in enumerate(args[1:], 1):
        if skip_next:
            skip_next = False
            continue
        if arg.startswith("-"):
            if arg in ("-r", "--requirement", "-c", "--constraint", "-e", "--editable",
                       "--index-url", "--extra-index-url", "--trusted-host",
                       "--target", "-t", "--upgrade-strategy", "--prefix"):
                skip_next = True
            continue
        if os.path.exists(arg):
            continue  # Skip local paths
        # Strip version specifiers
        import re
        match = re.match(r'^([A-Za-z0-9][A-Za-z0-9._\\-]*)', arg)
        if match:
            packages.append(match.group(1))
    
    if packages:
        print(f"\\n[GuardRail] Validating {{len(packages)}} package(s) before install...")
        
        import importlib.util
        # Run guardrail check
        check_failed = False
        for pkg in packages:
            result = subprocess.run(
                [sys.executable, "-m", "guardrail_shim", "check", pkg, "--ecosystem", "pypi"],
                capture_output=True,
                text=True,
            )
            # Fallback to direct invocation
            if result.returncode != 0 and result.stderr:
                print(f"[GuardRail] WARNING: {{pkg}} — risk detected!", file=sys.stderr)
                print(result.stderr, file=sys.stderr)
                # Block on critical risk
                if "CRITICAL" in result.stderr or "BLOCK" in result.stderr:
                    check_failed = True
        
        if check_failed:
            print("[GuardRail] ❌ Installation blocked due to high-risk packages.", file=sys.stderr)
            print("[GuardRail] Run 'guardrail check <package> --ecosystem pypi' for details.", file=sys.stderr)
            sys.exit(1)
    
    # Proceed with real pip
    os.execv(sys.executable, [sys.executable, "-m", "pip"] + args)

if __name__ == "__main__":
    main()
"""


def _npm_shim_content() -> str:
    return """#!/usr/bin/env node
// GuardRail npm shim — intercepts npm install to validate dependencies
const { execFileSync, spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const args = process.argv.slice(2);
const command = args[0];

const INSTALL_CMDS = new Set(['install', 'i', 'add', 'ci']);

if (!INSTALL_CMDS.has(command)) {
  // Pass through to real npm
  const realNpm = spawnSync('npm', args, { stdio: 'inherit', shell: false });
  process.exit(realNpm.status || 0);
}

// Extract package names from install args
const packages = [];
for (let i = 1; i < args.length; i++) {
  const arg = args[i];
  if (arg.startsWith('-') || arg.startsWith('.') || arg.startsWith('/')) continue;
  // Strip version (@1.0.0)
  const name = arg.replace(/@[^@].*$/, '').replace(/@[0-9].*$/, '');
  if (name && !name.startsWith('@') || name.match(/^@[^/]+\\/[^/]+/)) {
    packages.push(name);
  }
}

if (packages.length > 0) {
  console.error(`[GuardRail] Validating ${packages.length} package(s)...`);
  let blocked = false;
  
  for (const pkg of packages) {
    try {
      const result = spawnSync('guardrail', ['check', pkg, '--ecosystem', 'npm', '--format', 'json'], {
        encoding: 'utf8',
        timeout: 30000,
      });
      
      if (result.stdout) {
        const data = JSON.parse(result.stdout);
        if (data.risk_level === 'CRITICAL') {
          console.error(`[GuardRail] ❌ BLOCKED: ${pkg} — ${data.risk_level} risk (score: ${data.risk_score})`);
          if (data.remediation) console.error(`[GuardRail]    ${data.remediation}`);
          blocked = true;
        } else if (data.risk_level === 'HIGH' || data.risk_level === 'MEDIUM') {
          console.error(`[GuardRail] ⚠️  WARNING: ${pkg} — ${data.risk_level} risk (score: ${data.risk_score})`);
          if (data.remediation) console.error(`[GuardRail]    ${data.remediation}`);
        } else {
          console.error(`[GuardRail] ✓ ${pkg} — OK`);
        }
      }
    } catch (e) {
      console.error(`[GuardRail] Warning: Could not validate ${pkg}: ${e.message}`);
    }
  }
  
  if (blocked) {
    console.error('[GuardRail] Installation blocked. Review warnings above.');
    process.exit(1);
  }
}

// Pass through to real npm
const realNpm = spawnSync('npm', args, { stdio: 'inherit' });
process.exit(realNpm.status || 0);
"""


# ─────────────────────────── Output formatters ───────────────────────────

RISK_COLORS = {
    "LOW": "green",
    "MEDIUM": "yellow",
    "HIGH": "orange3",
    "CRITICAL": "red",
    "UNKNOWN": "grey50",
}

RISK_ICONS = {
    "LOW": "✓",
    "MEDIUM": "⚠",
    "HIGH": "⚠",
    "CRITICAL": "✗",
    "UNKNOWN": "?",
}


def _print_table(report):
    """Print a rich table of validation results."""
    from core.models import RiskLevel
    
    table = Table(
        title=f"GuardRail Scan: {report.manifest_path}",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Package", style="bold", min_width=25)
    table.add_column("Ecosystem", min_width=8)
    table.add_column("Risk", min_width=10, justify="center")
    table.add_column("Score", min_width=7, justify="right")
    table.add_column("Exists", min_width=7, justify="center")
    table.add_column("Flags / Details", min_width=40)

    for result in report.results:
        risk = result.risk_level.value
        color = RISK_COLORS.get(risk, "white")
        icon = RISK_ICONS.get(risk, "?")

        flags_text = ", ".join(result.flags[:3]) if result.flags else ""
        if len(result.flags) > 3:
            flags_text += f" (+{len(result.flags)-3})"
        
        if result.remediation and result.risk_level.value in ("HIGH", "CRITICAL"):
            # Truncate remediation for table
            rem = result.remediation[:80] + "..." if len(result.remediation) > 80 else result.remediation
            flags_text = rem

        table.add_row(
            result.package_name,
            result.ecosystem,
            f"[{color}]{icon} {risk}[/{color}]",
            f"[{color}]{result.risk_score:.2f}[/{color}]",
            "[green]✓[/green]" if result.exists_on_registry else "[red]✗[/red]",
            flags_text,
        )

    console.print(table)


def _print_summary(report):
    """Print scan summary panel."""
    total = report.total_packages
    blocked = report.blocked_count
    warned = report.warned_count
    clean = report.clean_count
    not_found = report.not_found_count

    if blocked > 0:
        border = "red"
        status = f"[red]❌ BLOCKED — {blocked} critical package(s) detected[/red]"
    elif warned > 0:
        border = "yellow"
        status = f"[yellow]⚠  {warned} warning(s) require review[/yellow]"
    else:
        border = "green"
        status = "[green]✓ All packages passed validation[/green]"

    content = (
        f"{status}\n\n"
        f"  Total packages:  {total}\n"
        f"  [green]Clean:[/green]          {clean}\n"
        f"  [yellow]Warnings:[/yellow]       {warned}\n"
        f"  [red]Blocked:[/red]         {blocked}\n"
        f"  [orange3]Not found:[/orange3]      {not_found}\n\n"
        f"  Scan time: {report.scan_duration_ms:.0f}ms"
    )
    if report.policy_server_used:
        content += "  [dim](policy server active)[/dim]"

    console.print(Panel(content, title="GuardRail Scan Summary", border_style=border))


def _print_single_result(result):
    """Print a single package validation result."""
    risk = result.risk_level.value
    color = RISK_COLORS.get(risk, "white")
    icon = RISK_ICONS.get(risk, "?")

    lines = [
        f"[bold]Package:[/bold]    {result.package_name}",
        f"[bold]Ecosystem:[/bold]  {result.ecosystem}",
        f"[bold]Risk Level:[/bold] [{color}]{icon} {risk}[/{color}]",
        f"[bold]Risk Score:[/bold] [{color}]{result.risk_score:.3f}[/{color}]",
        f"[bold]Exists:[/bold]     {'[green]Yes[/green]' if result.exists_on_registry else '[red]No[/red]'}",
    ]

    if result.flags:
        lines.append(f"[bold]Flags:[/bold]      {', '.join(result.flags[:5])}")

    if result.heuristic_result and result.heuristic_result.similar_packages:
        lines.append(
            f"[bold]Similar to:[/bold] {', '.join(result.heuristic_result.similar_packages[:3])}"
        )

    if result.reputation_result and result.reputation_result.download_count is not None:
        lines.append(
            f"[bold]Downloads:[/bold]  {result.reputation_result.download_count:,} (last month)"
        )

    if result.remediation:
        lines.append("")
        lines.append(f"[bold yellow]⚠ Remediation:[/bold yellow]")
        lines.append(f"  {result.remediation}")

    border = color if color != "white" else "cyan"
    console.print(Panel("\n".join(lines), title=f"GuardRail: {result.package_name}", border_style=border))


def _generate_sarif(report) -> dict:
    """Generate SARIF 2.1.0 report."""
    rules = [
        {
            "id": "GR001",
            "name": "PackageNotFound",
            "shortDescription": {"text": "Package not found on registry"},
            "fullDescription": {"text": "The package does not exist on the specified registry and may be AI-hallucinated."},
            "defaultConfiguration": {"level": "error"},
            "helpUri": "https://github.com/guardrail-dev/guardrail/wiki/GR001",
        },
        {
            "id": "GR002",
            "name": "TyposquatSuspect",
            "shortDescription": {"text": "Potential typosquat or slopsquat detected"},
            "fullDescription": {"text": "Package name is suspiciously similar to a known legitimate package."},
            "defaultConfiguration": {"level": "warning"},
            "helpUri": "https://github.com/guardrail-dev/guardrail/wiki/GR002",
        },
        {
            "id": "GR003",
            "name": "LowReputation",
            "shortDescription": {"text": "Package has low reputation signals"},
            "fullDescription": {"text": "Package has few downloads, recent publish date, or missing maintainer info."},
            "defaultConfiguration": {"level": "note"},
            "helpUri": "https://github.com/guardrail-dev/guardrail/wiki/GR003",
        },
    ]

    results = []
    for r in report.results:
        if r.risk_level.value == "LOW":
            continue
        
        # Map risk level to SARIF level
        level_map = {"MEDIUM": "note", "HIGH": "warning", "CRITICAL": "error"}
        level = level_map.get(r.risk_level.value, "note")
        
        # Pick rule
        if not r.exists_on_registry:
            rule_id = "GR001"
        elif r.heuristic_result and r.heuristic_result.edit_distance and r.heuristic_result.edit_distance <= 2:
            rule_id = "GR002"
        else:
            rule_id = "GR003"

        message = r.remediation or f"Package '{r.package_name}' has {r.risk_level.value} risk (score: {r.risk_score:.3f})"
        
        results.append({
            "ruleId": rule_id,
            "level": level,
            "message": {"text": message},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": report.manifest_path,
                            "uriBaseId": "%SRCROOT%",
                        },
                        "region": {"startLine": 1},
                    },
                    "logicalLocations": [
                        {
                            "name": r.package_name,
                            "kind": "package",
                        }
                    ],
                }
            ],
            "properties": {
                "risk_score": r.risk_score,
                "ecosystem": r.ecosystem,
                "exists_on_registry": r.exists_on_registry,
                "flags": r.flags,
            },
        })

    return {
        "version": "2.1.0",
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "GuardRail",
                        "version": "0.1.0",
                        "informationUri": "https://github.com/guardrail-dev/guardrail",
                        "rules": rules,
                    }
                },
                "results": results,
                "artifacts": [
                    {
                        "location": {"uri": report.manifest_path},
                        "description": {"text": f"{report.ecosystem} manifest"},
                    }
                ],
                "properties": {
                    "manifest": report.manifest_path,
                    "ecosystem": report.ecosystem,
                    "total_packages": report.total_packages,
                    "scan_duration_ms": report.scan_duration_ms,
                },
            }
        ],
    }


if __name__ == "__main__":
    cli()