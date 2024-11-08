CREATE TABLE mm5 (
    id SERIAL PRIMARY KEY,
    file_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);
