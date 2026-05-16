package models

import "time"

// PullRequest represents a PR in the system
type PullRequest struct {
	ID             int64     `json:"id" db:"id"`
	RepoOwner      string    `json:"repo_owner" db:"repo_owner"`
	RepoName       string    `json:"repo_name" db:"repo_name"`
	PRNumber       int       `json:"pr_number" db:"pr_number"`
	Title          string    `json:"title" db:"title"`
	Author         string    `json:"author" db:"author"`
	Status         string    `json:"status" db:"status"` // open, assigned, in_review, completed, merged, closed
	LinesAdded     int       `json:"lines_added" db:"lines_added"`
	LinesDeleted   int       `json:"lines_deleted" db:"lines_deleted"`
	FilesChanged   int       `json:"files_changed" db:"files_changed"`
	ComplexityScore float64  `json:"complexity_score" db:"complexity_score"`
	EstimatedMinutes int     `json:"estimated_minutes" db:"estimated_minutes"`
	AssignedReviewer string  `json:"assigned_reviewer,omitempty" db:"assigned_reviewer"`
	AssignedAt      *time.Time `json:"assigned_at,omitempty" db:"assigned_at"`
	ReviewStartedAt *time.Time `json:"review_started_at,omitempty" db:"review_started_at"`
	CompletedAt     *time.Time `json:"completed_at,omitempty" db:"completed_at"`
	CreatedAt       time.Time `json:"created_at" db:"created_at"`
	UpdatedAt       time.Time `json:"updated_at" db:"updated_at"`
}

// Reviewer represents a code reviewer
type Reviewer struct {
	Username       string    `json:"username" db:"username"`
	Email          string    `json:"email" db:"email"`
	FullName       string    `json:"full_name" db:"full_name"`
	CurrentLoad    int       `json:"current_load" db:"current_load"` // Number of active reviews
	MaxLoad        int       `json:"max_load" db:"max_load"`         // Max concurrent reviews
	AvgReviewTime  int       `json:"avg_review_time" db:"avg_review_time"` // Minutes
	TotalReviews   int       `json:"total_reviews" db:"total_reviews"`
	IsAvailable    bool      `json:"is_available" db:"is_available"`
	LastActiveAt   time.Time `json:"last_active_at" db:"last_active_at"`
	CreatedAt      time.Time `json:"created_at" db:"created_at"`
	UpdatedAt      time.Time `json:"updated_at" db:"updated_at"`
}

// ReviewerExpertise represents file/language expertise
type ReviewerExpertise struct {
	ID           int64     `json:"id" db:"id"`
	Username     string    `json:"username" db:"username"`
	FilePattern  string    `json:"file_pattern" db:"file_pattern"` // e.g., "*.go", "frontend/*"
	ExpertiseScore float64 `json:"expertise_score" db:"expertise_score"` // 0-1.0
	ReviewCount  int       `json:"review_count" db:"review_count"`
	CreatedAt    time.Time `json:"created_at" db:"created_at"`
	UpdatedAt    time.Time `json:"updated_at" db:"updated_at"`
}

// PRFile represents a file changed in a PR
type PRFile struct {
	ID         int64  `json:"id" db:"id"`
	PRID       int64  `json:"pr_id" db:"pr_id"`
	Filename   string `json:"filename" db:"filename"`
	Status     string `json:"status" db:"status"` // added, modified, deleted, renamed
	Additions  int    `json:"additions" db:"additions"`
	Deletions  int    `json:"deletions" db:"deletions"`
	Changes    int    `json:"changes" db:"changes"`
}

// AnalysisRequest sent to Python ML service
type AnalysisRequest struct {
	PRID         int64    `json:"pr_id"`
	LinesAdded   int      `json:"lines_added"`
	LinesDeleted int      `json:"lines_deleted"`
	FilesChanged int      `json:"files_changed"`
	Files        []string `json:"files"`
	Author       string   `json:"author"`
}

// AnalysisResponse from Python ML service
type AnalysisResponse struct {
	ComplexityScore  float64 `json:"complexity_score"`
	EstimatedMinutes int     `json:"estimated_minutes"`
	RiskLevel        string  `json:"risk_level"` // low, medium, high
}

// RoutingRequest for optimal reviewer assignment
type RoutingRequest struct {
	PRID            int64   `json:"pr_id"`
	ComplexityScore float64 `json:"complexity_score"`
	Files           []string `json:"files"`
	Author          string  `json:"author"`
}

// RoutingResponse with assigned reviewer
type RoutingResponse struct {
	AssignedReviewer string  `json:"assigned_reviewer"`
	Confidence       float64 `json:"confidence"`
	Reason           string  `json:"reason"`
}

// NotificationRequest for Slack/email
type NotificationRequest struct {
	PRID             int64  `json:"pr_id"`
	RepoOwner        string `json:"repo_owner"`
	RepoName         string `json:"repo_name"`
	PRNumber         int    `json:"pr_number"`
	Title            string `json:"title"`
	Author           string `json:"author"`
	AssignedReviewer string `json:"assigned_reviewer"`
	ComplexityScore  float64 `json:"complexity_score"`
	EstimatedMinutes int    `json:"estimated_minutes"`
	URL              string `json:"url"`
}

// MetricsOverview for dashboard
type MetricsOverview struct {
	ActivePRs           int     `json:"active_prs"`
	AvgTimeToAssign     float64 `json:"avg_time_to_assign_minutes"`
	AvgTimeToReview     float64 `json:"avg_time_to_review_minutes"`
	AvgTimeToMerge      float64 `json:"avg_time_to_merge_hours"`
	PRsToday            int     `json:"prs_today"`
	PRsCompletedToday   int     `json:"prs_completed_today"`
	BottleneckReviewers []string `json:"bottleneck_reviewers"`
}

// ReviewerStats for dashboard
type ReviewerStats struct {
	Username         string  `json:"username"`
	ActiveReviews    int     `json:"active_reviews"`
	CompletedToday   int     `json:"completed_today"`
	AvgReviewTime    int     `json:"avg_review_time_minutes"`
	UtilizationRate  float64 `json:"utilization_rate"` // current_load / max_load
	IsBottleneck     bool    `json:"is_bottleneck"`
}