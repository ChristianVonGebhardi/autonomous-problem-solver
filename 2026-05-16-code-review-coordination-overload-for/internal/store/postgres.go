package store

import (
	"database/sql"
	"fmt"
	"time"

	_ "github.com/lib/pq"

	"github.com/code-review-coordinator/internal/models"
)

type PostgresStore struct {
	db *sql.DB
}

func NewPostgresStore(connectionString string) (*PostgresStore, error) {
	db, err := sql.Open("postgres", connectionString)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(5 * time.Minute)

	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	return &PostgresStore{db: db}, nil
}

func (s *PostgresStore) Migrate() error {
	queries := []string{
		`CREATE TABLE IF NOT EXISTS pull_requests (
			id BIGSERIAL PRIMARY KEY,
			repo_owner VARCHAR(255) NOT NULL,
			repo_name VARCHAR(255) NOT NULL,
			pr_number INT NOT NULL,
			title TEXT NOT NULL,
			author VARCHAR(255) NOT NULL,
			status VARCHAR(50) NOT NULL DEFAULT 'open',
			lines_added INT DEFAULT 0,
			lines_deleted INT DEFAULT 0,
			files_changed INT DEFAULT 0,
			complexity_score FLOAT DEFAULT 0,
			estimated_minutes INT DEFAULT 30,
			assigned_reviewer VARCHAR(255),
			assigned_at TIMESTAMPTZ,
			review_started_at TIMESTAMPTZ,
			completed_at TIMESTAMPTZ,
			created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
			updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
			UNIQUE(repo_owner, repo_name, pr_number)
		)`,
		`CREATE TABLE IF NOT EXISTS reviewers (
			username VARCHAR(255) PRIMARY KEY,
			email VARCHAR(255),
			full_name VARCHAR(255),
			current_load INT DEFAULT 0,
			max_load INT DEFAULT 3,
			avg_review_time INT DEFAULT 60,
			total_reviews INT DEFAULT 0,
			is_available BOOLEAN DEFAULT true,
			last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
			created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
			updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
		)`,
		`CREATE TABLE IF NOT EXISTS reviewer_expertise (
			id BIGSERIAL PRIMARY KEY,
			username VARCHAR(255) NOT NULL REFERENCES reviewers(username),
			file_pattern VARCHAR(255) NOT NULL,
			expertise_score FLOAT DEFAULT 0.5,
			review_count INT DEFAULT 0,
			created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
			updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
			UNIQUE(username, file_pattern)
		)`,
		`CREATE TABLE IF NOT EXISTS pr_files (
			id BIGSERIAL PRIMARY KEY,
			pr_id BIGINT NOT NULL REFERENCES pull_requests(id),
			filename TEXT NOT NULL,
			status VARCHAR(50),
			additions INT DEFAULT 0,
			deletions INT DEFAULT 0,
			changes INT DEFAULT 0
		)`,
		`CREATE TABLE IF NOT EXISTS review_events (
			id BIGSERIAL PRIMARY KEY,
			pr_id BIGINT NOT NULL REFERENCES pull_requests(id),
			reviewer VARCHAR(255),
			event_type VARCHAR(50) NOT NULL,
			details TEXT,
			created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
		)`,
		`CREATE INDEX IF NOT EXISTS idx_prs_status ON pull_requests(status)`,
		`CREATE INDEX IF NOT EXISTS idx_prs_assigned ON pull_requests(assigned_reviewer)`,
		`CREATE INDEX IF NOT EXISTS idx_prs_created ON pull_requests(created_at)`,
		`CREATE INDEX IF NOT EXISTS idx_review_events_pr ON review_events(pr_id)`,
		`CREATE INDEX IF NOT EXISTS idx_review_events_created ON review_events(created_at)`,
	}

	for _, q := range queries {
		if _, err := s.db.Exec(q); err != nil {
			return fmt.Errorf("migration failed: %w\nQuery: %s", err, q)
		}
	}
	return nil
}

// ── PR Operations ──────────────────────────────────────────────────────────────

func (s *PostgresStore) UpsertPR(pr *models.PullRequest) error {
	query := `
		INSERT INTO pull_requests (repo_owner, repo_name, pr_number, title, author, status,
			lines_added, lines_deleted, files_changed, complexity_score, estimated_minutes, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW(), NOW())
		ON CONFLICT (repo_owner, repo_name, pr_number)
		DO UPDATE SET
			title = EXCLUDED.title,
			status = EXCLUDED.status,
			lines_added = EXCLUDED.lines_added,
			lines_deleted = EXCLUDED.lines_deleted,
			files_changed = EXCLUDED.files_changed,
			updated_at = NOW()
		RETURNING id`

	return s.db.QueryRow(query,
		pr.RepoOwner, pr.RepoName, pr.PRNumber, pr.Title, pr.Author, pr.Status,
		pr.LinesAdded, pr.LinesDeleted, pr.FilesChanged, pr.ComplexityScore, pr.EstimatedMinutes,
	).Scan(&pr.ID)
}

func (s *PostgresStore) GetPR(id int64) (*models.PullRequest, error) {
	pr := &models.PullRequest{}
	query := `SELECT id, repo_owner, repo_name, pr_number, title, author, status,
		lines_added, lines_deleted, files_changed, complexity_score, estimated_minutes,
		COALESCE(assigned_reviewer, ''), assigned_at, review_started_at, completed_at,
		created_at, updated_at
		FROM pull_requests WHERE id = $1`

	err := s.db.QueryRow(query, id).Scan(
		&pr.ID, &pr.RepoOwner, &pr.RepoName, &pr.PRNumber, &pr.Title, &pr.Author, &pr.Status,
		&pr.LinesAdded, &pr.LinesDeleted, &pr.FilesChanged, &pr.ComplexityScore, &pr.EstimatedMinutes,
		&pr.AssignedReviewer, &pr.AssignedAt, &pr.ReviewStartedAt, &pr.CompletedAt,
		&pr.CreatedAt, &pr.UpdatedAt,
	)
	if err != nil {
		return nil, err
	}
	return pr, nil
}

func (s *PostgresStore) UpdatePRAnalysis(id int64, score float64, estimatedMinutes int) error {
	_, err := s.db.Exec(
		`UPDATE pull_requests SET complexity_score = $1, estimated_minutes = $2, updated_at = NOW() WHERE id = $3`,
		score, estimatedMinutes, id,
	)
	return err
}

func (s *PostgresStore) AssignReviewer(prID int64, reviewer string) error {
	now := time.Now()
	_, err := s.db.Exec(
		`UPDATE pull_requests SET assigned_reviewer = $1, assigned_at = $2, status = 'assigned', updated_at = NOW() WHERE id = $3`,
		reviewer, now, prID,
	)
	return err
}

func (s *PostgresStore) UpdatePRStatus(id int64, status string) error {
	query := `UPDATE pull_requests SET status = $1, updated_at = NOW()`
	args := []interface{}{status, id}

	switch status {
	case "in_review":
		query += `, review_started_at = NOW()`
	case "completed", "merged", "closed":
		query += `, completed_at = NOW()`
	}
	query += ` WHERE id = $2`

	_, err := s.db.Exec(query, args...)
	return err
}

func (s *PostgresStore) ListPRs(status string, limit int) ([]*models.PullRequest, error) {
	query := `SELECT id, repo_owner, repo_name, pr_number, title, author, status,
		lines_added, lines_deleted, files_changed, complexity_score, estimated_minutes,
		COALESCE(assigned_reviewer, ''), assigned_at, review_started_at, completed_at,
		created_at, updated_at
		FROM pull_requests`

	var args []interface{}
	if status != "" {
		query += ` WHERE status = $1`
		args = append(args, status)
	}
	query += ` ORDER BY created_at DESC`
	if limit > 0 {
		query += fmt.Sprintf(` LIMIT %d`, limit)
	}

	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var prs []*models.PullRequest
	for rows.Next() {
		pr := &models.PullRequest{}
		err := rows.Scan(
			&pr.ID, &pr.RepoOwner, &pr.RepoName, &pr.PRNumber, &pr.Title, &pr.Author, &pr.Status,
			&pr.LinesAdded, &pr.LinesDeleted, &pr.FilesChanged, &pr.ComplexityScore, &pr.EstimatedMinutes,
			&pr.AssignedReviewer, &pr.AssignedAt, &pr.ReviewStartedAt, &pr.CompletedAt,
			&pr.CreatedAt, &pr.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}
		prs = append(prs, pr)
	}
	return prs, rows.Err()
}

func (s *PostgresStore) SavePRFiles(prID int64, files []models.PRFile) error {
	if _, err := s.db.Exec(`DELETE FROM pr_files WHERE pr_id = $1`, prID); err != nil {
		return err
	}

	for _, f := range files {
		_, err := s.db.Exec(
			`INSERT INTO pr_files (pr_id, filename, status, additions, deletions, changes) VALUES ($1, $2, $3, $4, $5, $6)`,
			prID, f.Filename, f.Status, f.Additions, f.Deletions, f.Changes,
		)
		if err != nil {
			return err
		}
	}
	return nil
}

func (s *PostgresStore) GetPRFiles(prID int64) ([]models.PRFile, error) {
	rows, err := s.db.Query(
		`SELECT id, pr_id, filename, COALESCE(status,''), additions, deletions, changes FROM pr_files WHERE pr_id = $1`,
		prID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var files []models.PRFile
	for rows.Next() {
		var f models.PRFile
		if err := rows.Scan(&f.ID, &f.PRID, &f.Filename, &f.Status, &f.Additions, &f.Deletions, &f.Changes); err != nil {
			return nil, err
		}
		files = append(files, f)
	}
	return files, rows.Err()
}

// ── Reviewer Operations ────────────────────────────────────────────────────────

func (s *PostgresStore) UpsertReviewer(r *models.Reviewer) error {
	_, err := s.db.Exec(`
		INSERT INTO reviewers (username, email, full_name, max_load, is_available, last_active_at, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, NOW(), NOW(), NOW())
		ON CONFLICT (username) DO UPDATE SET
			email = EXCLUDED.email,
			full_name = EXCLUDED.full_name,
			is_available = EXCLUDED.is_available,
			updated_at = NOW()`,
		r.Username, r.Email, r.FullName, r.MaxLoad, r.IsAvailable,
	)
	return err
}

func (s *PostgresStore) GetReviewer(username string) (*models.Reviewer, error) {
	r := &models.Reviewer{}
	err := s.db.QueryRow(`
		SELECT username, COALESCE(email,''), COALESCE(full_name,''), current_load, max_load,
		avg_review_time, total_reviews, is_available, last_active_at, created_at, updated_at
		FROM reviewers WHERE username = $1`, username,
	).Scan(&r.Username, &r.Email, &r.FullName, &r.CurrentLoad, &r.MaxLoad,
		&r.AvgReviewTime, &r.TotalReviews, &r.IsAvailable, &r.LastActiveAt, &r.CreatedAt, &r.UpdatedAt)
	if err != nil {
		return nil, err
	}
	return r, nil
}

func (s *PostgresStore) ListReviewers() ([]*models.Reviewer, error) {
	rows, err := s.db.Query(`
		SELECT username, COALESCE(email,''), COALESCE(full_name,''), current_load, max_load,
		avg_review_time, total_reviews, is_available, last_active_at, created_at, updated_at
		FROM reviewers ORDER BY username`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var reviewers []*models.Reviewer
	for rows.Next() {
		r := &models.Reviewer{}
		if err := rows.Scan(&r.Username, &r.Email, &r.FullName, &r.CurrentLoad, &r.MaxLoad,
			&r.AvgReviewTime, &r.TotalReviews, &r.IsAvailable, &r.LastActiveAt, &r.CreatedAt, &r.UpdatedAt); err != nil {
			return nil, err
		}
		reviewers = append(reviewers, r)
	}
	return reviewers, rows.Err()
}

func (s *PostgresStore) IncrementReviewerLoad(username string) error {
	_, err := s.db.Exec(`
		UPDATE reviewers SET current_load = current_load + 1, last_active_at = NOW(), updated_at = NOW()
		WHERE username = $1`, username)
	return err
}

func (s *PostgresStore) DecrementReviewerLoad(username string) error {
	_, err := s.db.Exec(`
		UPDATE reviewers SET
			current_load = GREATEST(0, current_load - 1),
			total_reviews = total_reviews + 1,
			last_active_at = NOW(),
			updated_at = NOW()
		WHERE username = $1`, username)
	return err
}

func (s *PostgresStore) GetAvailableReviewers() ([]*models.Reviewer, error) {
	rows, err := s.db.Query(`
		SELECT username, COALESCE(email,''), COALESCE(full_name,''), current_load, max_load,
		avg_review_time, total_reviews, is_available, last_active_at, created_at, updated_at
		FROM reviewers
		WHERE is_available = true AND current_load < max_load
		ORDER BY current_load ASC, avg_review_time ASC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var reviewers []*models.Reviewer
	for rows.Next() {
		r := &models.Reviewer{}
		if err := rows.Scan(&r.Username, &r.Email, &r.FullName, &r.CurrentLoad, &r.MaxLoad,
			&r.AvgReviewTime, &r.TotalReviews, &r.IsAvailable, &r.LastActiveAt, &r.CreatedAt, &r.UpdatedAt); err != nil {
			return nil, err
		}
		reviewers = append(reviewers, r)
	}
	return reviewers, rows.Err()
}

func (s *PostgresStore) GetReviewerExpertise(username string) ([]models.ReviewerExpertise, error) {
	rows, err := s.db.Query(`
		SELECT id, username, file_pattern, expertise_score, review_count, created_at, updated_at
		FROM reviewer_expertise WHERE username = $1 ORDER BY expertise_score DESC`, username)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var expertise []models.ReviewerExpertise
	for rows.Next() {
		var e models.ReviewerExpertise
		if err := rows.Scan(&e.ID, &e.Username, &e.FilePattern, &e.ExpertiseScore, &e.ReviewCount, &e.CreatedAt, &e.UpdatedAt); err != nil {
			return nil, err
		}
		expertise = append(expertise, e)
	}
	return expertise, rows.Err()
}

func (s *PostgresStore) UpsertExpertise(username, pattern string, score float64) error {
	_, err := s.db.Exec(`
		INSERT INTO reviewer_expertise (username, file_pattern, expertise_score, review_count, created_at, updated_at)
		VALUES ($1, $2, $3, 1, NOW(), NOW())
		ON CONFLICT (username, file_pattern) DO UPDATE SET
			expertise_score = ($3 + reviewer_expertise.expertise_score) / 2.0,
			review_count = reviewer_expertise.review_count + 1,
			updated_at = NOW()`,
		username, pattern, score,
	)
	return err
}

// ── Events / Audit Log ─────────────────────────────────────────────────────────

func (s *PostgresStore) LogEvent(prID int64, reviewer, eventType, details string) error {
	_, err := s.db.Exec(
		`INSERT INTO review_events (pr_id, reviewer, event_type, details, created_at) VALUES ($1, $2, $3, $4, NOW())`,
		prID, reviewer, eventType, details,
	)
	return err
}

func (s *PostgresStore) GetPREvents(prID int64) ([]models.ReviewEvent, error) {
	rows, err := s.db.Query(`
		SELECT id, pr_id, COALESCE(reviewer,''), event_type, COALESCE(details,''), created_at
		FROM review_events WHERE pr_id = $1 ORDER BY created_at DESC`, prID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var events []models.ReviewEvent
	for rows.Next() {
		var e models.ReviewEvent
		if err := rows.Scan(&e.ID, &e.PRID, &e.Reviewer, &e.EventType, &e.Details, &e.CreatedAt); err != nil {
			return nil, err
		}
		events = append(events, e)
	}
	return events, rows.Err()
}

func (s *PostgresStore) GetRecentEvents(limit int) ([]models.ReviewEvent, error) {
	rows, err := s.db.Query(fmt.Sprintf(`
		SELECT id, pr_id, COALESCE(reviewer,''), event_type, COALESCE(details,''), created_at
		FROM review_events ORDER BY created_at DESC LIMIT %d`, limit))
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var events []models.ReviewEvent
	for rows.Next() {
		var e models.ReviewEvent
		if err := rows.Scan(&e.ID, &e.PRID, &e.Reviewer, &e.EventType, &e.Details, &e.CreatedAt); err != nil {
			return nil, err
		}
		events = append(events, e)
	}
	return events, rows.Err()
}

// ── Analytics ─────────────────────────────────────────────────────────────────

func (s *PostgresStore) GetMetricsOverview() (*models.MetricsOverview, error) {
	m := &models.MetricsOverview{}

	s.db.QueryRow(`SELECT COUNT(*) FROM pull_requests WHERE status IN ('open','assigned','in_review')`).Scan(&m.ActivePRs)
	s.db.QueryRow(`SELECT COUNT(*) FROM pull_requests WHERE created_at >= NOW() - INTERVAL '24 hours'`).Scan(&m.PRsToday)
	s.db.QueryRow(`SELECT COUNT(*) FROM pull_requests WHERE completed_at >= NOW() - INTERVAL '24 hours'`).Scan(&m.PRsCompletedToday)

	s.db.QueryRow(`
		SELECT COALESCE(AVG(EXTRACT(EPOCH FROM (assigned_at - created_at))/60), 0)
		FROM pull_requests WHERE assigned_at IS NOT NULL AND created_at >= NOW() - INTERVAL '7 days'`,
	).Scan(&m.AvgTimeToAssign)

	s.db.QueryRow(`
		SELECT COALESCE(AVG(EXTRACT(EPOCH FROM (review_started_at - assigned_at))/60), 0)
		FROM pull_requests WHERE review_started_at IS NOT NULL AND created_at >= NOW() - INTERVAL '7 days'`,
	).Scan(&m.AvgTimeToReview)

	s.db.QueryRow(`
		SELECT COALESCE(AVG(EXTRACT(EPOCH FROM (completed_at - created_at))/3600), 0)
		FROM pull_requests WHERE completed_at IS NOT NULL AND created_at >= NOW() - INTERVAL '7 days'`,
	).Scan(&m.AvgTimeToMerge)

	rows, err := s.db.Query(`
		SELECT username FROM reviewers
		WHERE current_load >= max_load AND is_available = true
		ORDER BY current_load DESC LIMIT 5`)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var username string
			if rows.Scan(&username) == nil {
				m.BottleneckReviewers = append(m.BottleneckReviewers, username)
			}
		}
	}

	if m.BottleneckReviewers == nil {
		m.BottleneckReviewers = []string{}
	}

	return m, nil
}

func (s *PostgresStore) GetReviewerStats() ([]models.ReviewerStats, error) {
	rows, err := s.db.Query(`
		SELECT
			r.username,
			r.current_load,
			r.max_load,
			r.avg_review_time,
			COALESCE(
				(SELECT COUNT(*) FROM pull_requests p
				WHERE p.assigned_reviewer = r.username
				AND p.completed_at >= NOW() - INTERVAL '24 hours'), 0
			) as completed_today
		FROM reviewers r
		ORDER BY r.current_load DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var stats []models.ReviewerStats
	for rows.Next() {
		var st models.ReviewerStats
		var maxLoad int
		if err := rows.Scan(&st.Username, &st.ActiveReviews, &maxLoad, &st.AvgReviewTime, &st.CompletedToday); err != nil {
			return nil, err
		}
		if maxLoad > 0 {
			st.UtilizationRate = float64(st.ActiveReviews) / float64(maxLoad)
		}
		st.IsBottleneck = st.ActiveReviews >= maxLoad
		stats = append(stats, st)
	}
	return stats, rows.Err()
}

func (s *PostgresStore) Close() error {
	return s.db.Close()
}