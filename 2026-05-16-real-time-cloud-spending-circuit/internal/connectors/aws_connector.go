package connectors

import (
	"context"
	"fmt"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/costexplorer"
	"github.com/aws/aws-sdk-go-v2/service/costexplorer/types"
	"github.com/aws/aws-sdk-go-v2/service/ec2"
	ec2types "github.com/aws/aws-sdk-go-v2/service/ec2/types"
	"github.com/cloudcircuitbreaker/mvp/internal/models"
)

type AWSConnector struct {
	cfg            aws.Config
	ec2Client      *ec2.Client
	costClient     *costexplorer.Client
	defaultTeam    string
	defaultProject string
}

func NewAWSConnector(ctx context.Context, region, defaultTeam, defaultProject string) (*AWSConnector, error) {
	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(region))
	if err != nil {
		return nil, fmt.Errorf("load AWS config: %w", err)
	}

	return &AWSConnector{
		cfg:            cfg,
		ec2Client:      ec2.NewFromConfig(cfg),
		costClient:     costexplorer.NewFromConfig(cfg),
		defaultTeam:    defaultTeam,
		defaultProject: defaultProject,
	}, nil
}

// DiscoverResources finds EC2 instances in the account
func (c *AWSConnector) DiscoverResources(ctx context.Context) ([]models.Resource, error) {
	input := &ec2.DescribeInstancesInput{}
	result, err := c.ec2Client.DescribeInstances(ctx, input)
	if err != nil {
		return nil, fmt.Errorf("describe instances: %w", err)
	}

	var resources []models.Resource
	now := time.Now()

	for _, reservation := range result.Reservations {
		for _, instance := range reservation.Instances {
			tags := make(map[string]string)
			team := c.defaultTeam
			project := c.defaultProject

			for _, tag := range instance.Tags {
				if tag.Key != nil && tag.Value != nil {
					tags[*tag.Key] = *tag.Value
					if *tag.Key == "Team" {
						team = *tag.Value
					}
					if *tag.Key == "Project" {
						project = *tag.Value
					}
				}
			}

			resource := models.Resource{
				ID:           *instance.InstanceId,
				Provider:     models.AWS,
				Type:         string(instance.InstanceType),
				Region:       *c.cfg.Region,
				Tags:         tags,
				Team:         team,
				Project:      project,
				State:        string(instance.State.Name),
				CreatedAt:    *instance.LaunchTime,
				DiscoveredAt: now,
			}

			resources = append(resources, resource)
		}
	}

	return resources, nil
}

// FetchCostData retrieves cost data from AWS Cost Explorer
func (c *AWSConnector) FetchCostData(ctx context.Context, start, end time.Time) ([]models.CostMetric, error) {
	startStr := start.Format("2006-01-02")
	endStr := end.Format("2006-01-02")

	input := &costexplorer.GetCostAndUsageInput{
		TimePeriod: &types.DateInterval{
			Start: aws.String(startStr),
			End:   aws.String(endStr),
		},
		Granularity: types.GranularityHourly,
		Metrics:     []string{"UnblendedCost"},
		GroupBy: []types.GroupDefinition{
			{
				Type: types.GroupDefinitionTypeDimension,
				Key:  aws.String("SERVICE"),
			},
		},
	}

	result, err := c.costClient.GetCostAndUsage(ctx, input)
	if err != nil {
		return nil, fmt.Errorf("get cost and usage: %w", err)
	}

	var metrics []models.CostMetric

	for _, resultByTime := range result.ResultsByTime {
		timestamp, _ := time.Parse("2006-01-02", *resultByTime.TimePeriod.Start)

		for _, group := range resultByTime.Groups {
			serviceName := ""
			if len(group.Keys) > 0 {
				serviceName = group.Keys[0]
			}

			cost := 0.0
			if group.Metrics != nil && group.Metrics["UnblendedCost"] != nil && group.Metrics["UnblendedCost"].Amount != nil {
				fmt.Sscanf(*group.Metrics["UnblendedCost"].Amount, "%f", &cost)
			}

			metric := models.CostMetric{
				ResourceID:  "aws-account", // Account-level cost
				Provider:    models.AWS,
				Team:        c.defaultTeam,
				Project:     c.defaultProject,
				Timestamp:   timestamp,
				Cost:        cost,
				Currency:    "USD",
				MetricType:  "hourly",
				ServiceName: serviceName,
			}

			metrics = append(metrics, metric)
		}
	}

	return metrics, nil
}

// GetInstanceHourlyCost estimates hourly cost for an instance type
func (c *AWSConnector) GetInstanceHourlyCost(instanceType string) float64 {
	// Simplified pricing - in production would use AWS Price List API
	priceMap := map[string]float64{
		"t2.micro":   0.0116,
		"t2.small":   0.023,
		"t2.medium":  0.0464,
		"t2.large":   0.0928,
		"t3.micro":   0.0104,
		"t3.small":   0.0208,
		"t3.medium":  0.0416,
		"t3.large":   0.0832,
		"m5.large":   0.096,
		"m5.xlarge":  0.192,
		"m5.2xlarge": 0.384,
		"c5.large":   0.085,
		"c5.xlarge":  0.17,
		"r5.large":   0.126,
		"r5.xlarge":  0.252,
	}

	if cost, ok := priceMap[instanceType]; ok {
		return cost
	}

	return 0.1 // Default fallback
}

// GenerateSyntheticMetrics creates cost metrics for running instances
func (c *AWSConnector) GenerateSyntheticMetrics(ctx context.Context, resources []models.Resource) []models.CostMetric {
	var metrics []models.CostMetric
	now := time.Now()

	for _, resource := range resources {
		if resource.State == "running" {
			hourlyCost := c.GetInstanceHourlyCost(resource.Type)

			metric := models.CostMetric{
				ResourceID:  resource.ID,
				Provider:    models.AWS,
				Team:        resource.Team,
				Project:     resource.Project,
				Timestamp:   now,
				Cost:        hourlyCost,
				Currency:    "USD",
				MetricType:  "hourly",
				ServiceName: "Amazon EC2",
			}

			metrics = append(metrics, metric)
		}
	}

	return metrics
}