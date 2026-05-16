-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- Referrals table
CREATE TABLE referrals (
    id BIGSERIAL PRIMARY KEY,
    fhir_id VARCHAR(255) UNIQUE NOT NULL,
    patient_name VARCHAR(255) NOT NULL,
    patient_phone VARCHAR(50),
    patient_email VARCHAR(255),
    patient_mrn VARCHAR(100) NOT NULL,
    patient_dob DATE NOT NULL,
    
    referring_provider_name VARCHAR(255) NOT NULL,
    referring_provider_npi VARCHAR(20) NOT NULL,
    referring_facility VARCHAR(255) NOT NULL,
    
    specialty VARCHAR(100) NOT NULL,
    reason_code VARCHAR(50) NOT NULL,
    reason_text TEXT NOT NULL,
    priority VARCHAR(20) NOT NULL,
    clinical_notes TEXT,
    
    insurance_payer VARCHAR(255),
    insurance_member_id VARCHAR(100),
    insurance_group_id VARCHAR(100),
    
    patient_location GEOGRAPHY(POINT, 4326),
    preferred_distance_miles INTEGER DEFAULT 25,
    
    status VARCHAR(50) NOT NULL,
    workflow_id VARCHAR(255),
    
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_referral_status (status),
    INDEX idx_referral_specialty (specialty),
    INDEX idx_referral_created (created_at),
    INDEX idx_referral_workflow (workflow_id),
    INDEX idx_patient_location USING GIST (patient_location)
);

-- Specialists table
CREATE TABLE specialists (
    id BIGSERIAL PRIMARY KEY,
    npi VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    specialty VARCHAR(100) NOT NULL,
    subspecialties TEXT[],
    
    practice_name VARCHAR(255) NOT NULL,
    practice_location GEOGRAPHY(POINT, 4326) NOT NULL,
    address_line1 VARCHAR(255) NOT NULL,
    address_line2 VARCHAR(255),
    city VARCHAR(100) NOT NULL,
    state VARCHAR(2) NOT NULL,
    zip_code VARCHAR(10) NOT NULL,
    
    phone VARCHAR(50) NOT NULL,
    fax VARCHAR(50),
    email VARCHAR(255),
    
    accepting_new_patients BOOLEAN DEFAULT true,
    average_wait_days INTEGER DEFAULT 14,
    
    has_emr_integration BOOLEAN DEFAULT false,
    emr_system VARCHAR(100),
    
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_specialist_specialty (specialty),
    INDEX idx_specialist_location USING GIST (practice_location),
    INDEX idx_specialist_accepting (accepting_new_patients)
);

-- Insurance Networks table (specialists accepting specific insurance)
CREATE TABLE insurance_networks (
    id BIGSERIAL PRIMARY KEY,
    specialist_id BIGINT NOT NULL REFERENCES specialists(id),
    payer_name VARCHAR(255) NOT NULL,
    network_name VARCHAR(255),
    effective_date DATE NOT NULL,
    termination_date DATE,
    
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(specialist_id, payer_name, network_name),
    INDEX idx_network_specialist (specialist_id),
    INDEX idx_network_payer (payer_name)
);

-- Referral Assignments (matched specialist)
CREATE TABLE referral_assignments (
    id BIGSERIAL PRIMARY KEY,
    referral_id BIGINT NOT NULL REFERENCES referrals(id),
    specialist_id BIGINT NOT NULL REFERENCES specialists(id),
    
    distance_miles DECIMAL(10, 2),
    match_score DECIMAL(5, 2),
    match_reason TEXT,
    
    status VARCHAR(50) NOT NULL,
    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    accepted_at TIMESTAMP,
    rejected_at TIMESTAMP,
    rejection_reason TEXT,
    
    appointment_date TIMESTAMP,
    appointment_confirmed BOOLEAN DEFAULT false,
    
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_assignment_referral (referral_id),
    INDEX idx_assignment_specialist (specialist_id),
    INDEX idx_assignment_status (status)
);

-- Prior Authorization Requests
CREATE TABLE prior_auth_requests (
    id BIGSERIAL PRIMARY KEY,
    referral_id BIGINT NOT NULL REFERENCES referrals(id),
    
    payer_name VARCHAR(255) NOT NULL,
    auth_type VARCHAR(100) NOT NULL,
    
    status VARCHAR(50) NOT NULL,
    auth_number VARCHAR(100),
    
    submitted_at TIMESTAMP,
    approved_at TIMESTAMP,
    denied_at TIMESTAMP,
    denial_reason TEXT,
    
    clinical_justification TEXT,
    extracted_codes TEXT[],
    ai_response TEXT,
    
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_auth_referral (referral_id),
    INDEX idx_auth_status (status)
);

-- Patient Communications
CREATE TABLE patient_communications (
    id BIGSERIAL PRIMARY KEY,
    referral_id BIGINT NOT NULL REFERENCES referrals(id),
    
    channel VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    
    recipient VARCHAR(255) NOT NULL,
    message_content TEXT NOT NULL,
    
    status VARCHAR(50) NOT NULL,
    external_id VARCHAR(255),
    
    sent_at TIMESTAMP,
    delivered_at TIMESTAMP,
    failed_at TIMESTAMP,
    failure_reason TEXT,
    
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_comm_referral (referral_id),
    INDEX idx_comm_channel (channel),
    INDEX idx_comm_status (status)
);

-- Workflow Events (audit log)
CREATE TABLE workflow_events (
    id BIGSERIAL PRIMARY KEY,
    referral_id BIGINT NOT NULL REFERENCES referrals(id),
    workflow_id VARCHAR(255),
    
    event_type VARCHAR(100) NOT NULL,
    event_data JSONB NOT NULL,
    
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_event_referral (referral_id),
    INDEX idx_event_workflow (workflow_id),
    INDEX idx_event_type (event_type),
    INDEX idx_event_created (created_at)
);

-- Update trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_referrals_updated_at BEFORE UPDATE ON referrals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_specialists_updated_at BEFORE UPDATE ON specialists
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_assignments_updated_at BEFORE UPDATE ON referral_assignments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_auth_updated_at BEFORE UPDATE ON prior_auth_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();