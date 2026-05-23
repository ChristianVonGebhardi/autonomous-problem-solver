package main

import (
	"context"
	"fmt"
	"os"
	"text/tabwriter"
	"time"

	"github.com/cloudcircuitbreaker/mvp/internal/models"
	"github.com/cloudcircuitbreaker/mvp/internal/policy"
	"github.com/cloudcircuitbreaker/mvp/internal/simulator"
	"github.com/spf13/cobra"
)

var rootCmd = &cobra.Command{
	Use:   "ccb",
	Short: "Cloud Circuit Breaker — Real-time spending guardrails for dev teams",
	Long: `Cloud Circuit Breaker (CCB) monitors cloud resource spending in real time
and automatically triggers circuit breakers when spending policies are violated.

Prevents catastrophic bills from misconfigured loops and runaway resources.`,
}

var statusCmd = &cobra.Command{
	Use:   "status",
	Short: "Show current spending status and active circuit breakers",
	RunE:  runStatus,
}

var policyCmd = &cobra.Command{
	Use:   "policy",
	Short: "Policy management commands",
}

var policyListCmd = &cobra.Command{
	Use:   "list",
	Short: "List all policies",
	RunE:  runPolicyList,
}

var policyValidateCmd = &cobra.Command{
	Use:   "validate [file]",
	Short: "Validate a policy YAML file",
	Args:  cobra.ExactArgs(1),
	RunE:  runPolicyValidate,
}

var estimateCmd = &cobra.Command{
	Use:   "estimate",
	Short: "Estimate cost for resource types before provisioning",
	RunE:  runEstimate,
}

var demoCmd = &cobra.Command{
	Use:   "demo",
	Short: "Run an interactive demo showing circuit breaker triggering",
	RunE:  runDemo,
}

var (
	policyFile  string
	instanceType string
	hours        int
	teamFlag     string
)

func init() {
	rootCmd.PersistentFlags().StringVarP(&policyFile, "policy-file", "f", "configs/policies.yaml", "Path to policy YAML file")

	estimateCmd.Flags().StringVarP(&instanceType, "type", "t", "t3.medium", "EC2 instance type")
	estimateCmd.Flags().IntVarP(&hours, "hours", "n", 24, "Number of hours to estimate")
	estimateCmd.Flags().StringVarP(&teamFlag, "team", "", "my-team", "Team name for budget check")

	policyCmd.AddCommand(policyListCmd)
	policyCmd.AddCommand(policyValidateCmd)

	rootCmd.AddCommand(statusCmd)
	rootCmd.AddCommand(policyCmd)
	rootCmd.AddCommand(estimateCmd)
	rootCmd.AddCommand(demoCmd)
}

func main() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func runStatus(cmd *cobra.Command, args []string) error {
	ctx := context.Background()
	store := simulator.NewSpendingStore()
	sim := simulator.NewSimulator(store)
	sim.SeedHistoricalData()

	sim.PrintStatus(ctx)

	// Show spending by team
	fmt.Println("\n📊 Detailed Spending Report")
	fmt.Println(separator(54))

	w := tabwriter.NewWriter(os.Stdout, 0, 0, 2, ' ', 0)
	fmt.Fprintln(w, "TEAM\tPROJECT\t1H SPEND\t24H SPEND\tSTATUS")
	fmt.Fprintln(w, "----\t-------\t--------\t---------\t------")

	since1h := time.Now().Add(-time.Hour)
	since24h := time.Now().Add(-24 * time.Hour)

	type teamProject struct {
		team    string
		project string
	}

	seen := map[teamProject]bool{}
	for _, r := range sim.GetResources() {
		tp := teamProject{r.Resource.Team, r.Resource.Project}
		if seen[tp] {
			continue
		}
		seen[tp] = true

		spend1h, _ := store.GetProjectSpending(ctx, r.Resource.Team, r.Resource.Project, since1h)
		spend24h, _ := store.GetProjectSpending(ctx, r.Resource.Team, r.Resource.Project, since24h)

		status := "✅ OK"
		if spend1h > 5.0 {
			status = "⚠️  HIGH"
		}
		if spend24h > 50.0 {
			status = "🚨 BREACH"
		}

		fmt.Fprintf(w, "%s\t%s\t$%.4f\t$%.2f\t%s\n",
			r.Resource.Team, r.Resource.Project,
			spend1h, spend24h, status)
	}
	w.Flush()

	return nil
}

func runPolicyList(cmd *cobra.Command, args []string) error {
	policies, err := policy.LoadFromFile(policyFile)
	if err != nil {
		// Show default policies
		policies = defaultDemoPolicies()
		fmt.Printf("Note: Could not load %s, showing built-in demo policies\n\n", policyFile)
	}

	if len(policies) == 0 {
		fmt.Println("No policies found.")
		return nil
	}

	w := tabwriter.NewWriter(os.Stdout, 0, 0, 2, ' ', 0)
	fmt.Fprintln(w, "ID\tNAME\tTEAM\tTHRESHOLD\tWINDOW\tSTATUS")
	fmt.Fprintln(w, "--\t----\t----\t---------\t------\t------")

	for _, p := range policies {
		status := "DISABLED"
		if p.Enabled {
			status = "ACTIVE"
		}
		fmt.Fprintf(w, "%s\t%s\t%s\t$%.2f\t%s\t%s\n",
			p.ID, p.Name, p.Team, p.ThresholdAmount, p.TimeWindow, status)
	}
	w.Flush()

	return nil
}

func runPolicyValidate(cmd *cobra.Command, args []string) error {
	filePath := args[0]
	policies, err := policy.LoadFromFile(filePath)
	if err != nil {
		return fmt.Errorf("load file: %w", err)
	}

	fmt.Printf("Validating %d policies from %s\n\n", len(policies), filePath)

	allValid := true
	for _, p := range policies {
		errs := policy.Validate(p)
		if len(errs) == 0 {
			fmt.Printf("  ✅ %s (%s)\n", p.ID, p.Name)
		} else {
			allValid = false
			fmt.Printf("  ❌ %s (%s):\n", p.ID, p.Name)
			for _, e := range errs {
				fmt.Printf("       - %s\n", e)
			}
		}
	}

	if allValid {
		fmt.Printf("\n✅ All %d policies are valid\n", len(policies))
	} else {
		fmt.Printf("\n❌ Some policies have validation errors\n")
		return fmt.Errorf("validation failed")
	}

	return nil
}

func runEstimate(cmd *cobra.Command, args []string) error {
	// Simplified pricing map
	priceMap := map[string]float64{
		"t2.micro":    0.0116,
		"t2.small":    0.023,
		"t2.medium":   0.0464,
		"t2.large":    0.0928,
		"t3.micro":    0.0104,
		"t3.small":    0.0208,
		"t3.medium":   0.0416,
		"t3.large":    0.0832,
		"t3.xlarge":   0.1664,
		"m5.large":    0.096,
		"m5.xlarge":   0.192,
		"m5.2xlarge":  0.384,
		"m5.4xlarge":  0.768,
		"c5.large":    0.085,
		"c5.xlarge":   0.17,
		"c5.2xlarge":  0.34,
		"r5.large":    0.126,
		"r5.xlarge":   0.252,
		"r5.2xlarge":  0.504,
		"p3.2xlarge":  3.06,
		"p3.8xlarge":  12.24,
		"p3.16xlarge": 24.48,
	}

	hourlyCost, ok := priceMap[instanceType]
	if !ok {
		return fmt.Errorf("unknown instance type: %s (try t3.medium, m5.xlarge, etc.)", instanceType)
	}

	totalCost := hourlyCost * float64(hours)
	dailyCost := hourlyCost * 24
	weeklyCost := dailyCost * 7
	monthlyCost := dailyCost * 30

	fmt.Printf("\n💰 Cost Estimate: EC2 %s\n", instanceType)
	fmt.Println(separator(40))
	fmt.Printf("  Hourly rate:    $%.4f/hr\n", hourlyCost)
	fmt.Printf("  %d-hour total:   $%.2f\n", hours, totalCost)
	fmt.Printf("  Daily:          $%.2f/day\n", dailyCost)
	fmt.Printf("  Weekly:         $%.2f/week\n", weeklyCost)
	fmt.Printf("  Monthly:        $%.2f/month\n", monthlyCost)
	fmt.Println()

	// Check against demo policies
	policies := defaultDemoPolicies()
	fmt.Printf("📋 Policy Check for team '%s':\n", teamFlag)
	for _, p := range policies {
		if p.Team != teamFlag && p.Team != "*" {
			continue
		}

		var checkValue float64
		var checkDesc string

		switch p.TimeWindow {
		case "1h":
			checkValue = hourlyCost
			checkDesc = "hourly rate"
		case "24h":
			checkValue = dailyCost
			checkDesc = "daily cost"
		case "7d":
			checkValue = weeklyCost
			checkDesc = "weekly cost"
		case "30d":
			checkValue = monthlyCost
			checkDesc = "monthly cost"
		default:
			continue
		}

		if checkValue > p.ThresholdAmount {
			fmt.Printf("  ⚠️  WOULD BREACH: %s — %s ($%.2f > $%.2f threshold)\n",
				p.Name, checkDesc, checkValue, p.ThresholdAmount)
		} else {
			fmt.Printf("  ✅ OK: %s — %s ($%.2f <= $%.2f)\n",
				p.Name, checkDesc, checkValue, p.ThresholdAmount)
		}
	}
	fmt.Println()

	return nil
}

func runDemo(cmd *cobra.Command, args []string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()

	fmt.Println("🚀 Starting Cloud Circuit Breaker Demo")
	fmt.Println("   Simulating runaway EC2 spending for team 'data'")
	fmt.Println("   Circuit breaker threshold: $10/hr or $100/day")
	fmt.Println(separator(54))
	fmt.Println()

	// Setup
	store := simulator.NewSpendingStore()
	sim := simulator.NewSimulator(store)
	sim.SeedHistoricalData()
	sim.Start(ctx)

	breachCount := 0
	policies := defaultDemoPolicies()

	// Simple inline engine for demo
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	since24h := time.Now().Add(-24 * time.Hour)

	for {
		select {
		case <-ctx.Done():
			fmt.Printf("\n✅ Demo complete. %d breach events fired.\n", breachCount)
			return nil
		case <-ticker.C:
			since24h = time.Now().Add(-24 * time.Hour)
			since1h := time.Now().Add(-time.Hour)

			for _, p := range policies {
				window, _ := time.ParseDuration("1h")
				if p.TimeWindow == "24h" {
					window = 24 * time.Hour
				}

				since := time.Now().Add(-window)
				teamSpend, _ := store.GetTeamSpending(ctx, p.Team, since)
				hourlyRate := teamSpend / window.Hours()

				fmt.Printf("[%s] team=%-10s spend=%-10s hourly_rate=%-10s threshold=$%.2f — ",
					time.Now().Format("15:04:05"),
					p.Team,
					fmt.Sprintf("$%.4f", teamSpend),
					fmt.Sprintf("$%.4f/hr", hourlyRate),
					p.ThresholdAmount,
				)

				// Evaluate
				breached := false
				if p.CELExpression == "team_spend > threshold" {
					breached = teamSpend > p.ThresholdAmount
				} else if p.CELExpression == "hourly_rate > 10.0" {
					breached = hourlyRate > 10.0
				}

				if breached {
					breachCount++
					fmt.Printf("🚨 BREACH! Actions: %v\n", actionTypes(p.Actions))
				} else {
					fmt.Println("✅ OK")
				}
			}

			// Print overall summary
			_ = since24h
			fmt.Println()
		}
	}
}

func separator(n int) string {
	s := ""
	for i := 0; i < n; i++ {
		s += "─"
	}
	return s
}

func actionTypes(actions []models.PolicyAction) []string {
	types := make([]string, len(actions))
	for i, a := range actions {
		types[i] = a.Type
	}
	return types
}

func defaultDemoPolicies() []models.Policy {
	return []models.Policy{
		{
			ID:              "platform-daily-limit",
			Name:            "Platform Team Daily Limit",
			Team:            "platform",
			Project:         "*",
			Enabled:         true,
			CELExpression:   "team_spend > threshold",
			ThresholdAmount: 50.0,
			TimeWindow:      "24h",
			Actions: []models.PolicyAction{
				{Type: "notify", Severity: "warn"},
			},
		},
		{
			ID:              "data-hourly-limit",
			Name:            "Data Team Hourly Runaway Guard",
			Team:            "data",
			Project:         "*",
			Enabled:         true,
			CELExpression:   "hourly_rate > 10.0",
			ThresholdAmount: 10.0,
			TimeWindow:      "1h",
			Actions: []models.PolicyAction{
				{Type: "notify", Severity: "warn"},
				{Type: "halt", Severity: "critical"},
			},
		},
		{
			ID:              "data-daily-limit",
			Name:            "Data Team Daily Limit",
			Team:            "data",
			Project:         "ml-training",
			Enabled:         true,
			CELExpression:   "team_spend > threshold",
			ThresholdAmount: 100.0,
			TimeWindow:      "24h",
			Actions: []models.PolicyAction{
				{Type: "notify", Severity: "warn"},
				{Type: "halt", Severity: "critical"},
			},
		},
	}
}