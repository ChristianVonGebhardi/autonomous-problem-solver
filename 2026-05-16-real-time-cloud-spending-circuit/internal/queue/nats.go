package queue

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"github.com/cloudcircuitbreaker/mvp/internal/models"
	"github.com/nats-io/nats.go"
)

const (
	BreachSubject   = "circuitbreaker.breach"
	MetricsSubject  = "circuitbreaker.metrics"
	StreamName      = "CIRCUIT_BREAKER"
)

// NATSClient wraps NATS JetStream for guaranteed message delivery
type NATSClient struct {
	conn *nats.Conn
	js   nats.JetStreamContext
}

// NewNATSClient creates a new NATS JetStream client
func NewNATSClient(url string) (*NATSClient, error) {
	conn, err := nats.Connect(url,
		nats.RetryOnFailedConnect(true),
		nats.MaxReconnects(10),
		nats.ReconnectWait(2*time.Second),
		nats.DisconnectErrHandler(func(nc *nats.Conn, err error) {
			log.Printf("WARN: NATS disconnected: %v", err)
		}),
		nats.ReconnectHandler(func(nc *nats.Conn) {
			log.Printf("INFO: NATS reconnected to %s", nc.ConnectedUrl())
		}),
	)
	if err != nil {
		return nil, fmt.Errorf("connect to NATS: %w", err)
	}

	js, err := conn.JetStream()
	if err != nil {
		conn.Close()
		return nil, fmt.Errorf("create JetStream context: %w", err)
	}

	client := &NATSClient{conn: conn, js: js}

	if err := client.setupStream(); err != nil {
		conn.Close()
		return nil, fmt.Errorf("setup stream: %w", err)
	}

	return client, nil
}

// setupStream creates or ensures the JetStream stream exists
func (c *NATSClient) setupStream() error {
	_, err := c.js.StreamInfo(StreamName)
	if err != nil {
		// Stream doesn't exist, create it
		_, err = c.js.AddStream(&nats.StreamConfig{
			Name:     StreamName,
			Subjects: []string{"circuitbreaker.>"},
			MaxAge:   24 * time.Hour,
			Storage:  nats.FileStorage,
			Replicas: 1,
		})
		if err != nil {
			return fmt.Errorf("create stream: %w", err)
		}
		log.Printf("Created NATS JetStream stream: %s", StreamName)
	}
	return nil
}

// PublishBreachEvent publishes a breach event to the message queue
func (c *NATSClient) PublishBreachEvent(event models.BreachEvent) error {
	data, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("marshal event: %w", err)
	}

	_, err = c.js.Publish(BreachSubject, data)
	return err
}

// SubscribeBreachEvents subscribes to breach events
func (c *NATSClient) SubscribeBreachEvents(ctx context.Context, handler func(models.BreachEvent) error) error {
	sub, err := c.js.Subscribe(BreachSubject, func(msg *nats.Msg) {
		var event models.BreachEvent
		if err := json.Unmarshal(msg.Data, &event); err != nil {
			log.Printf("ERROR: unmarshal breach event: %v", err)
			msg.Nak()
			return
		}

		if err := handler(event); err != nil {
			log.Printf("ERROR: handle breach event: %v", err)
			msg.Nak()
			return
		}

		msg.Ack()
	}, nats.Durable("breach-processor"), nats.ManualAck())

	if err != nil {
		return fmt.Errorf("subscribe: %w", err)
	}

	go func() {
		<-ctx.Done()
		sub.Unsubscribe()
	}()

	return nil
}

// PublishMetrics publishes cost metrics for downstream processing
func (c *NATSClient) PublishMetrics(metrics []models.CostMetric) error {
	data, err := json.Marshal(metrics)
	if err != nil {
		return fmt.Errorf("marshal metrics: %w", err)
	}

	_, err = c.js.Publish(MetricsSubject, data)
	return err
}

// Close closes the NATS connection
func (c *NATSClient) Close() {
	if c.conn != nil {
		c.conn.Close()
	}
}

// InMemoryQueue is a simple in-memory queue for demo mode (no NATS required)
type InMemoryQueue struct {
	subscribers []func(models.BreachEvent) error
}

// NewInMemoryQueue creates a new in-memory queue
func NewInMemoryQueue() *InMemoryQueue {
	return &InMemoryQueue{}
}

// PublishBreachEvent publishes to all in-memory subscribers
func (q *InMemoryQueue) PublishBreachEvent(event models.BreachEvent) error {
	for _, sub := range q.subscribers {
		if err := sub(event); err != nil {
			return err
		}
	}
	return nil
}

// Subscribe adds a handler for breach events
func (q *InMemoryQueue) Subscribe(handler func(models.BreachEvent) error) {
	q.subscribers = append(q.subscribers, handler)
}