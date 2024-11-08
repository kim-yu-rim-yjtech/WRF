CREATE TABLE NCAR_data (
    id SERIAL PRIMARY KEY,
    time VARCHAR(50),
    file_name VARCHAR(50),
    url_path TEXT NOT NULL
);

