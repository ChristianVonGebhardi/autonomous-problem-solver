package config

import (
	"fmt"
	"os"
	"strconv"

	"github.com/joho/godotenv"
)

type Config struct {
	// GitHub
	GitHubWebhookSecret string
	GitHubToken         string

	// Slack
	SlackWebhookURL string

	// Database
	PostgresHost     string
	PostgresPort     int
	PostgresUser     string
	PostgresPassword string
	PostgresDB       string

	// Redis
	RedisHost string
	RedisPort int

	// Service Ports
	WebhookServicePort     int
	AnalysisServicePort    int
	RoutingServicePort     int
	CapacityServicePort    int
	NotificationServicePort int
	DashboardAPIPort       int
}

func Load() (*Config, error) {
	// Load .env file if it exists (ignore error if not found)
	_ = godotenv.Load()

	cfg := &Config{
		GitHubWebhookSecret: getEnv("GITHUB_WEBHOOK_SECRET", "dev_secret_key"),
		GitHubToken:         getEnv("GITHUB_TOKEN", ""),
		SlackWebhookURL:     getEnv("SLACK_WEBHOOK_URL", ""),

		PostgresHost:     getEnv("POSTGRES_HOST", "localhost"),
		PostgresPort:     getEnvInt("POSTGRES_PORT", 5432),
		PostgresUser:     getEnv("POSTGRES_USER", "reviewer"),
		PostgresPassword: getEnv("POSTGRES_PASSWORD", "reviewer_pass"),
		PostgresDB:       getEnv("POSTGRES_DB", "code_review_coordinator"),

		RedisHost: getEnv("REDIS_HOST", "localhost"),
		RedisPort: getEnvInt("REDIS_PORT", 6379),

		WebhookServicePort:      getEnvInt("WEBHOOK_SERVICE_PORT", 8080),
		AnalysisServicePort:     getEnvInt("ANALYSIS_SERVICE_PORT", 8081),
		RoutingServicePort:      getEnvInt("ROUTING_SERVICE_PORT", 8082),
		CapacityServicePort:     getEnvInt("CAPACITY_SERVICE_PORT", 8083),
		NotificationServicePort: getEnvInt("NOTIFICATION_SERVICE_PORT", 8084),
		DashboardAPIPort:        getEnvInt("DASHBOARD_API_PORT", 8085),
	}

	return cfg, nil
}

func (c *Config) PostgresConnectionString() string {
	return fmt.Sprintf("host=%s port=%d user=%s password=%s dbname=%s sslmode=disable",
		c.PostgresHost, c.PostgresPort, c.PostgresUser, c.PostgresPassword, c.PostgresDB)
}

func (c *Config) RedisAddress() string {
	return fmt.Sprintf("%s:%d", c.RedisHost, c.RedisPort)
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func getEnvInt(key string, defaultValue int) int {
	if value := os.Getenv(key); value != "" {
		if intVal, err := strconv.Atoi(value); err == nil {
			return intVal
		}
	}
	return defaultValue
}