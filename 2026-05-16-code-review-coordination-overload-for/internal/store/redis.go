package store

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/code-review-coordinator/internal/models"
)

type RedisStore struct {
	client *redis.Client
}

func NewRedisStore(addr string) (*RedisStore, error) {
	client := redis.NewClient(&redis.Options{
		Addr:         addr,
		DialTimeout:  5 * time.Second,
		ReadTimeout:  3 * time.Second,
		WriteTimeout: 3 * time.Second,
	})

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("failed to connect to Redis: %w", err)
	}

	return &RedisStore{client: client}, nil
}

const (
	reviewerCapacityPrefix = "reviewer:capacity:"
	prQueueKey             = "pr:queue"
	prStatePrefix          = "pr:state:"
	routingLockPrefix      = "routing:lock:"
)

// Reviewer Capacity

func (r *RedisStore) SetReviewerCapacity(ctx context.Context, username string, load, maxLoad int) error {
	key := reviewerCapacityPrefix + username
	data := map[string]interface{}{
		"current_load": load,
		"max_load":     maxLoad,
		"updated_at":   time.Now().Unix(),
	}
	return r.client.HSet(ctx, key, data).Err()
}

func (r *RedisStore) GetReviewerCapacity(ctx context.Context, username string) (int, int, error) {
	key := reviewerCapacityPrefix + username
	vals, err := r.client.HMGet(ctx, key, "current_load", "max_load").Result()
	if err != nil {
		return 0, 0, err
	}

	var load, maxLoad int
	if vals[0] != nil {
		fmt.Sscanf(fmt.Sprint(vals[0]), "%d", &load)
	}
	if vals[1] != nil {
		fmt.Sscanf(fmt.Sprint(vals[1]), "%d", &maxLoad)
		if maxLoad == 0 {
			maxLoad = 3 // default
		}
	}
	return load, maxLoad, nil
}

func (r *RedisStore) IncrementReviewerLoad(ctx context.Context, username string) error {
	key := reviewerCapacityPrefix + username
	return r.client.HIncrBy(ctx, key, "current_load", 1).Err()
}

func (r *RedisStore) DecrementReviewerLoad(ctx context.Context, username string) error {
	key := reviewerCapacityPrefix + username
	pipe := r.client.Pipeline()
	pipe.HIncrBy(ctx, key, "current_load", -1)
	pipe.HSet(ctx, key, "updated_at", time.Now().Unix())
	_, err := pipe.Exec(ctx)
	return err
}

// PR Queue (sorted set by priority score)

func (r *RedisStore) EnqueuePR(ctx context.Context, prID int64, priorityScore float64) error {
	return r.client.ZAdd(ctx, prQueueKey, redis.Z{
		Score:  priorityScore,
		Member: fmt.Sprintf("%d", prID),
	}).Err()
}

func (r *RedisStore) DequeuePR(ctx context.Context) (int64, error) {
	// Get highest priority (highest score)
	results, err := r.client.ZRevRangeWithScores(ctx, prQueueKey, 0, 0).Result()
	if err != nil || len(results) == 0 {
		return 0, err
	}

	var prID int64
	fmt.Sscanf(fmt.Sprint(results[0].Member), "%d", &prID)
	return prID, nil
}

func (r *RedisStore) RemoveFromQueue(ctx context.Context, prID int64) error {
	return r.client.ZRem(ctx, prQueueKey, fmt.Sprintf("%d", prID)).Err()
}

func (r *RedisStore) GetQueueLength(ctx context.Context) (int64, error) {
	return r.client.ZCard(ctx, prQueueKey).Err()
}

func (r *RedisStore) GetQueuedPRs(ctx context.Context) ([]int64, error) {
	results, err := r.client.ZRevRange(ctx, prQueueKey, 0, -1).Result()
	if err != nil {
		return nil, err
	}

	var ids []int64
	for _, result := range results {
		var id int64
		fmt.Sscanf(result, "%d", &id)
		ids = append(ids, id)
	}
	return ids, nil
}

// PR State Cache

func (r *RedisStore) CachePR(ctx context.Context, pr *models.PullRequest, ttl time.Duration) error {
	key := prStatePrefix + fmt.Sprintf("%d", pr.ID)
	data, err := json.Marshal(pr)
	if err != nil {
		return err
	}
	return r.client.Set(ctx, key, data, ttl).Err()
}

func (r *RedisStore) GetCachedPR(ctx context.Context, prID int64) (*models.PullRequest, error) {
	key := prStatePrefix + fmt.Sprintf("%d", prID)
	data, err := r.client.Get(ctx, key).Bytes()
	if err != nil {
		return nil, err
	}

	var pr models.PullRequest
	if err := json.Unmarshal(data, &pr); err != nil {
		return nil, err
	}
	return &pr, nil
}

// Routing Locks (prevent double-assignment)

func (r *RedisStore) AcquireRoutingLock(ctx context.Context, prID int64, ttl time.Duration) (bool, error) {
	key := routingLockPrefix + fmt.Sprintf("%d", prID)
	return r.client.SetNX(ctx, key, "1", ttl).Result()
}

func (r *RedisStore) ReleaseRoutingLock(ctx context.Context, prID int64) error {
	key := routingLockPrefix + fmt.Sprintf("%d", prID)
	return r.client.Del(ctx, key).Err()
}

// Health

func (r *RedisStore) Ping(ctx context.Context) error {
	return r.client.Ping(ctx).Err()
}

func (r *RedisStore) Close() error {
	return r.client.Close()
}