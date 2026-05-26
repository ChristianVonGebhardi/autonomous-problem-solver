package commands

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

var installHookCmd = &cobra.Command{
	Use:   "install-hook",
	Short: "Install LicenseGuard as a git pre-commit hook",
	Long: `Install LicenseGuard as a git pre-commit hook in the current repository.
The hook will automatically scan staged files before each commit.`,
	RunE: runInstallHook,
}

var removeHookCmd = &cobra.Command{
	Use:   "remove-hook",
	Short: "Remove the LicenseGuard git pre-commit hook",
	RunE:  runRemoveHook,
}

func init() {
	installHookCmd.Flags().Bool("force", false, "Overwrite existing pre-commit hook")
	rootCmd.AddCommand(removeHookCmd)
}

func runInstallHook(cmd *cobra.Command, args []string) error {
	// Find .git directory
	gitDir, err := findGitDir()
	if err != nil {
		return fmt.Errorf("not a git repository: %w", err)
	}

	hooksDir := filepath.Join(gitDir, "hooks")
	if err := os.MkdirAll(hooksDir, 0755); err != nil {
		return fmt.Errorf("failed to create hooks directory: %w", err)
	}

	hookPath := filepath.Join(hooksDir, "pre-commit")

	// Check if hook already exists
	force, _ := cmd.Flags().GetBool("force")
	if _, err := os.Stat(hookPath); err == nil && !force {
		return fmt.Errorf("pre-commit hook already exists. Use --force to overwrite")
	}

	apiURL := viper.GetString("api_url")
	hookContent := generateHookScript(apiURL)

	if err := os.WriteFile(hookPath, []byte(hookContent), 0755); err != nil {
		return fmt.Errorf("failed to write hook: %w", err)
	}

	color.Green("✅ LicenseGuard pre-commit hook installed at: %s", hookPath)
	fmt.Printf("\nThe hook will scan staged files before each commit.\n")
	fmt.Printf("API URL: %s\n", apiURL)
	fmt.Printf("\nTo configure, edit ~/.licenseguard.yaml or set LICENSEGUARD_API_URL env var.\n")

	return nil
}

func runRemoveHook(cmd *cobra.Command, args []string) error {
	gitDir, err := findGitDir()
	if err != nil {
		return fmt.Errorf("not a git repository: %w", err)
	}

	hookPath := filepath.Join(gitDir, "hooks", "pre-commit")

	// Read existing hook
	content, err := os.ReadFile(hookPath)
	if err != nil {
		return fmt.Errorf("no pre-commit hook found")
	}

	// Check if it's our hook
	if !strings.Contains(string(content), "LicenseGuard") {
		return fmt.Errorf("pre-commit hook was not installed by LicenseGuard")
	}

	if err := os.Remove(hookPath); err != nil {
		return fmt.Errorf("failed to remove hook: %w", err)
	}

	color.Green("✅ LicenseGuard pre-commit hook removed")
	return nil
}

func findGitDir() (string, error) {
	dir, err := os.Getwd()
	if err != nil {
		return "", err
	}

	for {
		gitPath := filepath.Join(dir, ".git")
		if info, err := os.Stat(gitPath); err == nil && info.IsDir() {
			return gitPath, nil
		}

		parent := filepath.Dir(dir)
		if parent == dir {
			return "", fmt.Errorf(".git directory not found")
		}
		dir = parent
	}
}

func generateHookScript(apiURL string) string {
	// Get the path to the current executable
	execPath, err := os.Executable()
	if err != nil {
		execPath = "licenseguard"
	}

	return fmt.Sprintf(`#!/bin/sh
# LicenseGuard Pre-commit Hook
# Automatically installed by LicenseGuard CLI
# Remove with: licenseguard remove-hook

LICENSEGUARD_BIN="%s"
LICENSEGUARD_API_URL="%s"

echo "🔍 LicenseGuard: Scanning staged files for license contamination..."

# Run scan on staged files
if ! "$LICENSEGUARD_BIN" scan --staged --api-url "$LICENSEGUARD_API_URL" --fail-on high; then
    echo ""
    echo "❌ LicenseGuard: High-risk license contamination detected in staged files."
    echo "   Run 'licenseguard scan --staged' for details."
    echo "   To bypass (not recommended): git commit --no-verify"
    echo ""
    exit 1
fi

echo "✅ LicenseGuard: No high-risk license contamination detected."
exit 0
`, execPath, apiURL)
}