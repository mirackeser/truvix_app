-- Truvix Demo Seed Data
-- Run this script using:
-- psql -h localhost -U truvix_user -d truvix_db -f database/seeds/seed.sql

-- 1 demo user
INSERT INTO users (id, email, password_hash, status, subscription_tier, created_at, updated_at) VALUES 
('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'demo@truvix.app', '$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$RdescudvJCsgt3ub+b+daw', 'active', 'premium', NOW(), NOW());

-- 5 vehicles
INSERT INTO vehicles (id, user_id, brand, model, year, mileage, fuel_type, transmission, body_type, price, location, is_favourite, created_at, updated_at) VALUES
('v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'BMW', '320i', 2023, 25000, 'benzin', 'otomatik', 'sedan', 1850000, 'İstanbul', false, NOW(), NOW()),
('v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a12', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Toyota', 'Corolla', 2021, 58000, 'hybrid', 'otomatik', 'sedan', 1250000, 'Ankara', false, NOW(), NOW()),
('v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a13', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Volkswagen', 'Golf', 2019, 92000, 'dizel', 'manuel', 'hatchback', 980000, 'İzmir', false, NOW(), NOW()),
('v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a14', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Mercedes', 'C200', 2020, 45000, 'benzin', 'otomatik', 'sedan', 2100000, 'İstanbul', true, NOW(), NOW()),
('v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a15', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Ford', 'Focus', 2017, 135000, 'dizel', 'manuel', 'hatchback', 620000, 'Bursa', false, NOW(), NOW());

-- 2 completed analyses (vehicle 1 and 3)
INSERT INTO vehicle_analyses (id, vehicle_id, trust_score, risk_level, summary, created_at, updated_at) VALUES
('a1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 82, 'low', 'Araç genel olarak iyi durumda. Ufak tefek çizikler dışında önemli bir sorun görünmüyor.', NOW(), NOW()),
('a1eebc99-9c0b-4ef8-bb6d-6bb9bd380a13', 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a13', 58, 'high', 'Araçta ciddi kaporta hasarları ve olası mekanik problemler tespit edildi. Detaylı ekspertiz önerilir.', NOW(), NOW());

-- 4 risk findings (for analysis 1 and 2)
INSERT INTO risk_findings (id, analysis_id, severity, description, created_at, updated_at) VALUES
('r0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'a1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'low', 'Sağ ön kapıda ufak çizik.', NOW(), NOW()),
('r0eebc99-9c0b-4ef8-bb6d-6bb9bd380a12', 'a1eebc99-9c0b-4ef8-bb6d-6bb9bd380a13', 'high', 'Ön tamponda ağır hasar izleri.', NOW(), NOW()),
('r0eebc99-9c0b-4ef8-bb6d-6bb9bd380a13', 'a1eebc99-9c0b-4ef8-bb6d-6bb9bd380a13', 'medium', 'Sol arka çamurluk boyalı olabilir.', NOW(), NOW()),
('r0eebc99-9c0b-4ef8-bb6d-6bb9bd380a14', 'a1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'low', 'Lastik diş derinliği sınıra yakın.', NOW(), NOW());

-- Price history
INSERT INTO price_snapshots (id, vehicle_id, price, snapshot_date) VALUES
(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 1900000, NOW() - INTERVAL '5 months'),
(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 1880000, NOW() - INTERVAL '4 months'),
(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 1880000, NOW() - INTERVAL '3 months'),
(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 1860000, NOW() - INTERVAL '2 months'),
(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 1850000, NOW() - INTERVAL '1 month'),
(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 1850000, NOW()),

(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a12', 1200000, NOW() - INTERVAL '5 months'),
(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a12', 1220000, NOW() - INTERVAL '4 months'),
(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a12', 1230000, NOW() - INTERVAL '3 months'),
(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a12', 1240000, NOW() - INTERVAL '2 months'),
(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a12', 1250000, NOW() - INTERVAL '1 month'),
(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a12', 1250000, NOW()),

(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a13', 1050000, NOW() - INTERVAL '5 months'),
(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a13', 1030000, NOW() - INTERVAL '4 months'),
(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a13', 1010000, NOW() - INTERVAL '3 months'),
(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a13', 990000, NOW() - INTERVAL '2 months'),
(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a13', 980000, NOW() - INTERVAL '1 month'),
(gen_random_uuid(), 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a13', 980000, NOW());

-- Notifications
INSERT INTO notifications (id, user_id, type, title, message, is_read, created_at) VALUES
(gen_random_uuid(), 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'welcome', 'Truvix''e Hoş Geldiniz!', 'Premium hesabınız aktif edildi.', false, NOW() - INTERVAL '1 day'),
(gen_random_uuid(), 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'price_drop', 'Fiyat Düşüşü', 'Favori aracınız Mercedes C200 fiyatı düştü.', false, NOW() - INTERVAL '2 hours'),
(gen_random_uuid(), 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'analysis_complete', 'Analiz Tamamlandı', 'BMW 320i analiz raporunuz hazır.', true, NOW() - INTERVAL '5 hours');

-- Collections
INSERT INTO collections (id, user_id, name, created_at, updated_at) VALUES
('c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Favorilerim', NOW(), NOW());

INSERT INTO collection_items (id, collection_id, vehicle_id, created_at) VALUES
(gen_random_uuid(), 'c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'v0eebc99-9c0b-4ef8-bb6d-6bb9bd380a14', NOW());
