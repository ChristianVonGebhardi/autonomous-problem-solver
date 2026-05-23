package simulator

import (
	"context"
	"fmt"
	"log"
	"math"
	"math/rand"
	"sync"
	"time"

	"github.com/cloudcircuitbreaker/mvp/internal/models"
)

// SimulatedResource represents a cloud resource in the simulation
type SimulatedResource struct {
	models.Resource
	HourlyCost  float64
	IsRunaway   bool // simulates misconfigured runaway spending
}

// SpendingStore is a thread-safe in-memory spending store
type SpendingStore struct {
	mu      sync.RWMutex
	metrics []models.CostMetric
}

// NewSpendingStore creates a new in-memory spending store
func NewSpendingStore() *SpendingStore {
	return &SpendingStore{}
}

// AddMetric adds a cost metric
func (s *SpendingStore) AddMetric(m models.CostMetric) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.metrics = append(s.metrics, m)
}

// AddMetrics adds multiple cost metrics
func (s *SpendingStore) AddMetrics(metrics []models.CostMetric) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.metrics = append(s.metrics, metrics...)
}

// GetTeamSpending returns total spending for a team since a time
func (s *SpendingStore) GetTeamSpending(_ context.Context, team string, since time.Time) (float64, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var total float64
	for _, m := range s.metrics {
		if m.Team == team && !m.Timestamp.Before(since) {
			total += m.Cost
		}
	}
	return total, nil
}

// GetProjectSpending returns total spending for a project since a time
func (s *SpendingStore) GetProjectSpending(_ context.Context, team, project string, since time.Time) (float64, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var total float64
	for _, m := range s.metrics {
		if m.Team == team && m.Project == project && !m.Timestamp.Before(since) {
			total += m.Cost
		}
	}
	return total, nil
}

// GetResourceSpending returns total spending for a resource since a time
func (s *SpendingStore) GetResourceSpending(_ context.Context, resourceID string, since time.Time) (float64, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var total float64
	for _, m := range s.metrics {
		if m.ResourceID == resourceID && !m.Timestamp.Before(since) {
			total += m.Cost
		}
	}
	return total, nil
}

// GetAllMetrics returns a snapshot of all metrics
func (s *SpendingStore) GetAllMetrics() []models.CostMetric {
	s.mu.RLock()
	defer s.mu.RUnlock()
	result := make([]models.CostMetric, len(s.metrics))
	copy(result, s.metrics)
	return result
}

// Simulator drives the demo scenario
type Simulator struct {
	store     *SpendingStore
	resources []SimulatedResource
	ticker    *time.Ticker
	stopCh    chan struct{}
	tickCount int
}

// NewSimulator creates a demo simulator with pre-built scenario
func NewSimulator(store *SpendingStore) *Simulator {
	now := time.Now()

	resources := []SimulatedResource{
		{
			Resource: models.Resource{
				ID:           "i-0abc123platform",
				Provider:     models.AWS,
				Type:         "t3.medium",
				Region:       "us-east-1",
				Team:         "platform",
				Project:      "api-gateway",
				State:        "running",
				CreatedAt:    now.Add(-48 * time.Hour),
				DiscoveredAt: now,
			},
			HourlyCost: 0.0416,
			IsRunaway:  false,
		},
		{
			Resource: models.Resource{
				ID:           "i-0def456platform",
				Provider:     models.AWS,
				Type:         "m5.xlarge",
				Region:       "us-east-1",
				Team:         "platform",
				Project:      "api-gateway",
				State:        "running",
				CreatedAt:    now.Add(-24 * time.Hour),
				DiscoveredAt: now,
			},
			HourlyCost: 0.192,
			IsRunaway:  false,
		},
		{
			Resource: models.Resource{
				ID:           "i-0ghi789data",
				Provider:     models.AWS,
				Type:         "r5.xlarge",
				Region:       "us-west-2",
				Team:         "data",
				Project:      "ml-training",
				State:        "running",
				CreatedAt:    now.Add(-2 * time.Hour),
				DiscoveredAt: now,
			},
			HourlyCost: 0.252,
			IsRunaway:  false,
		},
		{
			Resource: models.Resource{
				ID:           "i-0runaway999",
				Provider:     models.AWS,
				Type:         "m5.2xlarge",
				Region:       "us-east-1",
				Team:         "data",
				Project:      "ml-training",
				State:        "running",
				CreatedAt:    now.Add(-30 * time.Minute),
				DiscoveredAt: now,
			},
			HourlyCost: 0.384,
			IsRunaway:  true, // This will ramp up cost dramatically
		},
	}

	return &Simulator{
		store:     store,
		resources: resources,
		stopCh:    make(chan struct{}),
	}
}

// SeedHistoricalData adds past spending data to establish baselines
func (s *Simulator) SeedHistoricalData() {
	log.Println("Seeding historical spending data...")
	now := time.Now()

	for _, resource := range s.resources {
		// Add 24 hours of historical data at 1-minute intervals
		for i := 1440; i >= 1; i-- {
			ts := now.Add(-time.Duration(i) * time.Minute)
			cost := resource.HourlyCost / 60.0

			// Add some natural variance
			variance := 1.0 + (rand.Float64()-0.5)*0.1
			cost = cost * variance

			// Skip runaway resource in history (it just started)
			if resource.IsRunaway && i > 30 {
				continue
			}

			s.store.AddMetric(models.CostMetric{
				ResourceID:  resource.Resource.ID,
				Provider:    resource.Resource.Provider,
				Team:        resource.Resource.Team,
				Project:     resource.Resource.Project,
				Timestamp:   ts,
				Cost:        cost,
				Currency:    "USD",
				MetricType:  "per-minute",
				ServiceName: "Amazon EC2",
			})
		}
	}

	log.Printf("Seeded %d historical data points", len(s.store.GetAllMetrics()))
}

// Start begins emitting real-time cost metrics
func (s *Simulator) Start(ctx context.Context) {
	s.ticker = time.NewTicker(5 * time.Second)

	go func() {
		defer s.ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-s.stopCh:
				return
			case <-s.ticker.C:
				s.tick()
			}
		}
	}()

	log.Println("Simulator started — emitting metrics every 5 seconds")
}

// Stop halts the simulator
func (s *Simulator) Stop() {
	close(s.stopCh)
}

// tick emits one round of metrics
func (s *Simulator) tick() {
	s.tickCount++
	now := time.Now()

	for i := range s.resources {
		resource := &s.resources[i]
		if resource.Resource.State != "running" {
			continue
		}

		// Per 5-second cost = hourly / 720
		cost := resource.HourlyCost / 720.0

		if resource.IsRunaway {
			// Exponential cost ramp to simulate runaway loop
			multiplier := math.Pow(1.5, float64(s.tickCount)/10.0)
			cost = cost * multiplier

			if s.tickCount%12 == 0 { // every minute
				log.Printf("⚠️  RUNAWAY: resource %s cost this tick: $%.4f (multiplier: %.1fx)",
					resource.Resource.ID, cost, multiplier)
			}
		}

		s.store.AddMetric(models.CostMetric{
			ResourceID:  resource.Resource.ID,
			Provider:    resource.Resource.Provider,
			Team:        resource.Resource.Team,
			Project:     resource.Resource.Project,
			Timestamp:   now,
			Cost:        cost,
			Currency:    "USD",
			MetricType:  "per-5s",
			ServiceName: "Amazon EC2",
		})
	}
}

// GetResources returns the current simulated resources
func (s *Simulator) GetResources() []SimulatedResource {
	return s.resources
}

// GetSpendingSummary returns a summary of current spending
func (s *Simulator) GetSpendingSummary(ctx context.Context) map[string]float64 {
	since := time.Now().Add(-24 * time.Hour)
	summary := make(map[string]float64)

	teams := map[string]bool{}
	for _, r := range s.resources {
		teams[r.Resource.Team] = true
	}

	for team := range teams {
		spend, _ := s.store.GetTeamSpending(ctx, team, since)
		summary[team] = spend
	}

	return summary
}

// PrintStatus prints current spending status to stdout
func (s *Simulator) PrintStatus(ctx context.Context) {
	since24h := time.Now().Add(-24 * time.Hour)
	since1h := time.Now().Add(-time.Hour)

	fmt.Println("\n╔══════════════════════════════════════════════════════╗")
	fmt.Println("║        Cloud Spending Circuit Breaker - Status       ║")
	fmt.Println("╠══════════════════════════════════════════════════════╣")
	fmt.Printf("║  %-52s ║\n", fmt.Sprintf("Time: %s", time.Now().Format("15:04:05")))
	fmt.Println("╠══════════════════════════════════════════════════════╣")
	fmt.Println("║  RESOURCES                                           ║")
	fmt.Println("╠══════════════════════════════════════════════════════╣")

	for _, r := range s.resources {
		spend1h, _ := s.store.GetResourceSpending(ctx, r.Resource.ID, since1h)
		runawayFlag := ""
		if r.IsRunaway {
			runawayFlag = " 🔥RUNAWAY"
		}
		fmt.Printf("║  %-20s  %-10s  1h: $%-8.4f%s\n",
			truncate(r.Resource.ID, 20),
			r.Resource.Type,
			spend1h,
			runawayFlag,
		)
	}

	fmt.Println("╠══════════════════════════════════════════════════════╣")
	fmt.Println("║  TEAM SPENDING (24h)                                 ║")
	fmt.Println("╠══════════════════════════════════════════════════════╣")

	teams := map[string]bool{}
	for _, r := range s.resources {
		teams[r.Resource.Team] = true
	}

	for team := range teams {
		spend24h, _ := s.store.GetTeamSpending(ctx, team, since24h)
		bar := spendBar(spend24h, 50.0)
		fmt.Printf("║  %-12s  $%-8.2f  %s\n", team, spend24h, bar)
	}

	fmt.Println("╚══════════════════════════════════════════════════════╝")
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n-3] + "..."
}

func spendBar(amount, max float64) string {
	width := 20
	filled := int(amount / max * float64(width))
	if filled > width {
		filled = width
	}

	bar := "["
	for i := 0; i < width; i++ {
		if i < filled {
			bar += "█"
		} else {
			bar += "░"
		}
	}
	bar += "]"
	return bar
}