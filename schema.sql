-- =============================================================
-- FrontDesk AI – Database Schema
-- =============================================================

-- -------------------------------------------------------------
-- ENUMS
-- -------------------------------------------------------------

CREATE TYPE staff_role AS ENUM ('admin', 'front_desk', 'provider', 'read_only');

CREATE TYPE dow AS ENUM ('0','1','2','3','4','5','6');

CREATE TYPE btype AS ENUM ('available', 'blocked', 'vacation');

CREATE TYPE direction AS ENUM ('inbound', 'outbound');

CREATE TYPE outcome AS ENUM ('booked', 'rescheduled', 'transferred', 'voicemail', 'info_only');

CREATE TYPE eligibility_status AS ENUM ('active', 'inactive', 'unknown');

CREATE TYPE network_status AS ENUM ('in_network', 'accepted', 'limited', 'not_accepted');

CREATE TYPE referral_status AS ENUM ('received', 'scheduled', 'seen', 'closed', 'expired');

CREATE TYPE appointment_status AS ENUM ('scheduled', 'confirmed', 'checked_in', 'completed', 'cancelled', 'no_show');

CREATE TYPE audit_action AS ENUM ('view', 'create', 'update', 'delete', 'export');

-- -------------------------------------------------------------
-- TABLES
-- -------------------------------------------------------------

-- 1. organization (root — everything depends on this)
CREATE TABLE organization (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  timezone VARCHAR(100) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- 2. staff_user
CREATE TABLE staff_user (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organization(id),
  name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL,
  role staff_role NOT NULL,
  auth_subject_id VARCHAR(255),
  last_login_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  deleted_at TIMESTAMP,
  UNIQUE (org_id, email)
);

-- 3. patient
CREATE TABLE patient (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organization(id),
  source VARCHAR(50),
  external_id VARCHAR(255),
  first_name VARCHAR(255) NOT NULL,
  last_name VARCHAR(255) NOT NULL,
  dob DATE NOT NULL,
  phone VARCHAR(20) NOT NULL,
  email VARCHAR(255) NOT NULL,
  mrn VARCHAR(255),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  deleted_at TIMESTAMP,
  UNIQUE (org_id, email),
  UNIQUE (mrn),
  UNIQUE (org_id, phone)
);

-- 4. provider
CREATE TABLE provider (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organization(id),
  source VARCHAR(50),
  external_id VARCHAR(255),
  name VARCHAR(255) NOT NULL,
  specialty VARCHAR(255),
  npi VARCHAR(255),
  languages JSONB,
  accepting_new_patients BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  deleted_at TIMESTAMP,
  UNIQUE (npi)
);

-- 5. provider_availability
CREATE TABLE provider_availability (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organization(id),
  provider_id UUID REFERENCES provider(id),
  weekday dow,
  specific_date DATE,
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,
  block_type btype NOT NULL,
  valid_from DATE,
  valid_to DATE,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  deleted_at TIMESTAMP
);

-- 6. accepted_plan
CREATE TABLE accepted_plan (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organization(id),
  payer_name VARCHAR(255),
  network_status network_status,
  requires_referral BOOLEAN,
  requires_auth BOOLEAN,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  deleted_at TIMESTAMP
);

-- 7. call
CREATE TABLE call (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organization(id),
  patient_id UUID REFERENCES patient(id),
  direction direction NOT NULL,
  caller_phone VARCHAR(20) NOT NULL,
  caller_email VARCHAR(255),
  started_at TIMESTAMP,
  duration_seconds INTEGER,
  outcome outcome,
  recording_url VARCHAR(500),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  deleted_at TIMESTAMP
);

-- 8. transcript
CREATE TABLE transcript (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organization(id),
  call_id UUID UNIQUE REFERENCES call(id),
  content JSONB,
  redacted BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  deleted_at TIMESTAMP
);

-- 9. insurance
CREATE TABLE insurance (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organization(id),
  patient_id UUID REFERENCES patient(id),
  payer_name VARCHAR(255) NOT NULL,
  plan_type VARCHAR(50),
  member_id VARCHAR(255),
  group_number VARCHAR(255),
  eligibility_status eligibility_status DEFAULT 'unknown',
  eligibility_checked_at TIMESTAMP,
  card_front_url VARCHAR(500),
  card_back_url VARCHAR(500),
  is_primary BOOLEAN DEFAULT false,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  deleted_at TIMESTAMP
);

-- 10. referral
CREATE TABLE referral (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organization(id),
  patient_id UUID REFERENCES patient(id),
  referring_provider_name VARCHAR(255),
  referring_npi VARCHAR(255),
  target_specialty VARCHAR(255),
  target_provider_id UUID REFERENCES provider(id),
  reason TEXT,
  urgency VARCHAR(50),
  document_url VARCHAR(500),
  status referral_status NOT NULL DEFAULT 'received',
  received_at TIMESTAMP,
  expires_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- 11. appointment (depends on everything — built last)
CREATE TABLE appointment (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organization(id),
  patient_id UUID REFERENCES patient(id),
  provider_id UUID REFERENCES provider(id),
  referral_id UUID REFERENCES referral(id),
  call_id UUID REFERENCES call(id),
  start_at TIMESTAMP NOT NULL,
  end_at TIMESTAMP NOT NULL,
  type VARCHAR(50) NOT NULL,
  status appointment_status NOT NULL DEFAULT 'scheduled',
  insurance_verified BOOLEAN DEFAULT false,
  referral_required BOOLEAN DEFAULT false,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- 12. audit_log (append-only — no updated_at or deleted_at)
CREATE TABLE audit_log (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID REFERENCES organization(id),
  staff_user_id UUID REFERENCES staff_user(id),
  action audit_action NOT NULL,
  entity_type VARCHAR(100) NOT NULL,
  entity_id UUID NOT NULL,
  ip_address VARCHAR(50),
  occurred_at TIMESTAMP DEFAULT NOW(),
  created_at TIMESTAMP DEFAULT NOW(),
  detail JSONB
);