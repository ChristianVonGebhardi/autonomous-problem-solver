package commands

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

type ScanRequest struct {
	Code     string                 `json:"code"`
	Language string                 `json:"language,omitempty"`
	Source   string                 `json:"source"`
	Filename string                 `json:"filename,omitempty"`
	Metadata map[string]interface{} `json:"metadata,omitempty"`
}

type MatchResult struct {
	MatchID          string  `json:"match_id"`
	MatchType        string  `json:"match_type"`
	SimilarityScore  float64 `json:"similarity_score"`
	LicenseSPDX      string  `json:"license_spdx"`
	LicenseRiskTier  string  `json:"license_risk_tier"`
	SourceRepo       string  `json:"source_repo"`
	MatchedSnippet   string  `json:"matched_snippet"`
}

type ScanResult struct {
	ScanID         string        `json:"scan_id"`
	Status         string        `json:"status"`
	RiskTier       string        `json:"risk_tier"`
	Matches        []MatchResult `json:"matches"`
	Recommendation string        `json:"recommendation"`
	Message        string        `json:"message"`
	CreatedAt      string        `json:"created_at"`
}

var scanCmd = &cobra.Command{
	Use:   "scan [file|directory]",
	Short: "Scan code for license contamination",
	Long: `Scan a file, directory, or stdin for open-source license contamination.
	
Examples:
  # Scan a file
  licenseguard scan myfile.py

  # Scan from git diff (AI-touched files)
  git diff HEAD | licenseguard scan --stdin

  # Scan a directory
  licenseguard scan ./src/

  # Scan staged changes
  licenseguard scan --staged`,
	RunE: runScan,
}

var (
	scanStdin    bool
	scanStaged   bool
	scanLanguage string
	scanOutput   string
	failOnRisk   string
)

func init() {
	scanCmd.Flags().BoolVar(&scanStdin, "stdin", false, "Read code from stdin")
	scanCmd.Flags().BoolVar(&scanStaged, "staged", false, "Scan git staged changes")
	scanCmd.Flags().StringVar(&scanLanguage, "language", "", "Programming language hint")
	scanCmd.Flags().StringVar(&scanOutput, "output", "text", "Output format: text, json")
	scanCmd.Flags().StringVar(&failOnRisk, "fail-on", "high", "Exit with error on risk tier: high, medium, low")
}

func runScan(cmd *cobra.Command, args []string) error {
	apiURL := viper.GetString("api_url")

	var snippets []struct {
		code     string
		filename string
		language string
	}

	if scanStdin {
		// Read from stdin
		data, err := io.ReadAll(os.Stdin)
		if err != nil {
			return fmt.Errorf("failed to read stdin: %w", err)
		}
		snippets = append(snippets, struct {
			code     string
			filename string
			language string
		}{string(data), "stdin", scanLanguage})

	} else if scanStaged {
		// Get staged changes
		staged, err := getStagedDiff()
		if err != nil {
			return fmt.Errorf("failed to get staged diff: %w", err)
		}
		for filename, code := range staged {
			lang := detectLanguage(filename)
			if scanLanguage != "" {
				lang = scanLanguage
			}
			snippets = append(snippets, struct {
				code     string
				filename string
				language string
			}{code, filename, lang})
		}

	} else if len(args) > 0 {
		// Scan files/directories
		for _, arg := range args {
			info, err := os.Stat(arg)
			if err != nil {
				return fmt.Errorf("cannot access %s: %w", arg, err)
			}

			if info.IsDir() {
				// Walk directory
				err = filepath.Walk(arg, func(path string, fi os.FileInfo, err error) error {
					if err != nil {
						return err
					}
					if fi.IsDir() {
						return nil
					}
					if !isCodeFile(path) {
						return nil
					}
					data, err := os.ReadFile(path)
					if err != nil {
						return err
					}
					lang := detectLanguage(path)
					snippets = append(snippets, struct {
						code     string
						filename string
						language string
					}{string(data), path, lang})
					return nil
				})
				if err != nil {
					return err
				}
			} else {
				data, err := os.ReadFile(arg)
				if err != nil {
					return fmt.Errorf("failed to read %s: %w", arg, err)
				}
				lang := detectLanguage(arg)
				if scanLanguage != "" {
					lang = scanLanguage
				}
				snippets = append(snippets, struct {
					code     string
					filename string
					language string
				}{string(data), arg, lang})
			}
		}
	} else {
		return fmt.Errorf("provide a file path, use --stdin, or --staged")
	}

	if len(snippets) == 0 {
		fmt.Println("No code files to scan.")
		return nil
	}

	// Scan each snippet
	worstTier := "clean"
	var allResults []ScanResult
	exitCode := 0

	for _, s := range snippets {
		if viper.GetBool("verbose") {
			fmt.Fprintf(os.Stderr, "Scanning: %s (%s)\n", s.filename, s.language)
		}

		result, err := scanCode(apiURL, s.code, s.language, s.filename)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error scanning %s: %v\n", s.filename, err)
			continue
		}
		allResults = append(allResults, *result)
		worstTier = higherRiskTier(worstTier, result.RiskTier)
	}

	// Output results
	if scanOutput == "json" {
		data, _ := json.MarshalIndent(allResults, "", "  ")
		fmt.Println(string(data))
	} else {
		printResults(allResults)
	}

	// Determine exit code
	if shouldFail(worstTier, failOnRisk) {
		exitCode = 1
	}

	if exitCode != 0 {
		return fmt.Errorf("license contamination detected (risk tier: %s)", worstTier)
	}
	return nil
}

func scanCode(apiURL, code, language, filename string) (*ScanResult, error) {
	reqBody := ScanRequest{
		Code:     code,
		Language: language,
		Source:   "pre_commit",
		Filename: filename,
	}

	data, err := json.Marshal(reqBody)
	if err != nil {
		return nil, err
	}

	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Post(
		apiURL+"/api/v1/scan/sync",
		"application/json",
		bytes.NewReader(data),
	)
	if err != nil {
		return nil, fmt.Errorf("API request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API error %d: %s", resp.StatusCode, string(body))
	}

	var result ScanResult
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

func printResults(results []ScanResult) {
	bold := color.New(color.Bold)
	
	for _, r := range results {
		fmt.Println()
		bold.Printf("=== Scan Result ===\n")
		fmt.Printf("Scan ID:    %s\n", r.ScanID)
		fmt.Printf("Status:     %s\n", r.Status)
		fmt.Printf("Risk Tier:  %s\n", colorRiskTier(r.RiskTier))
		fmt.Printf("Matches:    %d\n", len(r.Matches))

		if len(r.Matches) > 0 {
			fmt.Println("\nMatches found:")
			for _, m := range r.Matches {
				fmt.Printf("  • [%s] %.1f%% similar to %s (%s)\n",
					strings.ToUpper(m.MatchType),
					m.SimilarityScore*100,
					m.SourceRepo,
					m.LicenseSPDX,
				)
			}
		}

		if r.Recommendation != "" {
			fmt.Printf("\nRecommendation:\n  %s\n", r.Recommendation)
		}
	}

	fmt.Println()
}

func colorRiskTier(tier string) string {
	switch tier {
	case "high":
		return color.RedString("HIGH ⚠️")
	case "medium":
		return color.YellowString("MEDIUM ⚡")
	case "low":
		return color.CyanString("LOW ℹ️")
	case "clean":
		return color.GreenString("CLEAN ✅")
	default:
		return tier
	}
}

func higherRiskTier(a, b string) string {
	order := map[string]int{
		"high":    4,
		"medium":  3,
		"unknown": 2,
		"low":     1,
		"clean":   0,
	}
	if order[a] >= order[b] {
		return a
	}
	return b
}

func shouldFail(worstTier, failOn string) bool {
	order := map[string]int{
		"high":   4,
		"medium": 3,
		"low":    1,
		"never":  0,
	}
	return order[worstTier] >= order[failOn]
}

func getStagedDiff() (map[string]string, error) {
	// Get list of staged files
	out, err := exec.Command("git", "diff", "--cached", "--name-only").Output()
	if err != nil {
		return nil, fmt.Errorf("git diff failed: %w", err)
	}

	files := strings.Split(strings.TrimSpace(string(out)), "\n")
	result := make(map[string]string)

	for _, f := range files {
		f = strings.TrimSpace(f)
		if f == "" || !isCodeFile(f) {
			continue
		}

		// Get staged content
		content, err := exec.Command("git", "show", ":"+f).Output()
		if err != nil {
			continue
		}
		result[f] = string(content)
	}

	return result, nil
}

func detectLanguage(filename string) string {
	ext := strings.ToLower(filepath.Ext(filename))
	switch ext {
	case ".py":
		return "python"
	case ".js", ".mjs":
		return "javascript"
	case ".ts", ".tsx":
		return "typescript"
	case ".go":
		return "go"
	case ".java":
		return "java"
	case ".c", ".h":
		return "c"
	case ".cpp", ".cc", ".cxx", ".hpp":
		return "cpp"
	case ".rs":
		return "rust"
	case ".rb":
		return "ruby"
	case ".php":
		return "php"
	case ".cs":
		return "csharp"
	default:
		return ""
	}
}

func isCodeFile(path string) bool {
	codeExts := map[string]bool{
		".py": true, ".js": true, ".ts": true, ".tsx": true,
		".go": true, ".java": true, ".c": true, ".cpp": true,
		".h": true, ".hpp": true, ".rs": true, ".rb": true,
		".php": true, ".cs": true, ".mjs": true, ".cc": true,
	}
	ext := strings.ToLower(filepath.Ext(path))
	return codeExts[ext]
}