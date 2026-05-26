package commands

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

var statusCmd = &cobra.Command{
	Use:   "status",
	Short: "Check LicenseGuard API status and corpus stats",
	RunE:  runStatus,
}

type HealthResponse struct {
	Status     string `json:"status"`
	Version    string `json:"version"`
	Database   string `json:"database"`
	Redis      string `json:"redis"`
	CorpusSize int    `json:"corpus_size"`
}

func runStatus(cmd *cobra.Command, args []string) error {
	apiURL := viper.GetString("api_url")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(apiURL + "/api/v1/health")
	if err != nil {
		color.Red("❌ Cannot connect to LicenseGuard API at %s", apiURL)
		color.Red("   Error: %v", err)
		fmt.Printf("\nTo start the API:\n  cd license-guard && docker compose up -d\n")
		return err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	var health HealthResponse
	if err := json.Unmarshal(body, &health); err != nil {
		return fmt.Errorf("failed to parse response: %w", err)
	}

	bold := color.New(color.Bold)
	fmt.Println()
	bold.Printf("LicenseGuard Status\n")
	fmt.Println(repeatStr("─", 40))
	fmt.Printf("API URL:      %s\n", apiURL)
	fmt.Printf("API Status:   %s\n", statusIcon(health.Status))
	fmt.Printf("Version:      %s\n", health.Version)
	fmt.Printf("Database:     %s\n", statusIcon(health.Database))
	fmt.Printf("Redis:        %s\n", statusIcon(health.Redis))
	fmt.Printf("Corpus Size:  %d snippets\n", health.CorpusSize)
	fmt.Println()

	return nil
}

func statusIcon(status string) string {
	if status == "ok" {
		return color.GreenString("✅ OK")
	}
	return color.RedString("❌ " + status)
}

func repeatStr(s string, n int) string {
	result := ""
	for i := 0; i < n; i++ {
		result += s
	}
	return result
}