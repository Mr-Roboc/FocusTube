# FocusTube Project Context

This document provides a comprehensive overview of the FocusTube project for the Gemini AI agent.

## Project Overview

FocusTube is a web application built with Python and Flask. Its primary purpose is to provide a distraction-free environment for watching educational YouTube videos. Users can search for topics, and the application fetches relevant videos using the YouTube Data API v3. The application is designed with a clean, minimalist interface to help users focus on the learning content.

### Key Technologies

*   **Backend:** Python, Flask
*   **Database:** SQLite with Flask-SQLAlchemy
*   **Frontend:** HTML, Bootstrap 5
*   **APIs:** YouTube Data API v3

### Architecture

The project follows a standard Flask application structure:

*   `app.py`: The main application file containing Flask routes, API integration, and application configuration.
*   `database/models.py`: Defines the `Video` database model using SQLAlchemy.
*   `templates/`: Contains the HTML templates for the user interface.
*   `static/`: Holds static assets like CSS and JavaScript files.
*   `.env`: Stores environment variables, specifically the YouTube API key.
*   `focus_tube.db`: The SQLite database file.

## Building and Running

Here are the key commands for setting up and running the FocusTube project:

1.  **Activate the Virtual Environment:**
    *   Before running any commands, ensure the project's virtual environment is activated.
    *   ```bash
        source venv/bin/activate
        ```

2.  **Initialize the Database:**
    *   This command creates the necessary database tables based on the models defined in `database/models.py`.
    *   ```bash
        python -m flask init-db
        ```

3.  **Run the Application:**
    *   This command starts the Flask development server.
    *   ```bash
        flask run
        ```
    *   The application will be accessible at `http://127.0.0.1:5000`.

## Development Conventions

*   **Virtual Environment:** All project dependencies are managed within a dedicated virtual environment located in the `venv/` directory.
*   **Configuration:** Environment variables (like API keys) are managed in a `.env` file and loaded using `python-dotenv`.
*   **Database Migrations:** The project uses a custom Flask CLI command (`flask init-db`) to initialize the database schema.
*   **Styling:** The project uses Bootstrap 5 for its primary styling, with an empty `static/css/style.css` for any custom styles.
*   **Client-Side Scripting:** There is an empty `static/js/script.js` file for any future client-side interactivity.
