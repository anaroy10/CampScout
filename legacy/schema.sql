USE camps_db;
CREATE TABLE Parks (
    park_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    state VARCHAR(150),
    visitors_count INT,
    description TEXT,
    INDEX idx_park_name (name) 
);

CREATE TABLE Activities (
    activity_id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE Campsites (
    site_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    park_id INT,
    recarea_name VARCHAR(150),
    closest_town VARCHAR(150),
    latitude DECIMAL(9,6) NOT NULL,
    longitude DECIMAL(9,6) NOT NULL,
    water_avail VARCHAR(150),
    electricity_hookup VARCHAR(100),
    sewer_hookup VARCHAR(100),
    restrooms VARCHAR(150),
    max_vehicle_length INT,
    max_nbr_vehicles INT,
    capacity INT,
    visitor_rating DECIMAL(3,2),
    FOREIGN KEY (park_id) REFERENCES Parks(park_id) ON DELETE SET NULL,
    INDEX idx_campsite_name (name),
    INDEX idx_location (closest_town)
);

CREATE TABLE Campsite_Activities (
    site_id VARCHAR(50),
    activity_id INT,
    PRIMARY KEY (site_id, activity_id),
    FOREIGN KEY (site_id) REFERENCES Campsites(site_id) ON DELETE CASCADE,
    FOREIGN KEY (activity_id) REFERENCES Activities(activity_id) ON DELETE CASCADE
);