-- Healthcare Referral Platform - Initial Schema

-- Patients table
CREATE TABLE IF NOT EXISTS patients (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    external_id VARCHAR(100) UNIQUE NOT NULL,
    fhir_id VARCHAR(100),
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    date_of_birth DATE NOT NULL,
    gender VARCHAR(20),
    phone VARCHAR(20),
    email VARCHAR(200),
    address_line1 VARCHAR(200),
    address_line2 VARCHAR(100),
    city VARCHAR(100),
    state VARCHAR(50),
    zip_code VARCHAR(10),
    latitude DOUBLE,
    longitude DOUBLE,
    insurance_member_id VARCHAR(100),
    insurance_plan_name VARCHAR(200),
    insurance_payer_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Providers / Specialists table
CREATE TABLE IF NOT EXISTS providers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    npi VARCHAR(20) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    credentials VARCHAR(50),
    specialty VARCHAR(200) NOT NULL,
    specialty_code VARCHAR(50),
    practice_name VARCHAR(200),
    phone VARCHAR(20),
    fax VARCHAR(20),
    email VARCHAR(200),
    address_line1 VARCHAR(200),
    city VARCHAR(100),
    state_abbr VARCHAR(5),
    zip_code VARCHAR(10),
    latitude DOUBLE,
    longitude DOUBLE,
    accepting_new_patients BOOLEAN DEFAULT TRUE,
    average_wait_days INTEGER DEFAULT 14,
    portal_enabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Provider insurance networks
CREATE TABLE IF NOT EXISTS provider_insurance_networks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    provider_id BIGINT NOT NULL REFERENCES providers(id),
    payer_id VARCHAR(50) NOT NULL,
    payer_name VARCHAR(200) NOT NULL,
    network_name VARCHAR(200),
    effective_date DATE,
    termination_date DATE,
    UNIQUE(provider_id, payer_id)
);

-- Referring providers
CREATE TABLE IF NOT EXISTS referring_providers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    npi VARCHAR(20) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    specialty VARCHAR(200),
    practice_name VARCHAR(200),
    phone VARCHAR(20),
    fax VARCHAR(20),
    email VARCHAR(200),
    health_system_id VARCHAR(100),
    emr_system VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Referrals (core entity)
CREATE TABLE IF NOT EXISTS referrals (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    referral_number VARCHAR(50) UNIQUE NOT NULL,
    fhir_service_request_id VARCHAR(100),
    status VARCHAR(50) NOT NULL DEFAULT 'NEW',
    priority VARCHAR(20) NOT NULL DEFAULT 'ROUTINE',

    -- Patient
    patient_id BIGINT NOT NULL REFERENCES patients(id),

    -- Referring provider
    referring_provider_id BIGINT REFERENCES referring_providers(id),

    -- Assigned specialist (after matching)
    assigned_provider_id BIGINT REFERENCES providers(id),

    -- Clinical info
    specialty_needed VARCHAR(200) NOT NULL,
    specialty_code VARCHAR(50),
    reason_for_referral TEXT NOT NULL,
    clinical_notes TEXT,
    diagnosis_codes VARCHAR(500),
    procedure_codes VARCHAR(500),

    -- Insurance
    insurance_payer_id VARCHAR(50),
    insurance_member_id VARCHAR(100),
    prior_auth_required BOOLEAN DEFAULT FALSE,
    prior_auth_number VARCHAR(100),
    prior_auth_status VARCHAR(50),
    prior_auth_submitted_at TIMESTAMP,
    prior_auth_decision_at TIMESTAMP,

    -- Appointment
    appointment_id VARCHAR(100),
    appointment_datetime TIMESTAMP,
    appointment_status VARCHAR(50),

    -- Tracking
    emr_order_id VARCHAR(100),
    source_system VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    due_date DATE,

    -- Communication
    patient_notified_at TIMESTAMP,
    patient_confirmed_at TIMESTAMP,
    specialist_sent_at TIMESTAMP,
    consult_note_received_at TIMESTAMP,

    -- Metrics
    matching_attempts INTEGER DEFAULT 0,
    notification_attempts INTEGER DEFAULT 0
);

-- Referral state history (audit trail)
CREATE TABLE IF NOT EXISTS referral_state_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    referral_id BIGINT NOT NULL REFERENCES referrals(id),
    from_status VARCHAR(50),
    to_status VARCHAR(50) NOT NULL,
    transition_event VARCHAR(100),
    notes TEXT,
    performed_by VARCHAR(200),
    performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Referral documents
CREATE TABLE IF NOT EXISTS referral_documents (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    referral_id BIGINT NOT NULL REFERENCES referrals(id),
    document_type VARCHAR(100) NOT NULL,
    file_name VARCHAR(300),
    content_type VARCHAR(100),
    storage_path VARCHAR(500),
    document_content TEXT,
    uploaded_by VARCHAR(200),
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Communication log
CREATE TABLE IF NOT EXISTS communication_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    referral_id BIGINT REFERENCES referrals(id),
    channel VARCHAR(50) NOT NULL,
    recipient_type VARCHAR(50) NOT NULL,
    recipient_address VARCHAR(300) NOT NULL,
    subject VARCHAR(500),
    message_body TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    external_message_id VARCHAR(200),
    sent_at TIMESTAMP,
    delivered_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Prior authorization requests
CREATE TABLE IF NOT EXISTS prior_auth_requests (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    referral_id BIGINT NOT NULL REFERENCES referrals(id),
    auth_number VARCHAR(100),
    payer_id VARCHAR(50) NOT NULL,
    payer_name VARCHAR(200),
    procedure_codes VARCHAR(500),
    diagnosis_codes VARCHAR(500),
    clinical_justification TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    submitted_at TIMESTAMP,
    decision_at TIMESTAMP,
    denial_reason TEXT,
    appeal_deadline DATE,
    expires_at DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_referrals_status ON referrals(status);
CREATE INDEX IF NOT EXISTS idx_referrals_patient_id ON referrals(patient_id);
CREATE INDEX IF NOT EXISTS idx_referrals_assigned_provider ON referrals(assigned_provider_id);
CREATE INDEX IF NOT EXISTS idx_referrals_created_at ON referrals(created_at);
CREATE INDEX IF NOT EXISTS idx_referral_history_referral_id ON referral_state_history(referral_id);
CREATE INDEX IF NOT EXISTS idx_comm_log_referral_id ON communication_log(referral_id);
CREATE INDEX IF NOT EXISTS idx_providers_specialty ON providers(specialty_code);