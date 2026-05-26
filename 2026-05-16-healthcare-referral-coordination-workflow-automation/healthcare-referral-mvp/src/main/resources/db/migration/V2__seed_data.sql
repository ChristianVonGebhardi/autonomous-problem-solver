-- Seed data for MVP demonstration

-- Insert referring providers
INSERT INTO referring_providers (npi, first_name, last_name, specialty, practice_name, phone, fax, email, health_system_id, emr_system)
VALUES
('1234567890', 'Sarah', 'Johnson', 'Family Medicine', 'Riverside Primary Care', '555-0100', '555-0101', 'dr.johnson@riverside.example', 'HS001', 'EPIC'),
('1234567891', 'Michael', 'Chen', 'Internal Medicine', 'Metro Health Associates', '555-0110', '555-0111', 'dr.chen@metro.example', 'HS001', 'EPIC'),
('1234567892', 'Lisa', 'Williams', 'Pediatrics', 'Children''s Wellness Center', '555-0120', '555-0121', 'dr.williams@childrens.example', 'HS002', 'CERNER');

-- Insert specialist providers
INSERT INTO providers (npi, first_name, last_name, credentials, specialty, specialty_code, practice_name, phone, fax, email, address_line1, city, state_abbr, zip_code, latitude, longitude, accepting_new_patients, average_wait_days, portal_enabled)
VALUES
('2000000001', 'Robert', 'Anderson', 'MD', 'Cardiology', 'CARDIO', 'Heart & Vascular Institute', '555-0200', '555-0201', 'r.anderson@heartinst.example', '100 Medical Center Dr', 'Boston', 'MA', '02101', 42.3601, -71.0589, TRUE, 10, TRUE),
('2000000002', 'Jennifer', 'Martinez', 'MD, FACC', 'Cardiology', 'CARDIO', 'Boston Cardiology Group', '555-0210', '555-0211', 'j.martinez@bcg.example', '200 Health Plaza', 'Boston', 'MA', '02102', 42.3611, -71.0599, TRUE, 14, FALSE),
('2000000003', 'David', 'Thompson', 'MD', 'Orthopedics', 'ORTHO', 'Boston Orthopedic Center', '555-0220', '555-0221', 'd.thompson@boc.example', '300 Sports Medicine Way', 'Cambridge', 'MA', '02139', 42.3736, -71.1097, TRUE, 21, TRUE),
('2000000004', 'Emily', 'Wilson', 'MD, PhD', 'Neurology', 'NEURO', 'Neuroscience Associates', '555-0230', '555-0231', 'e.wilson@neuro.example', '400 Brain Health Blvd', 'Boston', 'MA', '02103', 42.3621, -71.0609, TRUE, 18, FALSE),
('2000000005', 'James', 'Brown', 'MD', 'Gastroenterology', 'GI', 'Digestive Health Center', '555-0240', '555-0241', 'j.brown@dhc.example', '500 Wellness Ave', 'Newton', 'MA', '02458', 42.3370, -71.2092, FALSE, 30, TRUE),
('2000000006', 'Patricia', 'Davis', 'MD', 'Endocrinology', 'ENDO', 'Diabetes & Endocrine Clinic', '555-0250', '555-0251', 'p.davis@dec.example', '600 Hormone Health Dr', 'Brookline', 'MA', '02445', 42.3318, -71.1212, TRUE, 25, TRUE),
('2000000007', 'Thomas', 'Miller', 'MD, FACS', 'Orthopedics', 'ORTHO', 'New England Spine & Joint', '555-0260', '555-0261', 't.miller@nesj.example', '700 Joint Care Ln', 'Boston', 'MA', '02110', 42.3571, -71.0503, TRUE, 16, FALSE),
('2000000008', 'Susan', 'Taylor', 'MD', 'Pulmonology', 'PULM', 'Breathing & Sleep Center', '555-0270', '555-0271', 's.taylor@bsc.example', '800 Lung Health Pkwy', 'Waltham', 'MA', '02451', 42.3765, -71.2356, TRUE, 20, TRUE);

-- Insert insurance networks for providers
INSERT INTO provider_insurance_networks (provider_id, payer_id, payer_name, network_name, effective_date)
VALUES
(1, 'BCBS-MA', 'Blue Cross Blue Shield MA', 'BlueCare Network', '2023-01-01'),
(1, 'AETNA', 'Aetna', 'Choice POS II', '2023-01-01'),
(1, 'UHC', 'United Healthcare', 'Choice Plus', '2023-01-01'),
(2, 'BCBS-MA', 'Blue Cross Blue Shield MA', 'BlueCare Network', '2023-01-01'),
(2, 'CIGNA', 'Cigna', 'Open Access Plus', '2023-01-01'),
(3, 'BCBS-MA', 'Blue Cross Blue Shield MA', 'BlueCare Network', '2023-01-01'),
(3, 'UHC', 'United Healthcare', 'Choice Plus', '2023-01-01'),
(3, 'MEDICARE', 'Medicare', 'Original Medicare', '2023-01-01'),
(4, 'AETNA', 'Aetna', 'Choice POS II', '2023-01-01'),
(4, 'BCBS-MA', 'Blue Cross Blue Shield MA', 'BlueCare Network', '2023-01-01'),
(5, 'UHC', 'United Healthcare', 'Choice Plus', '2023-01-01'),
(5, 'CIGNA', 'Cigna', 'Open Access Plus', '2023-01-01'),
(6, 'BCBS-MA', 'Blue Cross Blue Shield MA', 'BlueCare Network', '2023-01-01'),
(6, 'AETNA', 'Aetna', 'Choice POS II', '2023-01-01'),
(6, 'MEDICARE', 'Medicare', 'Original Medicare', '2023-01-01'),
(7, 'UHC', 'United Healthcare', 'Choice Plus', '2023-01-01'),
(7, 'CIGNA', 'Cigna', 'Open Access Plus', '2023-01-01'),
(8, 'BCBS-MA', 'Blue Cross Blue Shield MA', 'BlueCare Network', '2023-01-01'),
(8, 'MEDICARE', 'Medicare', 'Original Medicare', '2023-01-01');

-- Insert sample patients
INSERT INTO patients (external_id, fhir_id, first_name, last_name, date_of_birth, gender, phone, email, address_line1, city, state, zip_code, latitude, longitude, insurance_member_id, insurance_plan_name, insurance_payer_id)
VALUES
('PAT-001', 'fhir-pat-001', 'John', 'Smith', '1958-03-15', 'MALE', '555-1001', 'john.smith@email.example', '42 Oak Street', 'Boston', 'MA', '02115', 42.3442, -71.0897, 'BCBS123456', 'BlueCare Premier', 'BCBS-MA'),
('PAT-002', 'fhir-pat-002', 'Mary', 'Johnson', '1972-07-22', 'FEMALE', '555-1002', 'mary.j@email.example', '88 Elm Ave', 'Cambridge', 'MA', '02140', 42.3776, -71.1190, 'UHC789012', 'Choice Plus Gold', 'UHC'),
('PAT-003', 'fhir-pat-003', 'Robert', 'Garcia', '1965-11-30', 'MALE', '555-1003', 'r.garcia@email.example', '15 Maple Rd', 'Newton', 'MA', '02460', 42.3370, -71.2092, 'AET345678', 'Aetna PPO', 'AETNA'),
('PAT-004', 'fhir-pat-004', 'Linda', 'Williams', '1980-05-14', 'FEMALE', '555-1004', 'linda.w@email.example', '233 Pine St', 'Brookline', 'MA', '02446', 42.3318, -71.1212, 'BCBS654321', 'BlueCare Network', 'BCBS-MA'),
('PAT-005', 'fhir-pat-005', 'James', 'Brown', '1950-09-08', 'MALE', '555-1005', 'james.b@email.example', '71 Walnut Ln', 'Waltham', 'MA', '02452', 42.3765, -71.2356, 'MED-A12345', 'Medicare Part B', 'MEDICARE');